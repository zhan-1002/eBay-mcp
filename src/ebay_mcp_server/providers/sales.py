"""Pluggable purchase-history providers used by the MCP sales tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError


class SalesHistoryProvider(ABC):
    name: str

    async def open_login(
        self, marketplace_id: str, item_id: str | None = None
    ) -> dict[str, Any]:
        del item_id
        raise EbayMcpError(
            "SALES_LOGIN_UNSUPPORTED",
            f"The {self.name} provider does not manage a browser login.",
        )

    @abstractmethod
    async def status(self) -> dict[str, Any]:
        """Return configuration and availability without exposing credentials."""

    @abstractmethod
    async def search(
        self,
        item_ids: list[str],
        marketplace_id: str,
        *,
        limit: int,
        allow_window: bool = False,
    ) -> dict[str, Any]:
        """Return recent purchase observations for numeric legacy item IDs."""

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
        item_ids: list[str],
        marketplace_id: str,
        *,
        limit: int,
        allow_window: bool = False,
    ) -> dict[str, Any]:
        del allow_window
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
    if settings.sales_provider in {
        "purchase_history",
        "purchase-history",
        "ebay-purchase-history",
    }:
        from ebay_mcp_server.providers.purchase_history import PurchaseHistoryProvider

        return PurchaseHistoryProvider(settings)
    return DisabledSalesProvider(
        f"Unknown EBAY_SALES_PROVIDER={settings.sales_provider!r}. "
        "Install and register a provider implementation before enabling it."
    )
