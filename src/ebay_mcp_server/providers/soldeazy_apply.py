"""把冻结的改动计划落到线上，并对账。

- ``build_plan``   读当前实际值 → 生成计划条目（只读，不写）
- ``apply_plan``   按 rowid 分组，一次表单提交改完一个数据表（原子）
- ``reconcile``    重新读实际值，与计划逐条比对，报告写成新文件
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem, new_plan_id

PRICE = "price"
QTY = "qty"
TOLERANCE = 0.005


def _num(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def build_items(
    live: dict[tuple[str, str], dict[str, Any]],
    kind: str,
    targets: dict[str, float],
) -> tuple[list[PlanItem], dict[str, Any]]:
    """按用户的 ``{SKU: 数值}`` 生成计划条目。

    - 改价：SKU 指**子体**，精确命中；精确不到才退化成前缀匹配，
      前缀命中多个不同子体时报冲突，不猜。
    - 改库存：SKU 指**母体**，命中它下面的所有行（父行 + 全部子体行）。
    """

    items: list[PlanItem] = []
    missing: list[str] = []
    conflicts: dict[str, list[str]] = {}

    field = PRICE if kind == "price" else QTY
    key = "price" if kind == "price" else "qty"

    if kind == "price":
        by_sku: dict[str, list[tuple[str, str]]] = {}
        for (rowid, sku) in live:
            by_sku.setdefault(sku, []).append((rowid, sku))

        for raw_sku, target in targets.items():
            wanted = str(raw_sku).strip()
            hits = by_sku.get(wanted, [])
            if not hits:
                candidates = sorted({sku for sku in by_sku if sku.startswith(wanted)})
                if len(candidates) == 1:
                    hits = by_sku[candidates[0]]
                elif len(candidates) > 1:
                    conflicts[wanted] = candidates
                    continue
                else:
                    missing.append(wanted)
                    continue
            for rowid, sku in hits:
                record = live[(rowid, sku)]
                old = _num(record[key])
                if old is None:
                    continue
                if abs(old - float(target)) < TOLERANCE:
                    continue
                items.append(
                    PlanItem(rowid=rowid, sku=sku, field=field, old=old, new=float(target))
                )
    else:
        for raw_sku, target in targets.items():
            wanted = str(raw_sku).strip()
            matched = [
                (rowid, sku)
                for (rowid, sku), record in live.items()
                if str(record.get("parent", "")).strip() == wanted
            ]
            if not matched:
                missing.append(wanted)
                continue
            for rowid, sku in matched:
                record = live[(rowid, sku)]
                old = _num(record[key])
                if old is None:
                    continue
                if abs(old - float(target)) < TOLERANCE:
                    continue
                items.append(
                    PlanItem(rowid=rowid, sku=sku, field=field, old=old, new=float(target))
                )

    report = {"missing": sorted(missing), "conflicts": conflicts}
    return items, report


def make_plan(
    kind: str,
    site: str,
    shop: dict[str, str],
    items: list[PlanItem],
    *,
    supersedes: str = "",
    note: str = "",
) -> ChangePlan:
    return ChangePlan(
        plan_id=new_plan_id(kind),
        kind=kind,
        site=site,
        shop=shop,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        items=items,
        supersedes=supersedes,
        note=note,
    )


def _group(plan: ChangePlan) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in plan.items:
        grouped.setdefault(item.rowid, []).append(
            {"sku": item.sku, "field": item.field, "new": item.new}
        )
    return grouped


def index_rows(matrix: list[list[Any]]) -> dict[tuple[str, str], int]:
    """``(母体rowid, 子体SKU) -> 导出文件里的 1-based 行号``。

    子体行没有 Row ID，归属到最近一个带 rowid 的行。
    """

    index: dict[tuple[str, str], int] = {}
    current = ""
    for number, row in enumerate(matrix, start=1):
        if number == 1:
            continue
        rowid = str(row[0] or "").strip()
        sku = str(row[3] or "").strip()
        if rowid:
            current = rowid
        if sku:
            index[(current, sku)] = number
    return index


def plan_to_cell_changes(
    plan: ChangePlan, matrix: list[list[Any]]
) -> tuple[list[tuple[str, int, Any]], list[dict[str, Any]]]:
    """把计划条目换成 ``(字段, 行号, 新值)``；定位不到的行单独报出来。"""

    index = index_rows(matrix)
    changes: list[tuple[str, int, Any]] = []
    missing: list[dict[str, Any]] = []
    for item in plan.items:
        row = index.get((item.rowid, item.sku))
        if row is None:
            missing.append(item.as_dict())
            continue
        changes.append((item.field, row, item.new))
    return changes, missing


def append_audit(audit_path: Path, plan_id: str, rowid: str, result: dict[str, Any]) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan_id": plan_id,
        "rowid": rowid,
        "success": result.get("success"),
        "applied": len(result.get("applied") or []),
        "failed": result.get("failed") or [],
        "warnings": result.get("warnings") or [],
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


async def apply_plan(browser: Any, plan: ChangePlan, workdir: Path) -> dict[str, Any]:
    """统一走「导出 → 批量改 → 一次上传」：整个计划只有一个上传请求。

    逐条打开表单保存的通道已封存——它每条 2 次请求，规模一上去就慢，
    而且失败粒度反而更碎。这条批量通道从同一份冻结计划出发，对账口径不变。
    """

    from ebay_mcp_server.providers.soldeazy_workbook import (
        build_upload_file,
        read_matrix,
    )

    workdir.mkdir(parents=True, exist_ok=True)
    audit = workdir / f"{plan.plan_id}.audit.jsonl"

    exported = workdir / f"{plan.plan_id}.export.xlsx"
    await browser.search("", plan.site)
    await browser.export(exported)
    _sheet, matrix = read_matrix(exported)

    changes, missing = plan_to_cell_changes(plan, matrix)
    if missing:
        return {
            "plan_id": plan.plan_id,
            "ok": False,
            "channel": "upload",
            "error": "计划里有行在导出结果中定位不到",
            "missing": missing,
            "audit": str(audit),
        }
    if not changes:
        return {
            "plan_id": plan.plan_id,
            "ok": True,
            "channel": "upload",
            "items": 0,
            "note": "所有行已经是目标值，无需上传",
            "audit": str(audit),
        }

    target = workdir / f"{plan.plan_id}.done.xlsx"
    report = build_upload_file(exported, target, changes)
    upload = await browser.upload_via_api(target)

    append_audit(
        audit,
        plan.plan_id,
        "-",
        {
            "success": True,
            "applied": [{"rows": len(changes)}],
            "warnings": [],
        },
    )
    return {
        "plan_id": plan.plan_id,
        "ok": True,
        "channel": "upload",
        "requests": 2,
        "items": len(changes),
        "rows_touched": len(changes),
        "changed_columns": report["changed_columns"],
        "file": report["path"],
        "handle": upload.get("handle"),
        "audit": str(audit),
    }


async def reconcile(
    browser: Any,
    plan: ChangePlan,
    report_dir: Path,
    *,
    attempts: int = 3,
    wait_seconds: float = 20.0,
) -> dict[str, Any]:
    """执行后对账：轮询到稳定，再下结论。

    平台应用是异步的，读一次就判会误报。策略是：
    - 每轮重新导出实际值逐条比对；
    - 全中即停；
    - 连续两轮结果完全一致也算稳定（说明确实没生效，不再空等）。
    """

    await browser.search("", plan.site)

    previous: list[dict[str, Any]] | None = None
    rounds = 0
    matched = 0
    mismatches: list[dict[str, Any]] = []
    absent: list[dict[str, Any]] = []

    for round_no in range(1, attempts + 1):
        rounds = round_no
        live = await browser.read_datasheet_values(plan.site, "", search=False)
        matched = 0
        mismatches = []
        absent = []

        for item in plan.items:
            record = live.get((item.rowid, item.sku))
            if record is None:
                absent.append({"rowid": item.rowid, "sku": item.sku, "field": item.field})
                continue
            actual = _num(record["price" if item.field == "price" else "qty"])
            if actual is None:
                absent.append({"rowid": item.rowid, "sku": item.sku, "field": item.field})
                continue
            if abs(actual - item.new) <= TOLERANCE:
                matched += 1
            else:
                mismatches.append(
                    {
                        "rowid": item.rowid,
                        "sku": item.sku,
                        "field": item.field,
                        "expected": item.new,
                        "actual": actual,
                    }
                )

        if not mismatches and not absent:
            break
        if previous is not None and previous == mismatches and not absent:
            break  # 连续两轮一样，判定为确实没生效
        previous = mismatches
        if round_no < attempts:
            await asyncio.sleep(wait_seconds)

    report = {
        "plan_id": plan.plan_id,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": len(plan.items),
        "matched": matched,
        "mismatched": mismatches,
        "absent": absent,
        "rounds": rounds,
        "ok": not mismatches and not absent,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{plan.plan_id}.reconcile.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report["report"] = str(path)
    return report
