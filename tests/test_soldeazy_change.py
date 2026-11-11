

def test_compact_report_is_small_and_verdict_first():
    """一步工具的返回必须是判决，不是明细。"""

    import json

    from ebay_mcp_server.providers.soldeazy_change import compact_plan_report
    from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem

    plan = ChangePlan(
        plan_id="price-x", kind="price", site="US",
        shop={"id": "159", "name": "FUN"}, created_at="2026-11-09",
        items=[PlanItem(str(4523000 + i), "JJPC0029", "price", 21.9, 23.0) for i in range(200)],
    )
    applied = {"ok": True, "sync": "ok", "sync_problems": [], "queue": {"ok": True}}
    reconciled = {"ok": True, "matched": 200, "items": 200}

    report = compact_plan_report(plan, applied=applied, reconcile=reconciled, kind="price")
    text = json.dumps(report, ensure_ascii=False)

    assert report["ok"] is True
    assert report["items"] == 200
    assert report["reconciled"] == "200/200"
    assert "detail" not in report
    # 200 条改动也必须压到很小的返回
    assert len(text) < 600


def test_compact_report_surfaces_problems_on_failure():
    import json

    from ebay_mcp_server.providers.soldeazy_change import compact_plan_report
    from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem

    plan = ChangePlan(
        plan_id="price-y", kind="price", site="US",
        shop={"id": "159", "name": "FUN"}, created_at="2026-11-09",
        items=[PlanItem("4512957", "JJPC0029", "price", 21.9, 23.0)],
    )
    applied = {"ok": False, "error": "工序处理了 7 个数据表，计划是 8 个", "queue": {"ok": False, "problems": ["工序任务有 1 条失败"]}}
    reconciled = {"ok": False, "matched": 0, "items": 1, "mismatched_total": 1, "absent_total": 0}

    report = compact_plan_report(plan, applied=applied, reconcile=reconciled, kind="price")
    assert report["ok"] is False
    assert report["problems"]
    assert len(report["problems"]) <= 10
    assert len(json.dumps(report, ensure_ascii=False)) < 900


def test_compact_report_problems_are_capped():
    from ebay_mcp_server.providers.soldeazy_change import MAX_PROBLEMS, compact_plan_report
    from ebay_mcp_server.providers.soldeazy_plan import ChangePlan

    plan = ChangePlan(plan_id="p", kind="price", site="US", shop={}, created_at="x", items=[])
    applied = {"ok": False, "queue": {"ok": False, "problems": [f"问题{i}" for i in range(100)]}}

    report = compact_plan_report(plan, applied=applied, reconcile=None, kind="price")
    assert len(report["problems"]) == MAX_PROBLEMS
    # 100 条队列问题 + 1 条“执行未通过”总述
    assert report["problems_total"] == 101


def test_compact_report_surfaces_missing_targets():
    """压缩返回不能把"没匹配上的目标"吞掉——这是校对能力的一部分。"""

    from ebay_mcp_server.providers.soldeazy_change import compact_plan_report
    from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem

    plan = ChangePlan(
        plan_id="price-z", kind="price", site="US",
        shop={"id": "159", "name": "FUN"}, created_at="2026-11-09",
        items=[PlanItem("4512957", "JJPC0029", "price", 21.9, 23.0)],
    )
    applied = {"ok": True, "sync": "ok", "sync_problems": [], "queue": {"ok": True}}
    reconciled = {"ok": True, "matched": 1, "items": 1}

    report = compact_plan_report(
        plan, applied=applied, reconcile=reconciled, kind="price",
        extra={"missing": ["NOT-EXIST"], "unmatched_targets": 1, "plan_sha256": "a" * 64},
    )
    assert report["ok"] is True
    assert report["missing"] == ["NOT-EXIST"]
    assert report["unmatched_targets"] == 1
    assert report["plan_sha256"] == "a" * 64


def test_compact_report_omits_empty_extras():
    from ebay_mcp_server.providers.soldeazy_change import compact_plan_report
    from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem

    plan = ChangePlan(
        plan_id="p", kind="price", site="US", shop={}, created_at="x",
        items=[PlanItem("1", "S", "price", 1.0, 2.0)],
    )
    report = compact_plan_report(
        plan, applied={"ok": True, "queue": {"ok": True}, "sync_problems": []},
        reconcile={"ok": True, "matched": 1, "items": 1}, kind="price",
        extra={"missing": [], "unmatched_targets": 0},
    )
    assert "missing" not in report
    assert "unmatched_targets" not in report


async def _async_shop(shop):
    return {"id": "159", "name": "FUN"}


def test_change_reports_missing_instead_of_noop(tmp_path):
    """线上一条都没匹配上时，必须报"找不到"，不能报"已经是目标值"。"""

    import asyncio

    from ebay_mcp_server.providers import soldeazy_change as mod

    class FakeBrowser:
        async def read_datasheet_values(self, site, query="", **kwargs):
            return {}          # 线上什么都没有

    async def run():
        return await mod.run_change(
            kind="price", site="US", targets={"JJPC0029": 23.0}, shop="",
            dry_run=True, sync=True, sync_price=True, sync_quantity=False,
            verbose=False, only_listed=True,
            deps={
                "build_items": __import__(
                    "ebay_mcp_server.providers.soldeazy_apply", fromlist=["build_items"]
                ).build_items,
                "make_plan": lambda *a, **k: None,
                "write_draft": lambda *a, **k: None,
                "freeze": lambda *a, **k: None,
                "load_verified": lambda *a, **k: (None, ""),
                "apply_plan": None,
                "reconcile": None,
                "plan_dir": tmp_path,
                "browser": FakeBrowser(),
                "resolve_shop": _async_shop,
            },
        )

    result = asyncio.run(run())
    assert result["ok"] is False
    assert result["missing"] == ["JJPC0029"]
    assert "找不到" in result["problems"][0]


def test_empty_site_flows_through_as_all_sites(tmp_path):
    """不传站点时，"全部" 必须一路传到读取和计划，不能被偷偷替换成 US。"""

    import asyncio
    import types

    from ebay_mcp_server.providers import soldeazy_change as mod
    from ebay_mcp_server.providers.soldeazy_apply import build_items

    seen: dict[str, object] = {}

    class FakeBrowser:
        async def read_datasheet_values(self, site, query="", **kwargs):
            seen["site"] = site
            return {
                ("4512957", "JJPC0029"): {
                    "rowid": "4512957", "parent": "JJPC0029",
                    "sku": "JJPC0029", "qty": 100, "price": 21.9,
                }
            }

    def fake_make_plan(kind, site, picked, items, **kwargs):
        seen["plan_site"] = site
        return types.SimpleNamespace(plan_id="price-all", items=list(items))

    async def run():
        return await mod.run_change(
            kind="price", site="", targets={"JJPC0029": 23.0}, shop="",
            dry_run=True, sync=True, sync_price=True, sync_quantity=False,
            verbose=False, only_listed=True,
            deps={
                "build_items": build_items,
                "make_plan": fake_make_plan,
                "write_draft": lambda *a, **k: None,
                "freeze": lambda *a, **k: None,
                "load_verified": lambda *a, **k: (None, ""),
                "apply_plan": None,
                "reconcile": None,
                "plan_dir": tmp_path,
                "browser": FakeBrowser(),
                "resolve_shop": _async_shop,
            },
        )

    result = asyncio.run(run())
    assert seen["site"] == ""
    assert seen["plan_site"] == ""
    assert result["dry_run"] is True
    assert result["items"] == 1


def test_change_reports_noop_when_already_at_target(tmp_path):
    import asyncio

    from ebay_mcp_server.providers import soldeazy_change as mod
    from ebay_mcp_server.providers.soldeazy_apply import build_items

    class FakeBrowser:
        async def read_datasheet_values(self, site, query="", **kwargs):
            return {
                ("4512957", "JJPC0029"): {
                    "rowid": "4512957", "parent": "JJPC0029",
                    "sku": "JJPC0029", "qty": 100, "price": 23.0,
                }
            }

    async def run():
        return await mod.run_change(
            kind="price", site="US", targets={"JJPC0029": 23.0}, shop="",
            dry_run=True, sync=True, sync_price=True, sync_quantity=False,
            verbose=False, only_listed=True,
            deps={
                "build_items": build_items,
                "make_plan": lambda *a, **k: None,
                "write_draft": lambda *a, **k: None,
                "freeze": lambda *a, **k: None,
                "load_verified": lambda *a, **k: (None, ""),
                "apply_plan": None,
                "reconcile": None,
                "plan_dir": tmp_path,
                "browser": FakeBrowser(),
                "resolve_shop": _async_shop,
            },
        )

    result = asyncio.run(run())
    assert result["ok"] is True
    assert result["items"] == 0
    assert "已经是目标值" in result["note"]
    assert result["missing"] == []
