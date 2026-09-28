import pytest

from ebay_mcp_server.clients.official import OfficialEbayClient
from ebay_mcp_server.contracts import require_marketplace
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.gateway import ApiResponse


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path.endswith("get_default_category_tree_id"):
            return ApiResponse({"categoryTreeId": "0"}, {"request_id": "tree"})
        return ApiResponse({"ok": True}, {"request_id": "test"})


@pytest.mark.asyncio
async def test_search_passes_marketplace_and_query_without_business_scoring():
    gateway = FakeGateway()
    client = OfficialEbayClient(gateway)
    market = require_marketplace("EBAY_US")

    response = await client.search_items(
        "phone case",
        market,
        limit=100,
        offset=200,
        filter_expression="buyingOptions:{FIXED_PRICE}",
    )

    assert response.data == {"ok": True}
    method, path, kwargs = gateway.calls[0]
    assert method == "GET"
    assert path == "/buy/browse/v1/item_summary/search"
    assert kwargs["marketplace"] == market
    assert kwargs["params"]["q"] == "phone case"
    assert kwargs["params"]["offset"] == 200
    assert "score" not in kwargs["params"]


@pytest.mark.asyncio
async def test_search_rejects_invalid_ebay_pagination():
    client = OfficialEbayClient(FakeGateway())
    with pytest.raises(EbayMcpError) as caught:
        await client.search_items(
            "phone case",
            require_marketplace("EBAY_US"),
            limit=100,
            offset=50,
        )
    assert caught.value.code == "INVALID_PAGINATION"


@pytest.mark.asyncio
async def test_category_suggestions_resolve_default_tree():
    gateway = FakeGateway()
    client = OfficialEbayClient(gateway)
    await client.category_suggestions(
        "wireless headphones",
        require_marketplace("EBAY_GB"),
    )
    assert len(gateway.calls) == 2
    assert gateway.calls[0][1].endswith("get_default_category_tree_id")
    assert "/category_tree/0/get_category_suggestions" in gateway.calls[1][1]


@pytest.mark.asyncio
async def test_feedback_uses_dedicated_application_scope():
    gateway = FakeGateway()
    client = OfficialEbayClient(gateway)
    await client.seller_feedback("seller-name")
    _, path, kwargs = gateway.calls[0]
    assert path == "/commerce/feedback/v1/feedback"
    assert kwargs["scopes"] == (
        "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly",
    )

