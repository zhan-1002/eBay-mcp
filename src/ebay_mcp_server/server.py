"""FastMCP entry point for the general-purpose eBay capability server."""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import logging
import sys
from typing import Any, Awaitable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ebay_mcp_server.clients import OfficialEbayClient
from ebay_mcp_server.config import Settings
from ebay_mcp_server.contracts import (
    marketplace_catalog,
    require_marketplace,
    success,
)
from ebay_mcp_server.errors import EbayMcpError, tool_error
from ebay_mcp_server.gateway import ApiResponse, EbayGateway
from ebay_mcp_server.providers import build_sales_provider
from ebay_mcp_server.skill_registry import SkillRegistry
from ebay_mcp_server.title_validation import validate_titles


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("ebay_mcp")

settings = Settings.load()
gateway = EbayGateway(settings)
official = OfficialEbayClient(gateway)
sales_provider = build_sales_provider(settings)
skill_registry = SkillRegistry()


@asynccontextmanager
async def lifespan(_server):
    try:
        yield {}
    finally:
        await sales_provider.close()
        await gateway.close()


mcp = FastMCP("ebay", lifespan=lifespan)

READ_ONLY_LOCAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
READ_ONLY_NETWORK = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _register_skill_resources() -> None:
    """Register packaged Skill files as deterministic MCP resources."""

    def make_reader(uri: str):
        async def read_skill_resource() -> str:
            text, _mime_type = skill_registry.read(uri)
            return text

        safe_name = uri.removeprefix("skill://").replace("/", "_").replace("-", "_")
        read_skill_resource.__name__ = f"read_{safe_name}"
        return read_skill_resource

    for entry in skill_registry.list():
        for resource in entry.resources:
            mcp.resource(
                resource.uri,
                name=f"{entry.name}:{resource.uri.rsplit('/', 1)[-1]}",
                title=str(entry.frontmatter.get("name") or entry.name),
                description=str(entry.frontmatter.get("description") or ""),
                mime_type=resource.mime_type,
            )(make_reader(resource.uri))


_register_skill_resources()


async def _official_result(
    operation: str,
    source: str,
    request: Awaitable[ApiResponse],
) -> dict[str, Any]:
    try:
        response = await request
        return success(operation, source, response.data, meta=response.meta)
    except EbayMcpError as exc:
        return tool_error(operation, exc)
    except Exception as exc:  # pragma: no cover - final MCP safety boundary
        logger.exception("Unhandled error in %s", operation)
        return tool_error(
            operation,
            EbayMcpError(
                "INTERNAL_ERROR",
                f"Unhandled server error: {type(exc).__name__}",
            ),
        )


@mcp.tool(annotations=READ_ONLY_LOCAL)
async def ebay_get_capabilities() -> dict[str, Any]:
    """Inspect server configuration and supported eBay capabilities.

    Use this before calling tools when authentication, marketplace support, or
    the optional sales-history provider is uncertain. No network request is
    made and no credential value is returned.
    """
    provider = await sales_provider.status()
    return success(
        "get_capabilities",
        "server",
        {
            "configuration": settings.public_status(),
            "marketplaces": marketplace_catalog(),
            "official_domains": [
                "buy.browse",
                "commerce.taxonomy",
                "commerce.feedback",
                "commerce.translation",
                "developer.analytics",
            ],
            "sales_history_provider": provider,
            "skills": [
                {
                    "name": entry.name,
                    "description": entry.frontmatter["description"],
                    "uri": entry.uri,
                }
                for entry in skill_registry.list()
            ],
            "write_tools_enabled": False,
        },
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_search_items(
    query: str,
    marketplace_id: str = "EBAY_US",
    limit: int = 50,
    offset: int = 0,
    category_ids: str | None = None,
    filter_expression: str | None = None,
    sort: str | None = None,
    fieldgroups: str | None = None,
    aspect_filter: str | None = None,
) -> dict[str, Any]:
    """Search active eBay listings through the official Browse API.

    This tool only retrieves and paginates eBay results. It does not score,
    select, recommend, expand keywords, or estimate sales. ``offset`` must be
    zero or a multiple of ``limit``; eBay caps ``limit`` at 200.
    """
    try:
        marketplace = require_marketplace(marketplace_id)
    except EbayMcpError as exc:
        return tool_error("search_items", exc)
    return await _official_result(
        "search_items",
        "ebay.buy.browse",
        official.search_items(
            query,
            marketplace,
            limit=limit,
            offset=offset,
            category_ids=category_ids,
            filter_expression=filter_expression,
            sort=sort,
            fieldgroups=fieldgroups,
            aspect_filter=aspect_filter,
        ),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_get_item(
    item_id: str,
    marketplace_id: str = "EBAY_US",
    fieldgroups: str | None = None,
) -> dict[str, Any]:
    """Get one active listing from the official Browse API by REST item ID."""
    try:
        marketplace = require_marketplace(marketplace_id)
    except EbayMcpError as exc:
        return tool_error("get_item", exc)
    return await _official_result(
        "get_item",
        "ebay.buy.browse",
        official.get_item(item_id, marketplace, fieldgroups=fieldgroups),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_get_default_category_tree(
    marketplace_id: str = "EBAY_US",
) -> dict[str, Any]:
    """Get the official default taxonomy tree ID for an eBay marketplace."""
    try:
        marketplace = require_marketplace(marketplace_id)
    except EbayMcpError as exc:
        return tool_error("get_default_category_tree", exc)
    return await _official_result(
        "get_default_category_tree",
        "ebay.commerce.taxonomy",
        official.default_category_tree(marketplace),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_suggest_categories(
    query: str,
    marketplace_id: str = "EBAY_US",
    category_tree_id: str | None = None,
) -> dict[str, Any]:
    """Return official eBay category suggestions for a text query."""
    try:
        marketplace = require_marketplace(marketplace_id)
    except EbayMcpError as exc:
        return tool_error("suggest_categories", exc)
    return await _official_result(
        "suggest_categories",
        "ebay.commerce.taxonomy",
        official.category_suggestions(
            query,
            marketplace,
            category_tree_id=category_tree_id,
        ),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_get_category_aspects(
    category_id: str,
    marketplace_id: str = "EBAY_US",
    category_tree_id: str | None = None,
) -> dict[str, Any]:
    """Get required, recommended, and optional item aspects for a category."""
    try:
        marketplace = require_marketplace(marketplace_id)
    except EbayMcpError as exc:
        return tool_error("get_category_aspects", exc)
    return await _official_result(
        "get_category_aspects",
        "ebay.commerce.taxonomy",
        official.category_aspects(
            category_id,
            marketplace,
            category_tree_id=category_tree_id,
        ),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_get_seller_feedback(
    user_id: str,
    feedback_type: str = "FEEDBACK_RECEIVED",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Get official eBay feedback records for a public seller identifier.

    Feedback represents orders that received feedback; it is not complete
    sales history and must not be labeled as absolute sales volume.
    """
    return await _official_result(
        "get_seller_feedback",
        "ebay.commerce.feedback",
        official.seller_feedback(
            user_id,
            feedback_type=feedback_type,
            limit=limit,
            offset=offset,
        ),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_translate_text(
    text: str,
    source_language: str,
    target_language: str,
    context: str = "ITEM_TITLE",
) -> dict[str, Any]:
    """Translate one text segment with the official eBay Translation API."""
    return await _official_result(
        "translate_text",
        "ebay.commerce.translation",
        official.translate(
            text,
            source_language,
            target_language,
            context=context,
        ),
    )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_get_rate_limits() -> dict[str, Any]:
    """Return the calling application's official eBay API rate-limit table."""
    return await _official_result(
        "get_rate_limits",
        "ebay.developer.analytics",
        official.rate_limits(),
    )


@mcp.tool(annotations=READ_ONLY_LOCAL)
async def ebay_sales_provider_status() -> dict[str, Any]:
    """Inspect the optional sales-history provider without performing a scrape."""
    return success(
        "sales_provider_status",
        "sales-provider",
        await sales_provider.status(),
    )


@mcp.tool(annotations=READ_ONLY_LOCAL)
async def ebay_read_skill(skill_name: str) -> dict[str, Any]:
    """Read one packaged eBay Agent Skill by name.

    This is the compatibility bridge for MCP clients such as WorkBuddy 1.2.3
    that do not yet discover ``skill://`` resources or the Skills extension.
    The canonical content remains the MCP resource.
    """
    try:
        entry = skill_registry.get(skill_name)
        text, mime_type = skill_registry.read(entry.uri)
        return success(
            "read_skill",
            "skill-resource",
            {
                "skill": entry.as_dict(),
                "mime_type": mime_type,
                "content": text,
            },
        )
    except EbayMcpError as exc:
        return tool_error("read_skill", exc)


@mcp.tool(annotations=READ_ONLY_LOCAL)
async def ebay_validate_titles(
    titles: list[str],
    forbidden_terms: list[str] | None = None,
    expected_count: int = 30,
    max_length: int = 80,
    recommended_min_length: int = 70,
) -> dict[str, Any]:
    """Mechanically validate English eBay title candidates.

    Checks exact count, length, punctuation, repeated words, duplicate titles
    and caller-supplied forbidden brands or model identifiers. It does not make
    semantic brand or factual-product judgments.
    """
    result = validate_titles(
        titles,
        forbidden_terms=forbidden_terms or [],
        expected_count=expected_count,
        max_length=max_length,
        recommended_min_length=recommended_min_length,
    )
    return success("validate_titles", "local-validator", result)


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def ebay_get_sales_history(
    query: str,
    marketplace_id: str = "EBAY_US",
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Reserved interface for an optional non-public sales-history provider.

    The base package intentionally ships no scraper. Until a separately
    reviewed provider is installed and configured, this tool returns
    ``SALES_PROVIDER_NOT_CONFIGURED``.
    """
    try:
        require_marketplace(marketplace_id)
        data = await sales_provider.search(
            query,
            marketplace_id.upper(),
            limit=max(1, min(int(limit), 200)),
            cursor=cursor,
        )
        return success("get_sales_history", sales_provider.name, data)
    except EbayMcpError as exc:
        return tool_error("get_sales_history", exc)
    except Exception as exc:  # pragma: no cover - provider safety boundary
        logger.exception("Unhandled sales provider error")
        return tool_error(
            "get_sales_history",
            EbayMcpError(
                "SALES_PROVIDER_ERROR",
                f"Sales provider failed: {type(exc).__name__}",
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="General-purpose eBay MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport; WorkBuddy currently uses stdio.",
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

