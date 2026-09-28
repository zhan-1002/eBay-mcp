"""Thin, business-neutral wrappers for supported official eBay APIs."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ebay_mcp_server.config import BASE_SCOPE, FEEDBACK_SCOPE
from ebay_mcp_server.contracts import Marketplace
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.gateway import ApiResponse, EbayGateway


class OfficialEbayClient:
    def __init__(self, gateway: EbayGateway):
        self.gateway = gateway

    async def search_items(
        self,
        query: str,
        marketplace: Marketplace,
        *,
        limit: int = 50,
        offset: int = 0,
        category_ids: str | None = None,
        filter_expression: str | None = None,
        sort: str | None = None,
        fieldgroups: str | None = None,
        aspect_filter: str | None = None,
    ) -> ApiResponse:
        query = (query or "").strip()
        if not query:
            raise EbayMcpError("INVALID_ARGUMENT", "query must not be empty.")
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        if offset % limit != 0:
            raise EbayMcpError(
                "INVALID_PAGINATION",
                "offset must be zero or a multiple of limit for Browse search.",
                details={"offset": offset, "limit": limit},
            )
        params: dict[str, Any] = {"q": query, "limit": limit, "offset": offset}
        optional = {
            "category_ids": category_ids,
            "filter": filter_expression,
            "sort": sort,
            "fieldgroups": fieldgroups,
            "aspect_filter": aspect_filter,
        }
        params.update({key: value for key, value in optional.items() if value})
        return await self.gateway.request(
            "GET",
            "/buy/browse/v1/item_summary/search",
            marketplace=marketplace,
            params=params,
        )

    async def get_item(
        self,
        item_id: str,
        marketplace: Marketplace,
        *,
        fieldgroups: str | None = None,
    ) -> ApiResponse:
        item_id = (item_id or "").strip()
        if not item_id:
            raise EbayMcpError("INVALID_ARGUMENT", "item_id must not be empty.")
        params = {"fieldgroups": fieldgroups} if fieldgroups else None
        return await self.gateway.request(
            "GET",
            f"/buy/browse/v1/item/{quote(item_id, safe='')}",
            marketplace=marketplace,
            params=params,
        )

    async def default_category_tree(
        self, marketplace: Marketplace
    ) -> ApiResponse:
        return await self.gateway.request(
            "GET",
            "/commerce/taxonomy/v1/get_default_category_tree_id",
            marketplace=marketplace,
            params={"marketplace_id": marketplace.marketplace_id},
        )

    async def category_suggestions(
        self,
        query: str,
        marketplace: Marketplace,
        *,
        category_tree_id: str | None = None,
    ) -> ApiResponse:
        query = (query or "").strip()
        if not query:
            raise EbayMcpError("INVALID_ARGUMENT", "query must not be empty.")
        tree_id = (category_tree_id or "").strip()
        if not tree_id:
            tree = await self.default_category_tree(marketplace)
            tree_id = str(tree.data.get("categoryTreeId") or "")
        if not tree_id:
            raise EbayMcpError(
                "INVALID_UPSTREAM_RESPONSE",
                "eBay did not return a category tree ID.",
            )
        return await self.gateway.request(
            "GET",
            f"/commerce/taxonomy/v1/category_tree/{quote(tree_id, safe='')}/"
            "get_category_suggestions",
            marketplace=marketplace,
            params={"q": query},
        )

    async def category_aspects(
        self,
        category_id: str,
        marketplace: Marketplace,
        *,
        category_tree_id: str | None = None,
    ) -> ApiResponse:
        category_id = (category_id or "").strip()
        if not category_id:
            raise EbayMcpError(
                "INVALID_ARGUMENT", "category_id must not be empty."
            )
        tree_id = (category_tree_id or "").strip()
        if not tree_id:
            tree = await self.default_category_tree(marketplace)
            tree_id = str(tree.data.get("categoryTreeId") or "")
        return await self.gateway.request(
            "GET",
            f"/commerce/taxonomy/v1/category_tree/{quote(tree_id, safe='')}/"
            "get_item_aspects_for_category",
            marketplace=marketplace,
            params={"category_id": category_id},
        )

    async def seller_feedback(
        self,
        user_id: str,
        *,
        feedback_type: str = "FEEDBACK_RECEIVED",
        limit: int = 50,
        offset: int = 0,
    ) -> ApiResponse:
        user_id = (user_id or "").strip()
        feedback_type = (feedback_type or "").strip().upper()
        if not user_id:
            raise EbayMcpError("INVALID_ARGUMENT", "user_id must not be empty.")
        if feedback_type not in {"FEEDBACK_RECEIVED", "FEEDBACK_SENT"}:
            raise EbayMcpError(
                "INVALID_ARGUMENT",
                "feedback_type must be FEEDBACK_RECEIVED or FEEDBACK_SENT.",
            )
        return await self.gateway.request(
            "GET",
            "/commerce/feedback/v1/feedback",
            scopes=(FEEDBACK_SCOPE,),
            params={
                "user_id": user_id,
                "feedback_type": feedback_type,
                "limit": max(1, min(int(limit), 200)),
                "offset": max(0, int(offset)),
            },
        )

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        context: str = "ITEM_TITLE",
    ) -> ApiResponse:
        text = (text or "").strip()
        if not text:
            raise EbayMcpError("INVALID_ARGUMENT", "text must not be empty.")
        return await self.gateway.request(
            "POST",
            "/commerce/translation/v1_beta/translate",
            json_body={
                "from": source_language.strip().lower(),
                "to": target_language.strip().lower(),
                "text": [text],
                "translationContext": context.strip().upper(),
            },
        )

    async def rate_limits(self) -> ApiResponse:
        return await self.gateway.request(
            "GET",
            "/developer/analytics/v1_beta/rate_limit/",
        )

