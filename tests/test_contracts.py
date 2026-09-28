import pytest

from ebay_mcp_server.contracts import MARKETPLACES, require_marketplace, success
from ebay_mcp_server.errors import EbayMcpError


def test_marketplace_lookup_is_case_insensitive():
    marketplace = require_marketplace("ebay_gb")
    assert marketplace.marketplace_id == "EBAY_GB"
    assert marketplace.country == "GB"
    assert marketplace.postal_code == "SW1A1AA"


def test_unknown_marketplace_has_stable_error():
    with pytest.raises(EbayMcpError) as caught:
        require_marketplace("EBAY_NOWHERE")
    assert caught.value.code == "INVALID_MARKETPLACE"
    assert "EBAY_US" in caught.value.details["supported"]


def test_success_envelope_keeps_data_and_provenance():
    result = success(
        "search_items",
        "ebay.buy.browse",
        {"itemSummaries": []},
        meta={"request_id": "abc"},
    )
    assert result["success"] is True
    assert result["data"] == {"itemSummaries": []}
    assert result["meta"]["request_id"] == "abc"
    assert result["meta"]["retrieved_at"].endswith("+00:00")


def test_supported_marketplaces_are_explicit():
    assert {"EBAY_US", "EBAY_GB", "EBAY_DE"} <= set(MARKETPLACES)

