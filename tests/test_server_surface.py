import pytest

from ebay_mcp_server import server


ALL_TOOL_NAMES = {
    "ebay_get_capabilities",
    "ebay_search_items",
    "ebay_get_item",
    "ebay_get_default_category_tree",
    "ebay_suggest_categories",
    "ebay_get_category_aspects",
    "ebay_get_seller_feedback",
    "ebay_translate_text",
    "ebay_get_rate_limits",
    "ebay_sales_provider_status",
    "ebay_sales_open_login",
    "ebay_read_skill",
    "ebay_validate_titles",
    "ebay_get_sales_history",
    "soldeazy_status",
    "soldeazy_open_login",
    "soldeazy_search_datasheet",
    # 2026-11-09 停用：旧「预览 → 令牌 → 写入」链路已整段注释
    # "soldeazy_preview_price_change",
    "soldeazy_stock_template",
    "soldeazy_change_history",
    "soldeazy_list_shops",
    "soldeazy_switch_shop",
    "soldeazy_create_datasheet",
    "soldeazy_delete_datasheet",
    "soldeazy_upload_photo",
    "soldeazy_plan_changes",
    "soldeazy_confirm_plan",
    "soldeazy_apply_plan",
    "soldeazy_change_price",
    "soldeazy_change_stock",
    "soldeazy_reconcile_plan",
    # "soldeazy_preview_stock_change",
    # "soldeazy_update_price",
    # "soldeazy_update_stock",
}


def test_tool_surface_is_general_purpose_and_has_no_selection_or_recall_tools():
    tools = set(server.mcp._tool_manager._tools)
    # MCP_TOOLSET 可以裁掉一半工具（省 schema token）；默认仍是全部 30 个。
    if server.settings.mcp_toolset == "all":
        assert tools == ALL_TOOL_NAMES
        assert len(tools) == 30
    else:
        assert tools == set(
            server.select_tool_names(ALL_TOOL_NAMES, server.settings.mcp_toolset)
        )
    assert not any("recall" in name or "selection" in name for name in tools)
    # 旧写工具已下线：改价/改库存只走 soldeazy_change_price / _change_stock
    assert not ({"soldeazy_update_price", "soldeazy_update_stock"} & tools)
    assert len(server.mcp._resource_manager._resources) == 7


def test_toolset_prefixes_map_to_disjoint_halves():
    """两个子集必须刚好把 30 个工具分完，且互不重叠。"""

    soldeazy = set(server.select_tool_names(ALL_TOOL_NAMES, "soldeazy"))
    official = set(server.select_tool_names(ALL_TOOL_NAMES, "official"))

    assert soldeazy | official == ALL_TOOL_NAMES
    assert not (soldeazy & official)
    assert len(soldeazy) == 16
    assert len(official) == 14
    assert set(server.select_tool_names(ALL_TOOL_NAMES, "all")) == ALL_TOOL_NAMES


def test_toolset_rejects_unknown_values():
    import pytest

    with pytest.raises(ValueError, match="MCP_TOOLSET"):
        server.toolset_prefixes("soldazy")   # 拼错不能静默退回全部


def test_exposed_tools_match_the_configured_toolset():
    """实际暴露的工具面必须等于 MCP_TOOLSET 算出来的那一半。"""

    assert set(server.EXPOSED_TOOLS) == set(
        server.select_tool_names(ALL_TOOL_NAMES, server.settings.mcp_toolset)
    )


def test_toolset_defaults_to_all():
    """不设 MCP_TOOLSET 时默认全开——裁工具必须是显式选择。"""

    import dataclasses

    from ebay_mcp_server.config import Settings

    fields = {field.name: field for field in dataclasses.fields(Settings)}
    assert fields["mcp_toolset"].default == "all"


def test_output_schema_is_disabled_to_save_request_tokens():
    """outputSchema 只是一句 additionalProperties，却每个请求都发一遍。"""

    import asyncio

    tools = asyncio.run(server.mcp.list_tools())
    assert tools
    assert all(tool.outputSchema is None for tool in tools)
    assert len(server.mcp._resource_manager._resources) == 7


@pytest.mark.asyncio
async def test_reserved_sales_tool_fails_closed_without_provider():
    result = await server.ebay_get_sales_history(["314126742195"])
    assert result["success"] is False
    assert result["error"]["code"] == "SALES_PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_sales_login_tool_fails_closed_without_provider():
    result = await server.ebay_sales_open_login()
    assert result["success"] is False
    assert result["error"]["code"] == "SALES_LOGIN_UNSUPPORTED"


@pytest.mark.asyncio
async def test_capabilities_do_not_expose_credentials():
    result = await server.ebay_get_capabilities()
    text = repr(result)
    assert result["success"] is True
    assert "client_secret" not in text
    assert "access_token" not in text
    assert result["data"]["write_tools_enabled"] is False
    assert len(result["data"]["skills"]) == 7


@pytest.mark.asyncio
async def test_workbuddy_skill_bridge_reads_canonical_resource():
    result = await server.ebay_read_skill("ebay-title-generation")
    assert result["success"] is True
    assert result["data"]["skill"]["uri"] == ("skill://ebay-title-generation/SKILL.md")
    assert "exactly 30" in result["data"]["content"]


@pytest.mark.asyncio
async def test_title_validator_tool_uses_local_contract():
    titles = [f"Wireless Earbuds Bluetooth Series {index}" for index in range(30)]
    result = await server.ebay_validate_titles(titles)
    assert result["success"] is True
    assert result["data"]["valid_for_delivery"] is True

# 2026-11-09 停用：旧的令牌写入工具已注释，以下三个用例随之停用（保留代码备查）。
# @pytest.mark.asyncio
# async def test_write_tools_fail_closed_when_the_flag_is_off():
#     for tool in (server.soldeazy_update_price, server.soldeazy_update_stock):
#         result = await tool("any-token")
#         assert result["success"] is False
#         assert result["error"]["code"] == "SOLDEAZY_WRITE_DISABLED"
#
#
# @pytest.mark.asyncio
# async def test_write_tool_rejects_an_unknown_token_even_when_enabled(monkeypatch):
#     import dataclasses
#
#     monkeypatch.setattr(
#         server, "settings", dataclasses.replace(server.settings, soldeazy_write_enabled=True)
#     )
#     result = await server.soldeazy_update_price("not-a-real-token")
#     assert result["success"] is False
#     assert result["error"]["code"] == "SOLDEAZY_TOKEN_INVALID"
#
#
# def test_write_tool_defaults_to_dry_run():
#     import inspect
#
#     signature = inspect.signature(server.soldeazy_update_price)
#     assert signature.parameters["dry_run"].default is True
#     signature = inspect.signature(server.soldeazy_update_stock)
#     assert signature.parameters["dry_run"].default is True

def test_shop_scope_collects_distinct_shops():
    found = {
        "rows": [
            {"shop": "EBAY FUN"},
            {"shop": "EBAY FUN"},
            {"shop": "EBAY LT"},
            {"shop": None},
            {"shop": "  "},
        ]
    }
    assert server._shop_scope(found) == ["EBAY FUN", "EBAY LT"]
    assert server._shop_scope({}) == []
    assert server._shop_scope({"rows": []}) == []


def test_new_write_tools_default_to_dry_run():
    import inspect

    for tool in (
        server.soldeazy_create_datasheet,
        server.soldeazy_delete_datasheet,
        server.soldeazy_upload_photo,
    ):
        assert inspect.signature(tool).parameters["dry_run"].default is True


def test_search_datasheet_site_defaults_to_all_sites():
    """不传站点 = 全部站点，不再直接报错要求先问用户。"""

    import inspect

    signature = inspect.signature(server.soldeazy_search_datasheet)
    assert signature.parameters["site"].default == ""

    for tool in (server.soldeazy_change_price, server.soldeazy_change_stock):
        assert inspect.signature(tool).parameters["site"].default == ""


def test_site_hint_tells_the_user_when_all_sites_are_used():
    assert server._site_hint("US") == {}
    assert server._site_hint("  us ") == {}
    hint = server._site_hint("")
    assert hint["site"] == "ALL"
    assert "全部站点" in hint["site_notice"]
    assert "全部站点" in server._site_hint("   ")["site_notice"]


def test_change_targets_stay_required_positional_first():
    """targets 是必填参数，必须排在带默认值的 site 之前，否则签名非法。"""

    import inspect

    for tool in (server.soldeazy_change_price, server.soldeazy_change_stock):
        params = list(inspect.signature(tool).parameters)
        assert params[0] == "targets"
        assert params[1] == "site"


def test_plan_tools_reject_empty_plan_id():
    import asyncio

    for tool in (
        server.soldeazy_confirm_plan,
        server.soldeazy_apply_plan,
        server.soldeazy_reconcile_plan,
    ):
        result = asyncio.run(tool(""))
        assert result["success"] is False
        assert result["error"]["code"] == "SOLDEAZY_PLAN_MISSING"


def test_apply_plan_has_shop_guard():
    from ebay_mcp_server.providers.soldeazy_apply import shop_problems

    assert callable(shop_problems)



def test_cap_rows_defaults_and_caps():
    from ebay_mcp_server.server import _cap_rows

    rows = [{"rowid": str(i), "sku": "X", "title": "很长的标题" * 10} for i in range(500)]

    page = _cap_rows(rows)
    assert len(page["rows"]) == 20
    assert page["total"] == 500
    assert page["has_more"] is True
    assert "title" not in page["rows"][0]          # 默认不带标题

    huge = _cap_rows(rows, limit=99999)
    assert len(huge["rows"]) == 200                 # 硬上限 200

    last = _cap_rows(rows, limit=20, offset=480)
    assert len(last["rows"]) == 20
    assert last["has_more"] is False


def test_cap_rows_keeps_title_when_asked():
    from ebay_mcp_server.server import _cap_rows

    rows = [{"rowid": "1", "title": "abc"}]
    assert _cap_rows(rows, with_title=True)["rows"][0]["title"] == "abc"


def test_cap_rows_response_is_bounded_in_size():
    """500 条带长标题的数据，裁完后的 JSON 必须远小于全量。"""

    import json

    from ebay_mcp_server.server import _cap_rows

    rows = [
        {"rowid": str(i), "sku": "JJPC0029", "title": "3/8/16 Outlet Surge Protector " * 3,
         "price": 21.9, "qty": 100}
        for i in range(500)
    ]
    full = len(json.dumps(rows, ensure_ascii=False))
    capped = len(json.dumps(_cap_rows(rows), ensure_ascii=False))
    assert capped < full / 8


def test_output_guard_blocks_large_payload():
    from ebay_mcp_server.server import _output_too_large

    big = {"rows": [{"x": "y" * 200} for _ in range(100)]}
    blocked = _output_too_large(big)
    assert blocked is not None
    assert blocked["success"] is False
    assert blocked["error"]["code"] == "SOLDEAZY_OUTPUT_TOO_LARGE"
    assert "确认" in blocked["error"]["message"]
    assert blocked["error"]["details"]["estimated_tokens"] > 0


def test_output_guard_allows_when_confirmed():
    from ebay_mcp_server.server import _output_too_large

    big = {"rows": [{"x": "y" * 200} for _ in range(100)]}
    assert _output_too_large(big, allow=True) is None


def test_output_guard_passes_small_payload():
    from ebay_mcp_server.server import _output_too_large

    assert _output_too_large({"ok": True, "items": 8}) is None


def test_list_shops_is_capped_and_hints_keyword(monkeypatch):
    """生产账号 85 个，全量倒进对话很贵：默认只回 20 个并提示用 keyword。"""

    import asyncio

    shops = [{"id": str(4000 + i), "name": f"EBAY S{i:02d}"} for i in range(85)]
    shops[10] = {"id": "159", "name": "EBAY FUN"}

    async def fake_list():
        return shops

    monkeypatch.setattr(server.soldeazy, "list_shop_options", fake_list)

    page = asyncio.run(server.soldeazy_list_shops())["data"]
    assert page["count"] == 85
    assert len(page["shops"]) == 20
    assert page["has_more"] is True
    assert "keyword" in page["hint"]

    tail = asyncio.run(server.soldeazy_list_shops(offset=80))["data"]
    assert len(tail["shops"]) == 5
    assert tail["has_more"] is False
    assert "hint" not in tail          # 已经看到尾了就不用再提示

    found = asyncio.run(server.soldeazy_list_shops(keyword="FUN"))["data"]
    assert found["count"] == 1
    assert found["shops"][0]["id"] == "159"


def test_schema_requires_only_targets_for_change_tools(monkeypatch):
    """site 变成可选后，schema 里必填项应该只剩 targets。"""

    import asyncio

    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(server.mcp.list_tools())}
    for name in ("soldeazy_change_price", "soldeazy_change_stock", "soldeazy_plan_changes"):
        if name not in schemas:      # MCP_TOOLSET 把这个子集裁掉了
            continue
        required = schemas[name].get("required") or []
        assert "targets" in required
        assert "site" not in required
    if "soldeazy_search_datasheet" in schemas:
        assert "site" not in (schemas["soldeazy_search_datasheet"].get("required") or [])


def test_change_tools_accept_a_targets_file(tmp_path):
    """上千条目标走文件，别让模型逐条生成内联字典。"""

    import asyncio
    import inspect

    for tool in (server.soldeazy_change_price, server.soldeazy_change_stock):
        params = inspect.signature(tool).parameters
        assert "targets_file" in params
        assert params["targets_file"].default == ""

    path = tmp_path / "targets.csv"
    path.write_text("A,10\nB,20\n", encoding="utf-8")

    resolved, info = server._resolve_targets({}, str(path), kind="price")
    assert resolved == {"A": 10.0, "B": 20.0}
    assert info["targets_count"] == 2
    assert info["targets_from"] == str(path)


def test_targets_and_targets_file_together_is_rejected(tmp_path):
    from ebay_mcp_server.errors import EbayMcpError

    path = tmp_path / "t.csv"
    path.write_text("A,10\n", encoding="utf-8")

    with pytest.raises(EbayMcpError) as caught:
        server._resolve_targets({"B": 1.0}, str(path), kind="price")
    assert caught.value.code == "SOLDEAZY_TARGETS_AMBIGUOUS"


def test_targets_file_with_issues_fails_before_any_write(tmp_path):
    """脏文件必须整份拒收，不能带着一半数据去改线上。"""

    from ebay_mcp_server.errors import EbayMcpError

    path = tmp_path / "bad.csv"
    path.write_text("A=10\nB=abc\n", encoding="utf-8")

    with pytest.raises(EbayMcpError) as caught:
        server._resolve_targets({}, str(path), kind="price")
    assert caught.value.code == "SOLDEAZY_TARGETS_FILE"
    assert caught.value.details["issues_total"] == 1


def test_targets_file_missing_is_reported(tmp_path):
    from ebay_mcp_server.errors import EbayMcpError

    with pytest.raises(EbayMcpError) as caught:
        server._resolve_targets({}, str(tmp_path / "none.csv"), kind="price")
    assert caught.value.code == "SOLDEAZY_TARGETS_FILE"


def test_status_reports_plan_dir_too():
    """登录态和计划各在哪，必须能从一次 status 里看出来。"""

    import asyncio

    from ebay_mcp_server import server

    data = asyncio.run(server.soldeazy_status())["data"]
    assert "profile_dir" in data
    assert data["plan_dir"].endswith("soldeazy-plans")


def test_default_page_fits_under_the_output_guard():
    """默认 limit 必须落在 4000 字符闸门内，否则闸门等于没有。"""

    from ebay_mcp_server.server import MAX_OUTPUT_CHARS, _cap_rows

    rows = [
        {"row": i + 3, "rowid": f"45466{i:03d}", "sku": f"SKU{i:04d}", "qty": 50,
         "price": 12.5, "postage": "0.00", "shop": "EBAY FUN", "site": "US"}
        for i in range(500)
    ]
    payload = {**_cap_rows(rows), "site_notice": "当前未选站点，按全部站点执行"}

    assert len(payload["rows"]) == 20
    # 甚至不需要 allow_large_output 就能正常返回
    assert server._output_too_large(payload) is None
    assert len(str(payload)) < MAX_OUTPUT_CHARS


def test_unlisted_plan_turns_sync_shortfall_into_a_warning():
    """FUN 这类全未刊登账号：上传 N 条、同步 0 条是预期内的，不能判失败。"""

    import asyncio

    from ebay_mcp_server.providers import soldeazy_apply as mod

    class FakeBrowser:
        """第一次调用是基线（还没有任务），之后冒出同一条同步任务。"""

        def __init__(self) -> None:
            self.calls = 0

        async def queue_jobs(self, limit=20):
            self.calls += 1
            if self.calls == 1:
                return []
            return [{
                "queue_job_idx": "9",
                "queue_job_act": "DSSync",
                "queue_job_res": {"total_items": "0", "failure_msgs_count": "0"},
            }]

    strict = asyncio.run(
        mod._await_latest_job(FakeBrowser(), 8, attempts=1, wait_seconds=0)
    )
    assert strict["ok"] is False
    assert strict["problems"]

    relaxed = asyncio.run(
        mod._await_latest_job(
            FakeBrowser(), 8, tolerate_mismatch=True, attempts=1, wait_seconds=0
        )
    )
    assert relaxed["ok"] is True
    assert relaxed["problems"] == []
    assert relaxed["notes"]


def test_compact_report_surfaces_sync_warnings_without_failing():
    from ebay_mcp_server.providers.soldeazy_change import compact_plan_report
    from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem

    plan = ChangePlan(
        plan_id="p", kind="price", site="US", shop={"id": "159", "name": "FUN"},
        created_at="x", items=[PlanItem("1", "S", "price", 21.9, 23.0)],
    )
    applied = {
        "ok": True, "sync": "ok", "sync_problems": [],
        "sync_notes": ["同步了 0 个数据表，上传的是 1 个（差额通常是这些数据表没有在线刊登）"],
        "queue": {"ok": True},
    }
    report = compact_plan_report(
        plan, applied=applied, reconcile={"ok": True, "matched": 1, "items": 1}, kind="price"
    )
    assert report["ok"] is True          # 警告不影响判决
    assert report["problems"] == []
    assert report["warnings_total"] == 1


def test_sales_history_truncates_transactions_but_keeps_summary():
    """历史里这个工具单次返回 3.3 万字符：明细必须默认截断，汇总不能截。"""

    import asyncio

    from ebay_mcp_server import server

    captured: dict = {}

    async def fake_search(item_ids, marketplace_id, *, limit, allow_window):
        captured["limit"] = limit
        return {
            "items": [
                {
                    "legacy_item_id": "314126742195",
                    "transactions": [
                        {"price": 1.0 + i, "quantity": 1} for i in range(60)
                    ],
                    "summary": {"visible_transaction_count": 60, "visible_quantity": 60},
                    "coverage": {"returned_records": 60},
                }
            ],
            "failures": [],
            "partial": False,
        }

    class FakeProvider:
        name = "purchase_history"

        search = staticmethod(fake_search)

    original = server.sales_provider
    server.sales_provider = FakeProvider()
    try:
        data = asyncio.run(
            server.ebay_get_sales_history(["314126742195"])
        )["data"]
    finally:
        server.sales_provider = original

    item = data["items"][0]
    assert len(item["transactions"]) == 20          # 默认上限 20
    assert item["transactions_total"] == 60
    assert item["transactions_truncated"] is True
    assert item["summary"]["visible_transaction_count"] == 60   # 汇总仍是全量


def test_validate_titles_can_omit_the_titles_themselves():
    """30 条标题回显约 8k 字符：只要判决时不该把文本再发一遍。"""

    import asyncio

    from ebay_mcp_server import server

    titles = [f"Wireless Earbuds Bluetooth Series {index}" for index in range(30)]

    full = asyncio.run(server.ebay_validate_titles(titles))["data"]
    assert full["titles"][0]["title"] == titles[0]

    lean = asyncio.run(server.ebay_validate_titles(titles, include_titles=False))["data"]
    assert "title" not in lean["titles"][0]
    assert lean["valid_count"] == full["valid_count"]
    assert lean["titles"][0]["index"] == 1


def test_search_returns_page_limit_and_total_records():
    """分页是隐藏成本：返回里必须带 page_limit / total_records 让人看见。"""

    import inspect

    from ebay_mcp_server.providers import soldeazy as mod

    src = inspect.getsource(mod.SoldeazyBrowser.search)
    assert "page_limit" in src
    assert "total_records" in src
    # search 只读档位不改档：改档会把导出按钮的点击绑定弄坏（2026-11-11 实机）
    assert "_read_page_limit" in src
    select_src = inspect.getsource(mod.SoldeazyBrowser.select_datasheets)
    assert "_select_page_limit" in select_src


def test_select_datasheets_walks_pages_and_reports_missing():
    """勾选只作用于渲染出来的行：必须逐页翻，且把没勾到的列出来。"""

    import asyncio

    from ebay_mcp_server.providers import soldeazy as mod

    class FakePage:
        def __init__(self, pages: list[list[str]], cursor: list[int]) -> None:
            self.pages = pages
            self.cursor = cursor

        async def evaluate(self, script: str, arg=None):
            wanted = set(arg or [])
            current = self.pages[self.cursor[0]]
            hit = [row for row in current if row in wanted]
            return {"count": len(hit), "hit": hit}

    class FakeBrowser(mod.SoldeazyBrowser):
        def __init__(self, pages: list[list[str]]) -> None:  # 不碰 settings / playwright
            self._pages = pages
            self._cursor = [0]
            self._fake_page = FakePage(pages, self._cursor)

        async def _ensure_page(self):
            return self._fake_page

        async def _select_page_limit(self, limit: int = 200) -> int:
            return 0    # 假页面没有分页控件

        async def _goto_next_page(self) -> bool:
            if self._cursor[0] + 1 >= len(self._pages):
                return False
            self._cursor[0] += 1
            return True

    browser = FakeBrowser([["111111"], ["222222"]])

    # 目标在第 2 页：必须翻页才能勾到
    picked = asyncio.run(browser.select_datasheets(["222222"]))
    assert picked["selected"] == 1
    assert picked["pages_walked"] == 2
    assert picked["missing"] == []

    # 不存在的 id：翻完所有页后报 missing，不会死循环
    browser = FakeBrowser([["111111"], ["222222"]])   # 新实例：页游标从头开始
    picked = asyncio.run(browser.select_datasheets(["999999"]))
    assert picked["selected"] == 0
    assert picked["pages_walked"] == 2
    assert picked["missing"] == ["999999"]

    # 空请求不翻页
    picked = asyncio.run(browser.select_datasheets([]))
    assert picked == {
        "selected": 0, "wanted": 0, "pages_walked": 0, "found": [], "missing": []
    }


def test_sync_up_via_api_accepts_explicit_row_ids():
    """跨页勾选后页面上的勾选集合不完整：接口参数必须按完整清单给。"""

    import inspect

    from ebay_mcp_server.providers import soldeazy as mod

    sig = inspect.signature(mod.SoldeazyBrowser.sync_up_via_api)
    assert "row_ids" in sig.parameters


def test_expensive_tools_require_confirmation_flag():
    import inspect

    from ebay_mcp_server import server

    for tool in (
        server.soldeazy_search_datasheet,
        server.soldeazy_plan_changes,
        server.soldeazy_apply_plan,
        server.soldeazy_reconcile_plan,
        server.soldeazy_change_price,
        server.soldeazy_change_stock,
    ):
        sig = inspect.signature(tool)
        assert "allow_large_output" in sig.parameters
        assert sig.parameters["allow_large_output"].default is False
