"""Shared response contracts and eBay marketplace metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Marketplace:
    marketplace_id: str
    country: str
    postal_code: str


MARKETPLACES: dict[str, Marketplace] = {
    "EBAY_US": Marketplace("EBAY_US", "US", "10001"),
    "EBAY_GB": Marketplace("EBAY_GB", "GB", "SW1A1AA"),
    "EBAY_DE": Marketplace("EBAY_DE", "DE", "10115"),
    "EBAY_AU": Marketplace("EBAY_AU", "AU", "2000"),
    "EBAY_FR": Marketplace("EBAY_FR", "FR", "75001"),
    "EBAY_ES": Marketplace("EBAY_ES", "ES", "28001"),
    "EBAY_IT": Marketplace("EBAY_IT", "IT", "00118"),
    "EBAY_CA": Marketplace("EBAY_CA", "CA", "M5V3L9"),
    "EBAY_HK": Marketplace("EBAY_HK", "HK", "999077"),
}


def require_marketplace(marketplace_id: str) -> Marketplace:
    key = (marketplace_id or "").strip().upper()
    try:
        return MARKETPLACES[key]
    except KeyError as exc:
        from ebay_mcp_server.errors import EbayMcpError

        raise EbayMcpError(
            "INVALID_MARKETPLACE",
            f"Unsupported marketplace_id: {marketplace_id}",
            details={"supported": sorted(MARKETPLACES)},
        ) from exc


def success(
    operation: str,
    source: str,
    data: Any,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        **(meta or {}),
    }
    return {
        "success": True,
        "operation": operation,
        "source": source,
        "data": data,
        "meta": metadata,
    }


def marketplace_catalog() -> list[dict[str, str]]:
    return [asdict(value) for value in MARKETPLACES.values()]

