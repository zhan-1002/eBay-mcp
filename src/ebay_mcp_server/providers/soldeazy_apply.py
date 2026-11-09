"""把冻结的改动计划落到线上，并对账。

- ``build_plan``   读当前实际值 → 生成计划条目（只读，不写）
- ``apply_plan``   按 rowid 分组，一次表单提交改完一个数据表（原子）
- ``reconcile``    重新读实际值，与计划逐条比对，报告写成新文件
"""

from __future__ import annotations

import asyncio
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

    from ebay_mcp_server.providers.soldeazy_workbook import header_row_count

    index: dict[tuple[str, str], int] = {}
    current = ""
    header = header_row_count(matrix)
    for number, row in enumerate(matrix, start=1):
        if number <= header:
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


def shop_problems(plan: ChangePlan, matrix: list[list[Any]], current_shop: dict | None) -> list[str]:
    """确认导出的数据和计划属于同一个渠道账号。

    两个来源都要对：a) 当前活动账号；b) 导出文件里实际出现的店铺名。
    少任何一条，切号后执行都会悄悄写进别的店铺。
    """

    problems: list[str] = []
    expected_id = str((plan.shop or {}).get("id") or "").strip()
    expected_name = str((plan.shop or {}).get("name") or "").strip()
    current_id = str((current_shop or {}).get("id") or "").strip()

    if expected_id and current_id and expected_id != current_id:
        problems.append(
            f"活动渠道账号已从 {expected_name or expected_id} 切到 {current_id}，请重新预览"
        )

    from ebay_mcp_server.providers.soldeazy_workbook import header_row_count

    header = header_row_count(matrix)
    shops = {
        str(row[1] or "").strip()
        for row in matrix[header:]
        if len(row) > 1 and str(row[1] or "").strip()
    }
    if expected_name and shops and expected_name not in shops:
        problems.append(f"导出结果里没有计划所属的渠道账号 {expected_name}，实际为 {sorted(shops)}")
    return problems


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


def datasheet_spans(matrix: list[list[Any]]) -> dict[str, list[int]]:
    """``母体rowid -> 这个数据表占用的全部行号``（含母体行与所有子体行）。

    导出表里一个多变体数据表是连续的几行：母体行有 Row ID，后面跟着
    若干无 Row ID 的子体行，直到下一个带 Row ID 的行为止。
    """

    from ebay_mcp_server.providers.soldeazy_workbook import header_row_count

    spans: dict[str, list[int]] = {}
    current = ""
    header = header_row_count(matrix)
    for number, row in enumerate(matrix, start=1):
        if number <= header:
            continue
        rowid = str(row[0] or "").strip()
        if rowid:
            current = rowid
            spans[current] = [number]
        elif current:
            spans[current].append(number)
    return spans


def plan_rows(plan: ChangePlan, matrix: list[list[Any]]) -> list[int]:
    """计划涉及的数据表在导出文件里占用的全部行号。

    必须带上母体行与全部子体行：只传子体行会丢结构，只传母体行则子体不跟随。
    """

    spans = datasheet_spans(matrix)
    keep: set[int] = set()
    for item in plan.items:
        keep.update(spans.get(item.rowid, []))
    return sorted(keep)


async def apply_plan(
    browser: Any,
    plan: ChangePlan,
    workdir: Path,
    *,
    sync: bool = True,
    sync_price: bool = True,
    sync_quantity: bool = False,
) -> dict[str, Any]:
    """统一走「导出 → 批量改 → 一次上传 →（可选）同步上平台」。

    上传文件只保留**计划涉及的数据表**（``keep_rows``）——实测整份导出上传时，
    平台会把文件里每一行都 revise 一遍，没打算动的行会被覆盖成导出时的值。

    上传后按工序管理核对：``total_items`` 与计划的数据表数一致，且逐行成功。
    ``sync=True`` 时再勾选同一批数据表做 BULK SYNC，并核对同步条数——
    两者数量不一致是常态（没有在线刊登的数据表同步不了），但必须报出来。
    """

    from ebay_mcp_server.providers.soldeazy_workbook import (
        build_upload_file,
        read_matrix,
    )

    workdir.mkdir(parents=True, exist_ok=True)
    audit = workdir / f"{plan.plan_id}.audit.jsonl"
    expected_datasheets = len({item.rowid for item in plan.items})

    exported = workdir / f"{plan.plan_id}.export.xlsx"
    await browser.search("", plan.site)
    await browser.export(exported)
    _sheet, matrix = read_matrix(exported)

    # 切了渠道账号还拿旧计划执行，会写进别的店铺——这里直接拦住
    guard = shop_problems(plan, matrix, getattr(browser, "active_shop", None))
    if guard:
        return {
            "plan_id": plan.plan_id,
            "ok": False,
            "channel": "upload",
            "error": "渠道账号与计划不一致，已中止（未上传）",
            "problems": guard,
            "audit": str(audit),
        }

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

    keep = plan_rows(plan, matrix)
    target = workdir / f"{plan.plan_id}.done.xlsx"
    report = build_upload_file(exported, target, changes, keep_rows=keep)
    upload = await browser.upload_via_api(target)
    handle = upload.get("handle")

    # 等工序任务结束再核对，避免读到"处理中"
    queue = await _await_queue(browser, handle, expected_datasheets)

    busy = await _active_jobs(browser)
    busy_note = (
        f"工序队列还有 {len(busy)} 个任务在执行中（{', '.join(str(j.get('queue_job_idx')) for j in busy[:5])}），"
        "本次会排队，耗时会变长"
        if busy
        else ""
    )

    sync_result: dict[str, Any] | None = None
    sync_problems: list[str] = []
    if sync:
        planned_ids = sorted({item.rowid for item in plan.items})
        # 重新搜索后再勾选，BULK SYNC 只作用于勾选行
        await browser.search("", plan.site)
        selected = await browser.select_datasheets(planned_ids)
        if selected != len(planned_ids):
            sync_problems.append(
                f"只勾选到 {selected} 个数据表，计划是 {len(planned_ids)} 个"
            )
        sync_result = await browser.sync_up_via_api(
            price_postage=sync_price, quantity=sync_quantity
        )
        # 同步接口会回传全部勾选行，条数一多就是上万 token——只留样本
        if isinstance(sync_result, dict) and isinstance(sync_result.get("table_row_ids"), list):
            ids = sync_result["table_row_ids"]
            sync_result["table_row_ids"] = ids[:20]
            sync_result["table_row_ids_total"] = len(ids)
            sync_result["table_row_ids_truncated"] = len(ids) > 20
        sync_queue = await _await_latest_job(browser, expected_datasheets)
        if sync_queue:
            sync_result["queue"] = sync_queue
            sync_problems.extend(sync_queue.get("problems") or [])

    if sync_result and not sync_problems:
        sync_status = "ok"
    elif sync_result:
        sync_status = "partial"
    else:
        sync_status = "skipped"

    append_audit(
        audit,
        plan.plan_id,
        "-",
        {
            "success": bool(queue.get("ok")),
            "applied": [{"rows": len(changes), "datasheets": expected_datasheets}],
            "warnings": (queue.get("problems") or []) + sync_problems,
        },
    )
    return {
        "plan_id": plan.plan_id,
        "ok": bool(queue.get("ok")) and not sync_problems,
        "channel": "upload",
        "requests": 4 if sync else 2,
        "items": len(changes),
        "rows_touched": len(changes),
        "uploaded_rows": report.get("rows"),
        "expected_datasheets": expected_datasheets,
        "changed_columns": report["changed_columns"],
        "file": report["path"],
        "handle": handle,
        "queue": queue,
        "sync": sync_status,
        "sync_result": sync_result,
        "sync_problems": sync_problems,
        "queue_busy": busy_note,
        "audit": str(audit),
    }


async def _await_queue(
    browser: Any,
    handle: Any,
    expected_datasheets: int,
    *,
    attempts: int = 10,
    wait_seconds: float = 6.0,
) -> dict[str, Any]:
    """轮询工序管理，确认任务完成、条数对得上、逐行成功。"""

    if handle in (None, ""):
        return {"ok": False, "problems": ["上传没有返回 handle，无法核对工序任务"]}

    job_id = str(handle)
    job: dict[str, Any] = {}
    for attempt in range(attempts):
        jobs = await browser.queue_jobs(limit=50)
        job = next((j for j in jobs if str(j.get("queue_job_idx")) == job_id), {})
        if job:
            res = job.get("queue_job_res") or {}
            processing = str(res.get("processing_msgs_count", "0"))
            if processing in {"0", ""} and str(job.get("queue_job_enddate") or "").strip():
                break
        elif attempt >= 2:
            # 列表里翻不到（任务太多或被清理）就别再空等，详情接口按 id 一定能查
            break
        await asyncio.sleep(wait_seconds)

    detail = await browser.queue_result(job_id)
    rows = detail.get("rows") or []

    if not job and not rows:
        return {
            "ok": False,
            "job_id": job_id,
            "problems": ["工序列表里找不到这个任务，按 id 也查不到明细"],
        }

    res = job.get("queue_job_res") or {}
    total = str(res.get("total_items", "")) or str(len(rows))
    success = str(res.get("success_msgs_count", "")) or str(
        sum(1 for row in rows if "successful" in row["result"].lower())
    )
    failed = str(res.get("failure_msgs_count", "0"))

    problems: list[str] = []
    if failed not in {"0", ""}:
        problems.append(f"工序任务有 {failed} 条失败")
    if total and total != str(expected_datasheets):
        problems.append(
            f"工序处理了 {total} 个数据表，计划是 {expected_datasheets} 个"
        )

    bad_rows = [row for row in detail.get("rows") or [] if "successful" not in row["result"].lower()]
    if bad_rows:
        problems.append(f"{len(bad_rows)} 行结果不是 Revise Successful")

    return {
        "ok": not problems,
        "job_id": job_id,
        "act": job.get("queue_job_act"),
        "status": job.get("queue_job_status"),
        "created": job.get("queue_job_createdate"),
        "total_items": total,
        "success": success,
        "failed": failed,
        "expected_datasheets": expected_datasheets,
        "rowids": [row["rowid"] for row in rows][:20],
        "rowids_total": len(rows),
        "rowids_truncated": len(rows) > 20,
        "problems": problems,
    }


def _trim_ids(ids: list[str], limit: int = 20) -> dict[str, Any]:
    """回传时只带前 N 个 id。

    实战里单批最多出现过 2557 条，完整列表在返回里重复两次，
    光这一项就吃掉 1.4 万 token，而且对调用方没有价值。
    """

    sample = ids[:limit]
    return {
        "rowids": sample,
        "rowids_total": len(ids),
        "rowids_truncated": len(ids) > limit,
    }


async def _active_jobs(browser: Any) -> list[dict[str, Any]]:
    """列出仍在执行中的工序任务（没有结束时间的）。"""

    try:
        jobs = await browser.queue_jobs(limit=30)
    except Exception:  # noqa: BLE001 - 查不到不算错误
        return []
    return [
        job
        for job in jobs
        if not str(job.get("queue_job_enddate") or "").strip()
    ]


async def _await_latest_job(
    browser: Any,
    expected: int,
    *,
    attempts: int = 10,
    wait_seconds: float = 6.0,
) -> dict[str, Any] | None:
    """同步接口不返回任务号，只能等工序管理里冒出新的同步任务。

    以"本轮之前见过的最新 job_idx"为基线，找比它更新的那条。
    """

    try:
        baseline = {str(job.get("queue_job_idx")) for job in await browser.queue_jobs(limit=20)}
    except Exception:  # noqa: BLE001 - 拿不到基线就不做比对
        baseline = set()

    for _ in range(attempts):
        try:
            jobs = await browser.queue_jobs(limit=20)
        except Exception:  # noqa: BLE001
            jobs = []
        fresh = [job for job in jobs if str(job.get("queue_job_idx")) not in baseline]
        if fresh:
            job = fresh[0]
            res = job.get("queue_job_res") or {}
            total = str(res.get("total_items", ""))
            failed = str(res.get("failure_msgs_count", "0"))
            problems: list[str] = []
            if failed not in {"0", ""}:
                problems.append(f"同步任务有 {failed} 条失败")
            if total and total != str(expected):
                problems.append(
                    f"同步了 {total} 个数据表，上传的是 {expected} 个"
                    "（差额通常是这些数据表没有在线刊登，同步不处理）"
                )
            return {
                "ok": not problems,
                "job_id": str(job.get("queue_job_idx")),
                "act": job.get("queue_job_act"),
                "total_items": total,
                "success": str(res.get("success_msgs_count", "")),
                "failed": failed,
                "problems": problems,
            }
        await asyncio.sleep(wait_seconds)
    return None


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
