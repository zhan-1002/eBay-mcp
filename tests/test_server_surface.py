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
        "soldeazy_preview_stock_change",
        "soldeazy_update_price",
        "soldeazy_update_stock",
    } <= tools
    assert len(tools) == 28
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
