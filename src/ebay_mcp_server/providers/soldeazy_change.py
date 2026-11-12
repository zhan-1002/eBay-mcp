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

# 每个基础 SKU 都可能挂着 x2 / x4 / US 好几个套装，200 个 SKU 就能把判决
# 从 70 token 顶到 2700。只回前几个 + 总数，完整清单在计划文件里。
MAX_PACKS = 10


def cap_packs(packs: Any) -> dict[str, Any]:
    """把 ``skipped_packs`` 压成「前 MAX_PACKS 个 + 总数」；空则返回空字典。"""

    items = list((packs or {}).items())
    if not items:
        return {}
    return {
        "skipped_packs": dict(items[:MAX_PACKS]),
        "skipped_packs_total": len(items),
    }


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
    warnings: list[str] = []
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
        # 预期内的差额（未刊登数据表同步不了）只记警告，不影响判决
        warnings.extend(str(n) for n in applied.get("sync_notes") or [])
        if applied.get("queue_busy"):
            problems.append(str(applied["queue_busy"]))

    if reconcile is not None:
        stage = "reconcile"
        if not reconcile.get("ok"):
            if reconcile.get("error"):
                # 读错店铺这类"根本没比对"，不能报成 0 行不一致
                problems.append(str(reconcile["error"]))
            else:
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

    if warnings:
        report["warnings"] = warnings[:MAX_PROBLEMS]
        report["warnings_total"] = len(warnings)

    if extra:
        for key in ("missing", "conflicts", "unmatched_targets", "plan_sha256"):
            if key in extra and extra[key]:
                report[key] = extra[key]
        report.update(cap_packs(extra.get("skipped_packs")))

    if verbose:
        report["detail"] = {
            "apply": applied,
            "reconcile": reconcile,
            "items": [item.as_dict() for item in (getattr(plan, "items", []) or [])[:50]],
        }
    else:
        report["hint"] = (
            "通过，无需再查明细。"
            if ok
            else "未通过。先看 problems；需要逐条核对再传 verbose=true（较贵）。"
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
    only_listed: bool = True,
    deps: dict[str, Any] | None = None,
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
    live = await browser.read_datasheet_values(site, only_listed=only_listed)
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

        # 一个都没匹配上，不能报"已经是目标值"——那是把"没找到"说成"不用改"。
        if missing:
            return {
                "ok": False,
                "kind": kind,
                "plan_id": "",
                "items": 0,
                "missing": missing[:MAX_PROBLEMS],
                "missing_total": len(missing),
                "problems": [
                    f"{len(missing)} 个目标在线上找不到对应行",
                ],
                "problems_total": 1,
                "hint": (
                    "检查 SKU 写法；如果生产账号里这些是未刊登，"
                    "需要 include_unlisted=true 才会被查到。"
                    "如果只有套装，请显式写 'SKU x2' 才会改套装。"
                ),
            }

        return {
            "ok": True,
            "kind": kind,
            "plan_id": "",
            "items": 0,
            "note": "所有行已经是目标值，未生成计划",
            "missing": [],
            "problems": [],
        }

    plan = make_plan(kind, site, picked, items, only_listed=only_listed)

    if dry_run:
        # 预览不落盘：计划文件是"将要执行"的承诺，没确认前不留痕迹
        preview = {
            "ok": True,
            "dry_run": True,
            "kind": kind,
            "plan_id": plan.plan_id,
            "items": len(items),
            "datasheets": len({item.rowid for item in items}),
            "only_listed": only_listed,
            "skipped_packs": {},
            "sample": [item.as_dict() for item in items[:5]],
            "hint": "确认无误后传 dry_run=false 执行",
        }
        preview.update(cap_packs(build_report.get("skipped_packs")))
        return preview

    write_draft(plan_dir, plan)
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
            "skipped_packs": build_report.get("skipped_packs") or {},
            "plan_sha256": digest,
        },
    )
