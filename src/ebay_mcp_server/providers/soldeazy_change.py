"""一步到位的改价/改库存：服务端自己校验，只回判决。

为什么要有这个工具：

原来的流程是「起草 → 确认 → 执行 → 对账」四个工具，每一步都把明细推进对话，
让 agent 读了再判断。生产账号一次几千行，agent 反复读这些明细，实测累积到
**6000 万 token**。真正的浪费不是单次返回大，而是"把校验责任推给模型"。

这里把四步合到服务端：起草、冻结、执行、对账都在内部完成，
只回一个 ``ok`` + 计数 + 问题列表（有条数上限）。明细写文件，
调用方只在 ``ok=false`` 时才需要深挖。
"""

from __future__ import annotations

from typing import Any

from ebay_mcp_server.errors import EbayMcpError

# 单次返回的问题条数上限：出错时也不该把整份清单倒进对话
MAX_PROBLEMS = 10


def compact_plan_report(
    plan: Any,
    *,
    applied: dict[str, Any] | None,
    reconcile: dict[str, Any] | None,
    kind: str,
    verbose: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把四步结果压成一个判决。

    ``extra`` 用来带「没匹配上的目标」「前缀歧义」这类必须让调用方知道的信息——
    压缩返回不能把它们吞掉。
    ``verbose=True`` 时才附带逐条明细——给确实要排查的场景用。
    """

    problems: list[str] = []
    stage = "plan"

    if applied is not None:
        stage = "apply"
        if not applied.get("ok"):
            problems.append(str(applied.get("error") or "执行未通过"))
            problems.extend(str(item) for item in (applied.get("problems") or []))
            for item in applied.get("missing") or []:
                problems.append(f"定位不到：{item.get('rowid')}/{item.get('sku')}")
        queue = applied.get("queue") or {}
        if queue and not queue.get("ok"):
            problems.extend(str(p) for p in queue.get("problems") or [])
        problems.extend(str(p) for p in applied.get("sync_problems") or [])
        if applied.get("queue_busy"):
            problems.append(str(applied["queue_busy"]))

    if reconcile is not None:
        stage = "reconcile"
        if not reconcile.get("ok"):
            missed = reconcile.get("mismatched_total", len(reconcile.get("mismatched") or []))
            gone = reconcile.get("absent_total", len(reconcile.get("absent") or []))
            problems.append(f"对账不一致 {missed} 行、查不到 {gone} 行")

    ok = applied is not None and bool(applied.get("ok")) and bool(
        (reconcile or {}).get("ok")
    )

    report: dict[str, Any] = {
        "ok": ok,
        "kind": kind,
        "plan_id": getattr(plan, "plan_id", ""),
        "items": len(getattr(plan, "items", []) or []),
        "datasheets": len({item.rowid for item in getattr(plan, "items", []) or []}),
        "uploaded": bool(applied and applied.get("ok")),
        "synced": (applied or {}).get("sync") or "skipped",
        "reconciled": (
            f"{(reconcile or {}).get('matched', 0)}/{(reconcile or {}).get('items', 0)}"
            if reconcile
            else "skipped"
        ),
        "stage": stage if not ok else "done",
        "problems": problems[:MAX_PROBLEMS],
        "problems_total": len(problems),
    }

    if extra:
        for key in ("missing", "conflicts", "unmatched_targets", "plan_sha256"):
            if key in extra and extra[key]:
                report[key] = extra[key]

    if verbose:
        report["detail"] = {
            "apply": applied,
            "reconcile": reconcile,
            "items": [item.as_dict() for item in (getattr(plan, "items", []) or [])[:50]],
        }
    else:
        report["hint"] = (
            "通过。明细在 plan/reconcile 文件里，需要时用 verbose=true 或读文件。"
            if ok
            else "未通过。先看 problems；需要逐条明细用 verbose=true。"
        )
    return report


async def run_change(
    *,
    kind: str,
    site: str,
    targets: dict[str, float],
    shop: str,
    dry_run: bool,
    sync: bool,
    sync_price: bool,
    sync_quantity: bool,
    verbose: bool,
    deps: dict[str, Any],
) -> dict[str, Any]:
    """内部串起 起草 → 冻结 → 执行 → 对账，返回压缩后的判决。"""

    build_items = deps["build_items"]
    make_plan = deps["make_plan"]
    write_draft = deps["write_draft"]
    freeze = deps["freeze"]
    apply_plan = deps["apply_plan"]
    reconcile = deps["reconcile"]
    plan_dir = deps["plan_dir"]

    browser = deps["browser"]
    resolve_shop = deps["resolve_shop"]

    picked = await resolve_shop(shop)
    live = await browser.read_datasheet_values(site)
    items, build_report = build_items(live, kind, targets)

    if not items:
        conflicts = build_report.get("conflicts") or {}
        missing = build_report.get("missing") or []
        if conflicts:
            raise EbayMcpError(
                "SOLDEAZY_PLAN_AMBIGUOUS",
                "SKU 前缀命中多个子体，无法判断改哪个",
                details={"conflicts": conflicts, "missing": missing[:MAX_PROBLEMS]},
            )
        return {
            "ok": True,
            "kind": kind,
            "plan_id": "",
            "items": 0,
            "note": "所有行已经是目标值，未生成计划",
            "missing": missing[:MAX_PROBLEMS],
            "problems": [],
        }

    plan = make_plan(kind, site, picked, items)
    write_draft(plan_dir, plan)

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "kind": kind,
            "plan_id": plan.plan_id,
            "items": len(items),
            "datasheets": len({item.rowid for item in items}),
            "sample": [item.as_dict() for item in items[:5]],
            "hint": "确认无误后传 dry_run=false 执行",
        }

    frozen = freeze(plan_dir, plan)
    # 冻结后回读一次：确认落盘内容和哈希一致，和分步路径同等强度
    load_verified = deps["load_verified"]
    verified_plan, digest = load_verified(plan_dir, plan.plan_id)
    plan = verified_plan

    applied = await apply_plan(
        browser,
        plan,
        plan_dir,
        sync=sync,
        sync_price=sync_price,
        sync_quantity=sync_quantity,
    )
    reconcile_result = await reconcile(browser, plan, plan_dir)
    return compact_plan_report(
        plan,
        applied=applied,
        reconcile=reconcile_result,
        kind=kind,
        verbose=verbose,
        extra={
            "missing": (build_report.get("missing") or [])[:MAX_PROBLEMS],
            "unmatched_targets": len(build_report.get("missing") or []),
            "plan_sha256": digest,
        },
    )
