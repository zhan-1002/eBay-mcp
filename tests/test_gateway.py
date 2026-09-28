import httpx
import pytest

from ebay_mcp_server.config import BASE_SCOPE, Settings
from ebay_mcp_server.contracts import require_marketplace
from ebay_mcp_server.gateway import EbayGateway


def settings() -> Settings:
    return Settings(
        environment="production",
        client_id="client-id",
        client_secret="client-secret",
        user_access_token="",
        request_timeout=5,
        max_retries=0,
        retry_base_delay=0,
        sales_provider="disabled",
    )


@pytest.mark.asyncio
async def test_oauth_token_is_cached_per_scope_and_never_returned_in_meta():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/identity/v1/oauth2/token"):
            return httpx.Response(
                200,
                json={"access_token": "secret-token", "expires_in": 7200},
            )
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB"
        return httpx.Response(
            200,
            headers={"x-ebay-c-request-id": "request-1"},
            json={"itemSummaries": []},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = EbayGateway(settings(), http=http)
    market = require_marketplace("EBAY_GB")

    first = await gateway.request(
        "GET",
        "/buy/browse/v1/item_summary/search",
        scopes=(BASE_SCOPE,),
        marketplace=market,
    )
    second = await gateway.request(
        "GET",
        "/buy/browse/v1/item_summary/search",
        scopes=(BASE_SCOPE,),
        marketplace=market,
    )

    assert len([c for c in calls if c.url.path.endswith("/token")]) == 1
    assert first.meta["request_id"] == "request-1"
    assert second.meta["request_id"] == "request-1"
    assert "secret-token" not in repr(first.meta)
    await http.aclose()


@pytest.mark.asyncio
async def test_upstream_error_is_structured():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/identity/v1/oauth2/token"):
            return httpx.Response(
                200,
                json={"access_token": "token", "expires_in": 7200},
            )
        return httpx.Response(429, json={"errors": [{"errorId": 1001}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = EbayGateway(settings(), http=http)

    with pytest.raises(Exception) as caught:
        await gateway.request("GET", "/test")
    error = caught.value
    assert error.code == "RATE_LIMITED"
    assert error.status_code == 429
    assert error.retryable is True
    await http.aclose()

