from ebay_mcp_server.providers.sales import (
    DisabledSalesProvider,
    SalesHistoryProvider,
    build_sales_provider,
)

__all__ = [
    "DisabledSalesProvider",
    "PurchaseHistoryProvider",
    "SalesHistoryProvider",
    "build_sales_provider",
]


def __getattr__(name: str):
    if name == "PurchaseHistoryProvider":
        from ebay_mcp_server.providers.purchase_history import PurchaseHistoryProvider

        return PurchaseHistoryProvider
    raise AttributeError(name)
