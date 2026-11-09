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
        "soldeazy_preview_price_change",
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
        "soldeazy_preview_stock_change",
        "soldeazy_update_price",
        "soldeazy_update_stock",
    } <= tools
    assert len(tools) == 34
    assert not any("recall" in name or "selection" in name for name in tools)
    # 写工具已注册但默认关闭：没有 SOLDEAZY_WRITE_ENABLED 时一律拒绝
    assert {"soldeazy_update_price", "soldeazy_update_stock"} <= tools
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

@pytest.mark.asyncio
async def test_write_tools_fail_closed_when_the_flag_is_off():
    for tool in (server.soldeazy_update_price, server.soldeazy_update_stock):
        result = await tool("any-token")
        assert result["success"] is False
        assert result["error"]["code"] == "SOLDEAZY_WRITE_DISABLED"


@pytest.mark.asyncio
async def test_write_tool_rejects_an_unknown_token_even_when_enabled(monkeypatch):
    import dataclasses

    monkeypatch.setattr(
        server, "settings", dataclasses.replace(server.settings, soldeazy_write_enabled=True)
    )
    result = await server.soldeazy_update_price("not-a-real-token")
    assert result["success"] is False
    assert result["error"]["code"] == "SOLDEAZY_TOKEN_INVALID"


def test_write_tool_defaults_to_dry_run():
    import inspect

    signature = inspect.signature(server.soldeazy_update_price)
    assert signature.parameters["dry_run"].default is True
    signature = inspect.signature(server.soldeazy_update_stock)
    assert signature.parameters["dry_run"].default is True

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


def test_search_datasheet_requires_site_but_allows_empty_query():
    import asyncio

    result = asyncio.run(server.soldeazy_search_datasheet(""))
    assert result["success"] is False
    assert result["error"]["code"] == "SOLDEAZY_SITE_REQUIRED"


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
