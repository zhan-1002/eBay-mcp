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
        "ebay_read_skill",
        "ebay_validate_titles",
        "ebay_get_sales_history",
    } <= tools
    assert len(tools) == 13
    assert not any("recall" in name or "selection" in name for name in tools)
    assert len(server.mcp._resource_manager._resources) == 7


@pytest.mark.asyncio
async def test_reserved_sales_tool_fails_closed_without_provider():
    result = await server.ebay_get_sales_history("phone case")
    assert result["success"] is False
    assert result["error"]["code"] == "SALES_PROVIDER_NOT_CONFIGURED"


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
    assert result["data"]["skill"]["uri"] == (
        "skill://ebay-title-generation/SKILL.md"
    )
    assert "exactly 30" in result["data"]["content"]


@pytest.mark.asyncio
async def test_title_validator_tool_uses_local_contract():
    titles = [f"Wireless Earbuds Bluetooth Series {index}" for index in range(30)]
    result = await server.ebay_validate_titles(titles)
    assert result["success"] is True
    assert result["data"]["valid_for_delivery"] is True

