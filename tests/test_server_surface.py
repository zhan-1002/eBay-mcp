import pytest

from ebay_mcp_server import server


def test_tool_surface_is_general_purpose_and_has_no_selection_or_recall_tools():
    tools = set(server.mcp._tool_manager._tools)
    assert {
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
    } <= tools
    assert len(tools) == 30
    assert not any("recall" in name or "selection" in name for name in tools)
    # 旧写工具已下线：改价/改库存只走 soldeazy_change_price / _change_stock
    assert not ({"soldeazy_update_price", "soldeazy_update_stock"} & tools)
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
    assert len(page["rows"]) == 50
    assert page["total"] == 500
    assert page["has_more"] is True
    assert "title" not in page["rows"][0]          # 默认不带标题

    huge = _cap_rows(rows, limit=99999)
    assert len(huge["rows"]) == 200                 # 硬上限 200

    last = _cap_rows(rows, limit=50, offset=480)
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
        required = schemas[name].get("required") or []
        assert "targets" in required
        assert "site" not in required
    assert "site" not in (schemas["soldeazy_search_datasheet"].get("required") or [])


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
