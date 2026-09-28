import pytest

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.providers.sales import DisabledSalesProvider, build_sales_provider


def settings(provider: str = "disabled") -> Settings:
    return Settings(
        environment="production",
        client_id="",
        client_secret="",
        user_access_token="",
        request_timeout=30,
        max_retries=2,
        retry_base_delay=0,
        sales_provider=provider,
    )


@pytest.mark.asyncio
async def test_base_package_has_no_scraper_implementation():
    provider = build_sales_provider(settings())
    assert isinstance(provider, DisabledSalesProvider)
    status = await provider.status()
    assert status["available"] is False
    assert status["implementation_bundled"] is False


@pytest.mark.asyncio
async def test_disabled_provider_returns_explicit_error():
    provider = DisabledSalesProvider()
    with pytest.raises(EbayMcpError) as caught:
        await provider.search(
            "phone case",
            "EBAY_US",
            limit=20,
            cursor=None,
        )
    assert caught.value.code == "SALES_PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_unknown_provider_fails_closed():
    provider = build_sales_provider(settings("future-private-provider"))
    status = await provider.status()
    assert status["available"] is False
    assert "Unknown EBAY_SALES_PROVIDER" in status["reason"]

