"""Pluggable boundary for purchase-history data sources.

The base package does not include a collector yet. A future provider stays
behind this contract so official API tools remain stable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError


class SalesHistoryProvider(ABC):
    name: str

    @abstractmethod
    async def status(self) -> dict[str, Any]:
        """Return configuration and availability without exposing credentials."""

    @abstractmethod
    async def search(
        self,
        query: str,
        marketplace_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        """Return provider-native sales observations in a normalized envelope."""

    async def close(self) -> None:
        return None


class DisabledSalesProvider(SalesHistoryProvider):
    name = "disabled"

    def __init__(self, reason: str = "No sales-history provider is configured."):
        self.reason = reason

    async def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": False,
            "reason": self.reason,
            "implementation_bundled": False,
        }

    async def search(
        self,
        query: str,
        marketplace_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        raise EbayMcpError(
            "SALES_PROVIDER_NOT_CONFIGURED",
            self.reason,
            details={
                "provider_contract": "ebay_mcp_server.providers.sales.SalesHistoryProvider",
                "requested_marketplace": marketplace_id,
            },
        )


def build_sales_provider(settings: Settings) -> SalesHistoryProvider:
    if settings.sales_provider in {"", "disabled", "none"}:
        return DisabledSalesProvider()
    return DisabledSalesProvider(
        f"Unknown EBAY_SALES_PROVIDER={settings.sales_provider!r}. "
        "Install and register a provider implementation before enabling it."
    )

