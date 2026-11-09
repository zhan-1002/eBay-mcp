"""FastMCP entry point for the general-purpose eBay capability server."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

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
from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser
from ebay_mcp_server.providers.soldeazy_pricing import (
    DatasheetRow,
    load_targets,
    plan_price_changes,
    plan_stock_changes,
    rows_from_matrix,
)
from ebay_mcp_server.providers.soldeazy_plan import PlanError
from ebay_mcp_server.providers.soldeazy_write import WriteRegistry, check_drift, rows_to_state
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
soldeazy = SoldeazyBrowser(settings)
write_registry = WriteRegistry()
skill_registry = SkillRegistry()


@asynccontextmanager
async def lifespan(_server):
    try:
        yield {}
    finally:
        await soldeazy.close()
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
LOCAL_SESSION_ACTION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
REMOTE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
LOCAL_FILE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
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
    sales-history provider state is uncertain. No network request is
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
    """Get one active listing from the official Browse API by REST item ID.

    ``estimatedSoldQuantity`` in this response is an official aggregate
    estimate. It is not the sales detail. Collected sales are the
    purchase-history transaction rows from ``ebay_get_sales_history``.
    """
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
    """Inspect the sales-history provider and its persistent browser session."""
    return success(
        "sales_provider_status",
        "sales-provider",
        await sales_provider.status(),
    )


@mcp.tool(annotations=LOCAL_SESSION_ACTION)
async def ebay_sales_open_login(
    marketplace_id: str = "EBAY_GB",
    item_id: str | None = None,
) -> dict[str, Any]:
    """Show the purchase-history browser window after the user has agreed.

    Do not call this until the user explicitly allows the window to appear.
    After sign-in the same window stays open and minimized. Pass ``item_id``
    to park it on that listing's purchase-history page. Do not close it.
    """
    try:
        require_marketplace(marketplace_id)
        data = await sales_provider.open_login(
            marketplace_id.upper(), item_id=item_id
        )
        return success("sales_open_login", sales_provider.name, data)
    except EbayMcpError as exc:
        return tool_error("sales_open_login", exc)
    except Exception as exc:  # pragma: no cover - provider safety boundary
        logger.exception("Unhandled sales login error")
        return tool_error(
            "sales_open_login",
            EbayMcpError(
                "SALES_LOGIN_ERROR",
                f"Sales login failed: {type(exc).__name__}",
            ),
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
    item_ids: list[str],
    marketplace_id: str = "EBAY_GB",
    limit_per_item: int = 100,
    allow_browser_window: bool = False,
) -> dict[str, Any]:
    """Collect purchase-history transaction rows for legacy item IDs.

    The sales data is ``items[].transactions``: each visible purchase with
    price, quantity, time and variation. ``visible_quantity`` only sums those
    rows. Do not substitute Browse API ``estimatedSoldQuantity``.

    ``item_ids`` must contain traditional numeric eBay listing IDs, not REST
    IDs such as ``v1|123456789012|0``. The call first checks the parked
    browser. The window stays minimized. A detected eBay check waits silently
    for a verification component and does not by itself show the window. Set
    ``allow_browser_window`` only after the user agrees.
    """
    try:
        require_marketplace(marketplace_id)
        data = await sales_provider.search(
            item_ids,
            marketplace_id.upper(),
            limit=max(1, min(int(limit_per_item), 100)),
            allow_window=bool(allow_browser_window),
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


def _search_text(skus: list[str] | None, raw: str) -> str:
    """Build the space-joined wildcard query the Soldeazy search box expects."""

    if raw.strip():
        return raw.strip()
    terms: list[str] = []
    for sku in skus or []:
        core = str(sku).strip()
        if core:
            terms.append(core if core.startswith("*") else f"*{core}")
    return " ".join(terms)


def _to_rows(records: list[dict[str, Any]], *, first_row: int = 3) -> list[DatasheetRow]:
    rows: list[DatasheetRow] = []
    for offset, record in enumerate(records):
        rows.append(
            DatasheetRow(
                row=first_row + offset,
                rowid=str(record.get("rowid") or "").strip(),
                parent_sku="",
                sku=str(record.get("sku") or "").strip(),
                qty=float(record.get("qty") or 0),
                price=float(record.get("price") or 0),
                postage=record.get("postage"),
            )
        )
    return rows


@mcp.tool(annotations=READ_ONLY_LOCAL)
async def soldeazy_status() -> dict[str, Any]:
    """Report the Soldeazy browser profile, credentials and write-tool state.

    Use this before any Soldeazy call: it says whether a profile exists, whether
    credentials are configured, and whether the write tools are enabled.
    """
    try:
        return success("soldeazy_status", "soldeazy", await soldeazy.status())
    except EbayMcpError as exc:
        return tool_error("soldeazy_status", exc)


@mcp.tool(annotations=LOCAL_SESSION_ACTION)
async def soldeazy_open_login() -> dict[str, Any]:
    """Open the Soldeazy sign-in page in the persistent profile.

    With ``SOLDEAZY_USERNAME``/``SOLDEAZY_PASSWORD`` the form is filled and
    submitted; otherwise the window stays open for a manual sign-in. The browser
    is kept open for later calls until the server stops.
    """
    try:
        return success("soldeazy_open_login", "soldeazy", await soldeazy.interactive_login())
    except EbayMcpError as exc:
        return tool_error("soldeazy_open_login", exc)


def _cap_rows(
    rows: list[dict[str, Any]], *, limit: int = 50, offset: int = 0, with_title: bool = False
) -> dict[str, Any]:
    """把行列表裁成安全的一页。

    生产账号一次搜索可能几千行，全量回传会在对话里吃掉几十万 token。
    这里统一限流：默认 50 条、最多 200 条，标题默认不带。
    """

    page_size = max(1, min(int(limit or 50), 200))
    start = max(0, int(offset or 0))
    window = rows[start : start + page_size]
    if not with_title:
        window = [{k: v for k, v in row.items() if k != "title"} for row in window]
    return {
        "rows": window,
        "total": len(rows),
        "offset": start,
        "limit": page_size,
        "truncated": start + page_size < len(rows),
        "has_more": start + page_size < len(rows),
    }


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def soldeazy_search_datasheet(
    site: str,
    skus: list[str] | None = None,
    search_text: str = "",
    limit: int = 50,
    offset: int = 0,
    with_title: bool = False,
) -> dict[str, Any]:
    """Read datasheet rows (Row ID, SKU, price, postage, qty) for one site.

    ``skus`` are product codes; each becomes a ``*CODE`` wildcard so the bare
    SKU and its ``US``/``x2``/``x4`` variants come back in one query. Pass
    ``search_text`` to use the box verbatim instead.

    **返回条数默认上限 50 条**（``limit``，最多 200）。生产账号一次可能几千条，
    全量返回会在对话里吃掉几十万 token；确实需要全量时用 ``offset`` 翻页。
    ``with_title`` 默认关闭——标题是单行最占字的部分。
    """
    # 空查询是合法的：等于「这个渠道账号 + 站点下的全部数据表」，
    # 计划预览内部就是这么读的，工具层不该比它还严。
    query = _search_text(skus, search_text)
    if not site:
        return tool_error(
            "soldeazy_search_datasheet",
            EbayMcpError("SOLDEAZY_SITE_REQUIRED", "必须给出 site（US/UK/DE…）。"),
        )
    try:
        data = await soldeazy.search(query, site)
        rows = data.get("rows") or []
        return success(
            "soldeazy_search_datasheet",
            "soldeazy",
            {
                **{k: v for k, v in data.items() if k != "rows"},
                **_cap_rows(rows, limit=limit, offset=offset, with_title=with_title),
            },
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_search_datasheet", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy search error")
        return tool_error(
            "soldeazy_search_datasheet",
            EbayMcpError("SOLDEAZY_SEARCH_ERROR", f"搜索失败: {type(exc).__name__}"),
        )


async def _collect_site_rows(
    site: str, query: str
) -> tuple[dict[str, Any], list[Any], Path]:
    """搜索 → 导出 → 读成数据表行。

    行号取自导出文件本身，写回时可以直接按行号定位（与影刀同一份载体）。
    """

    from ebay_mcp_server.providers.soldeazy_workbook import read_matrix

    found = await soldeazy.search(query, site)
    workdir = Path(tempfile.mkdtemp(prefix="soldeazy-"))
    exported = workdir / f"export_{site}.xlsx"
    await soldeazy.export(exported)
    _sheet, matrix = read_matrix(exported)
    body = [
        [row[i] if i < len(row) else None for i in (0, 2, 3, 4, 5, 6)]
        for row in matrix[2:]
    ]
    return found, rows_from_matrix(body, first_row=3), exported


def _shop_scope(found: dict[str, Any]) -> list[str]:
    """搜索结果里出现的渠道账号集合（用于确认写回时还是同一批店铺）。"""

    names = {(row.get("shop") or "").strip() for row in found.get("rows") or []}
    return sorted(name for name in names if name)


def _manifest_path() -> str:
    configured = (settings.soldeazy_manifest_path or "").strip()
    if configured:
        return configured
    base = Path(settings.soldeazy_profile_dir or ".").expanduser().parent
    return str(base / "soldeazy-writes.jsonl")


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def soldeazy_preview_price_change(
    site: str,
    price_sheet: list[list[Any]],
    pack_policy: str = "multiply",
) -> dict[str, Any]:
    """Preview a price change and return a ``confirm_token``.

    ``price_sheet`` is the operator's ``(SKU, 价格更新)`` rows: the two-letter
    prefix selects the site, ``EF-``/``EF2-`` prefixes are stripped, and the
    price is the *minimum selling price* (price + postage). The plan is computed
    on the exported datasheet, so row numbers match the file that would be
    uploaded. Nothing is written; the token is required by the update tool.
    """
    if pack_policy not in {"same", "skip", "multiply"}:
        return tool_error(
            "soldeazy_preview_price_change",
            EbayMcpError("SOLDEAZY_PACK_POLICY", "pack_policy 只能是 same/skip/multiply。"),
        )
    try:
        targets = load_targets([(row[0], row[1]) for row in price_sheet])
        site_targets = targets.for_site(site)
        if not site_targets:
            raise EbayMcpError(
                "SOLDEAZY_NO_TARGETS",
                f"{site} 没有可用目标价。",
                details={"rejected": targets.rejected, "conflicts": targets.conflicts},
            )
        query = " ".join(f"*{key}" for key in sorted(site_targets))
        found, rows, exported = await _collect_site_rows(site, query)
        plan = plan_price_changes(rows, site_targets, pack_policy=pack_policy)  # type: ignore[arg-type]

        token = ""
        if plan.changes:
            token = write_registry.register(
                "price",
                site,
                query,
                [change.as_dict() for change in plan.changes],
                rows_to_state(found["rows"]),
                context={
                    "targets": site_targets,
                    "pack_policy": pack_policy,
                    "shop_scope": _shop_scope(found),
                    "active_shop": dict(soldeazy.active_shop or {}),
                },
            ).token

        return success(
            "soldeazy_preview_price_change",
            "soldeazy",
            {
                "site": site,
                "search": query,
                "datasheet_rows": len(rows),
                "exported": str(exported),
                "plan": plan.as_dict(),
                "confirm_token": token,
                "rejected_targets": targets.rejected,
                "target_conflicts": targets.conflicts,
            },
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_preview_price_change", exc)
    except RuntimeError as exc:
        return tool_error(
            "soldeazy_preview_price_change",
            EbayMcpError("SOLDEAZY_DEPENDENCY_MISSING", str(exc)),
        )
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy preview error")
        return tool_error(
            "soldeazy_preview_price_change",
            EbayMcpError("SOLDEAZY_PREVIEW_ERROR", f"预览失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def soldeazy_preview_stock_change(
    site: str,
    stock_sheet_path: str = "",
    stock: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Preview a stock change; the write itself goes through the same API chain.

    Two ways to supply the target quantities:

    * ``stock`` — ``{SKU: 数量}`` given straight from the caller (no file needed);
    * ``stock_sheet_path`` — the operator's ``库存更新.xlsx`` (SKU | 库存 | 备注).

    Either way the plan is computed on the exported datasheet and the write is an
    absolute quantity per row: no pack conversion, residue ignored.
    """
    try:
        from ebay_mcp_server.providers.soldeazy_stock import (
            StockSheet,
            read_stock_sheet,
        )

        if stock:
            entries: dict[str, float] = {}
            issues: list[str] = []
            for raw_sku, raw_qty in stock.items():
                sku = str(raw_sku).strip()
                if not sku:
                    issues.append("有空 SKU")
                    continue
                try:
                    qty = float(str(raw_qty).replace(",", "").strip())
                except (TypeError, ValueError):
                    issues.append(f"{sku}：数量 {raw_qty!r} 不是数字")
                    continue
                if qty < 0 or qty != int(qty):
                    issues.append(f"{sku}：数量 {qty:g} 必须是非负整数")
                    continue
                entries[sku] = qty
            sheet = StockSheet(entries=entries, issues=issues)
        elif stock_sheet_path:
            sheet = read_stock_sheet(stock_sheet_path)
        else:
            raise EbayMcpError(
                "SOLDEAZY_STOCK_SOURCE",
                "请给出 stock（{SKU: 数量}）或 stock_sheet_path。",
            )

        if sheet.issues:
            raise EbayMcpError(
                "SOLDEAZY_STOCK_SHEET_INVALID",
                "库存数据校验未通过，整份拒收",
                details={"issues": sheet.issues[:20]},
            )
        if not sheet.entries:
            raise EbayMcpError("SOLDEAZY_STOCK_SHEET_EMPTY", "没有可用的 SKU 行")

        catalog = sorted(sheet.entries)
        query = " ".join(f"*{sku}" for sku in catalog)
        found, rows, exported = await _collect_site_rows(site, query)
        plan = plan_stock_changes(rows, sheet.entries, catalog=catalog)

        token = ""
        if plan.changes:
            token = write_registry.register(
                "stock",
                site,
                query,
                [change.as_dict() for change in plan.changes],
                rows_to_state(found["rows"]),
                context={
                    "stock": sheet.entries,
                    "catalog": catalog,
                    "shop_scope": _shop_scope(found),
                    "active_shop": dict(soldeazy.active_shop or {}),
                },
            ).token

        return success(
            "soldeazy_preview_stock_change",
            "soldeazy",
            {
                "site": site,
                "search": query,
                "datasheet_rows": len(rows),
                "exported": str(exported),
                "stock_rows": len(catalog),
                "plan": plan.as_dict(),
                "confirm_token": token,
                "skipped_sheet_rows": sheet.skipped,
            },
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_preview_stock_change", exc)
    except RuntimeError as exc:  # 缺 openpyxl 等环境问题，给出可执行提示
        return tool_error(
            "soldeazy_preview_stock_change",
            EbayMcpError("SOLDEAZY_DEPENDENCY_MISSING", str(exc)),
        )
    except Exception as exc:  # pragma: no cover - browser/file safety boundary
        logger.exception("Unhandled Soldeazy stock preview error")
        return tool_error(
            "soldeazy_preview_stock_change",
            EbayMcpError("SOLDEAZY_STOCK_PREVIEW_ERROR", f"库存预览失败: {exc}"),
        )


async def _apply_write(kind: str, confirm_token: str, dry_run: bool) -> dict[str, Any]:
    """预览令牌 → 现场复核 → 改文件 → 自检 → 上传 → 同步 → 记账。"""

    from ebay_mcp_server.providers.soldeazy_workbook import build_upload_file
    from ebay_mcp_server.providers.soldeazy_write import append_manifest, same_plan

    if not settings.soldeazy_write_enabled:
        raise EbayMcpError(
            "SOLDEAZY_WRITE_DISABLED",
            "写工具未开启：确认只读链路验证通过后设置 SOLDEAZY_WRITE_ENABLED=1。",
        )

    plan = write_registry.consume(confirm_token)
    if plan is None:
        raise EbayMcpError(
            "SOLDEAZY_TOKEN_INVALID",
            "确认令牌无效或已过期，请重新预览。",
        )
    if plan.kind != kind:
        raise EbayMcpError(
            "SOLDEAZY_TOKEN_KIND",
            f"令牌是 {plan.kind} 预览发的，不能用来做 {kind}。",
        )

    # 账号守卫（先做纯内存比对，切过账号就不必再去搜索了）
    expected_shop = plan.context.get("active_shop") or {}
    current_shop = dict(soldeazy.active_shop or {})
    if expected_shop.get("id") and expected_shop.get("id") != current_shop.get("id"):
        raise EbayMcpError(
            "SOLDEAZY_SHOP_CHANGED",
            "活动渠道账号已切换，请重新预览后再写入",
            details={"expected": expected_shop, "now": current_shop},
        )

    found, rows, exported = await _collect_site_rows(plan.site, plan.query)

    # 搜索回来的账号若和预览时不一致，同样中止
    expected_scope = plan.context.get("shop_scope")
    if expected_scope is not None:
        now_scope = _shop_scope(found)
        if now_scope != expected_scope:
            raise EbayMcpError(
                "SOLDEAZY_SHOP_CHANGED",
                "当前搜索到的渠道账号与预览时不一致，已中止（未上传）",
                details={"expected": expected_scope, "now": now_scope},
            )

    drift = check_drift(plan.expected, rows_to_state(found["rows"]))
    if not drift.ok:
        raise EbayMcpError(
            "SOLDEAZY_DRIFT",
            "线上数据与预览时不一致，已中止（未上传）",
            details={"problems": drift.problems},
        )

    if kind == "price":
        recomputed = plan_price_changes(
            rows, plan.context["targets"], pack_policy=plan.context["pack_policy"]
        )
        field = "price"
        sync_kwargs = {"price_postage": True}
    else:
        recomputed = plan_stock_changes(
            rows, plan.context["stock"], catalog=plan.context.get("catalog")
        )
        field = "stock"
        sync_kwargs = {"price_postage": False, "quantity": True}

    reconciliation = same_plan(plan.changes, recomputed.changes)
    if not reconciliation.ok:
        raise EbayMcpError(
            "SOLDEAZY_PLAN_CHANGED",
            "重新算出来的改动与预览不一致，已中止（未上传）",
            details={"problems": reconciliation.problems},
        )
    if not recomputed.changes:
        raise EbayMcpError("SOLDEAZY_NOTHING_TO_DO", "重新核对后没有需要改的行。")

    summary = {
        "site": plan.site,
        "search": plan.query,
        "rows": len(recomputed.changes),
        "changes": [change.as_dict() for change in recomputed.changes],
        "exported": str(exported),
    }
    if dry_run:
        return {**summary, "dry_run": True, "uploaded": False}

    target = exported.with_name(f"{exported.stem}_done.xlsx")
    report = build_upload_file(
        exported, target, to_cell_changes(recomputed.changes, field)
    )
    # 走接口上传：与页面等价，但没有 UI 等待，失败信息更直接
    upload = await soldeazy.upload_via_api(target)
    # 上传后重新搜索，让 BULK SYNC 作用在刚传上去的那批行上
    await soldeazy.search(plan.query, plan.site)
    await soldeazy._ensure_rows_selected()  # noqa: SLF001 - 同步同样只作用于勾选行
    sync = await soldeazy.sync_up_via_api(**sync_kwargs)

    append_manifest(
        _manifest_path(),
        {
            "token": plan.token,
            "kind": kind,
            "site": plan.site,
            "search": plan.query,
            "uploaded": report["path"],
            "changed_columns": report["changed_columns"],
            "changes": report["changes"],
            "upload_handle": upload.get("handle"),
            "sync": sync,
        },
    )
    return {
        **summary,
        "dry_run": False,
        "uploaded": report["path"],
        "changed_columns": report["changed_columns"],
        "sync": sync,
    }


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_update_price(confirm_token: str, dry_run: bool = True) -> dict[str, Any]:
    """Apply a previewed price change to Soldeazy and sync it to eBay.

    Requires the ``confirm_token`` from ``soldeazy_preview_price_change`` and a
    server started with ``SOLDEAZY_WRITE_ENABLED=1``. ``dry_run`` defaults to
    true: it re-checks the live rows and returns the plan without uploading.
    """
    try:
        return success(
            "soldeazy_update_price", "soldeazy", await _apply_write("price", confirm_token, dry_run)
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_update_price", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy price write error")
        return tool_error(
            "soldeazy_update_price",
            EbayMcpError("SOLDEAZY_WRITE_ERROR", f"改价失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_update_stock(confirm_token: str, dry_run: bool = True) -> dict[str, Any]:
    """Apply a previewed stock change to Soldeazy and sync the quantity to eBay.

    Same guards as the price tool: write flag, one-shot token, live-row drift
    check, E/F-only upload, and a manifest line per applied write.
    """
    try:
        return success(
            "soldeazy_update_stock", "soldeazy", await _apply_write("stock", confirm_token, dry_run)
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_update_stock", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy stock write error")
        return tool_error(
            "soldeazy_update_stock",
            EbayMcpError("SOLDEAZY_WRITE_ERROR", f"改库存失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def soldeazy_list_shops(keyword: str = "") -> dict[str, Any]:
    """List the channel accounts (eBay shops) this login may operate.

    Returns each shop's id and short name; `keyword` filters by name. The list
    comes from the datasheet search form, which reflects the site's own
    authorisation rather than a guessed inventory.
    """
    try:
        shops = await soldeazy.list_shop_options()
        active = soldeazy.active_shop or {}
        if keyword:
            needle = keyword.strip().upper()
            shops = [s for s in shops if needle in s["name"].upper() or needle in s["id"]]
        return success(
            "soldeazy_list_shops",
            "soldeazy",
            {"count": len(shops), "active": active, "shops": shops},
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_list_shops", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy shop list error")
        return tool_error(
            "soldeazy_list_shops",
            EbayMcpError("SOLDEAZY_SHOPS_ERROR", f"读取渠道账号失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=LOCAL_SESSION_ACTION)
async def soldeazy_switch_shop(shop: str) -> dict[str, Any]:
    """Switch the active channel account for later calls.

    Accepts the short name (`FUN`) or the numeric id. After switching, search
    and preview tools default to this shop instead of asking again.
    """
    try:
        picked = await soldeazy.switch_shop(shop)
        return success("soldeazy_switch_shop", "soldeazy", {"active": picked})
    except EbayMcpError as exc:
        return tool_error("soldeazy_switch_shop", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy switch error")
        return tool_error(
            "soldeazy_switch_shop",
            EbayMcpError("SOLDEAZY_SWITCH_ERROR", f"切换渠道账号失败: {type(exc).__name__}"),
        )


def _require_write_enabled() -> None:
    if not settings.soldeazy_write_enabled:
        raise EbayMcpError(
            "SOLDEAZY_WRITE_DISABLED",
            "写工具未开启：确认只读链路验证通过后设置 SOLDEAZY_WRITE_ENABLED=1。",
        )


async def _resolve_shop_id(shop: str) -> dict[str, str]:
    """把渠道账号简称/id 解析成 {id, name}，空值回落到当前 active。"""

    if shop:
        return await soldeazy.switch_shop(shop)
    if soldeazy.active_shop:
        return soldeazy.active_shop
    raise EbayMcpError(
        "SOLDEAZY_SHOP_REQUIRED",
        "还没有选定渠道账号：先调用 soldeazy_switch_shop。",
    )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_change_price(
    site: str,
    targets: dict[str, float],
    shop: str = "",
    dry_run: bool = False,
    sync_price: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """**一步改价**：起草 → 冻结 → 执行 → 对账，只返回判决。

    这是推荐入口。旧的四个分步工具仍然可用，但每一步都要把明细推进对话，
    生产账号几千行时会把 token 烧光（实测累积到 6000 万）。
    这里服务端自己校验，只回 `ok` + 计数 + 问题列表（最多 10 条）。

    `targets` 是 `{子体SKU: 新价格}`，价格按给定值精确写入。
    `dry_run=True` 只出计划不写盘。
    """

    try:
        from ebay_mcp_server.providers.soldeazy_change import run_change
        from ebay_mcp_server.providers.soldeazy_apply import apply_plan, build_items, make_plan, reconcile
        from ebay_mcp_server.providers.soldeazy_plan import freeze, write_draft

        if not targets:
            raise EbayMcpError("SOLDEAZY_PLAN_EMPTY", "targets 不能为空。")
        if not dry_run:
            _require_write_enabled()

        data = await run_change(
            kind="price",
            site=site,
            targets=targets,
            shop=shop,
            dry_run=dry_run,
            sync=True,
            sync_price=sync_price,
            sync_quantity=False,
            verbose=verbose,
            deps={
                "build_items": build_items,
                "make_plan": make_plan,
                "write_draft": write_draft,
                "freeze": freeze,
                "apply_plan": apply_plan,
                "reconcile": reconcile,
                "plan_dir": _plan_dir(),
                "browser": soldeazy,
                "resolve_shop": _resolve_shop_id,
            },
        )
        return success("soldeazy_change_price", "soldeazy", data)
    except EbayMcpError as exc:
        return tool_error("soldeazy_change_price", exc)
    except Exception as exc:  # pragma: no cover
        logger.exception("Unhandled Soldeazy change_price error")
        return tool_error(
            "soldeazy_change_price",
            EbayMcpError("SOLDEAZY_CHANGE_ERROR", f"改价失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_change_stock(
    site: str,
    targets: dict[str, float],
    shop: str = "",
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """**一步改库存**：起草 → 冻结 → 执行 → 对账，只返回判决。

    `targets` 是 `{母体SKU: 数量}`，会写进该母体下的所有行
    （母体行 + 全部子体行），数量是绝对值。
    """

    try:
        from ebay_mcp_server.providers.soldeazy_change import run_change
        from ebay_mcp_server.providers.soldeazy_apply import apply_plan, build_items, make_plan, reconcile
        from ebay_mcp_server.providers.soldeazy_plan import freeze, write_draft

        if not targets:
            raise EbayMcpError("SOLDEAZY_PLAN_EMPTY", "targets 不能为空。")
        if not dry_run:
            _require_write_enabled()

        data = await run_change(
            kind="qty",
            site=site,
            targets=targets,
            shop=shop,
            dry_run=dry_run,
            sync=True,
            sync_price=False,
            sync_quantity=True,
            verbose=verbose,
            deps={
                "build_items": build_items,
                "make_plan": make_plan,
                "write_draft": write_draft,
                "freeze": freeze,
                "apply_plan": apply_plan,
                "reconcile": reconcile,
                "plan_dir": _plan_dir(),
                "browser": soldeazy,
                "resolve_shop": _resolve_shop_id,
            },
        )
        return success("soldeazy_change_stock", "soldeazy", data)
    except EbayMcpError as exc:
        return tool_error("soldeazy_change_stock", exc)
    except Exception as exc:  # pragma: no cover
        logger.exception("Unhandled Soldeazy change_stock error")
        return tool_error(
            "soldeazy_change_stock",
            EbayMcpError("SOLDEAZY_CHANGE_ERROR", f"改库存失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_create_datasheet(
    item_ids: str = "",
    shop: str = "",
    template: str = "",
    site: str = "US",
    title: str = "",
    sku: str = "",
    price: float = 0.0,
    qty: int = 0,
    category: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create a new datasheet, either copied from live listings or built from scratch.

    Two modes:

    * ``item_ids`` given → ``create_datasheet_from_listing_spy``, which copies the
      listing content and returns the full 212-field payload;
    * no ``item_ids`` → creates a blank datasheet (``template`` presets the
      listing parameters), then optionally fills title/SKU/price/qty/category.

    ``dry_run`` defaults to true and only reports what would happen.
    """

    try:
        picked = await _resolve_shop_id(shop)
        plan: dict[str, Any] = {
            "shop": picked,
            "site": site,
            "template": template,
            "item_ids": item_ids,
        }

        if item_ids:
            plan["mode"] = "from_listing"
            if dry_run:
                return success("soldeazy_create_datasheet", "soldeazy", {**plan, "dry_run": True})
            _require_write_enabled()
            created = await soldeazy.create_from_listing_spy(item_ids, picked["id"])
            return success(
                "soldeazy_create_datasheet", "soldeazy", {**plan, "dry_run": False, **created}
            )

        fields: dict[str, Any] = {}
        if title:
            fields["dsheet_titleexternal"] = title
        if category:
            fields["dsheet_ebcategory"] = category
        if sku:
            fields["dsheet_full_item_model"] = sku
            fields["dsku_product_code[]"] = sku
        if price:
            fields["dsku_price[]"] = price
        if qty:
            fields["dsku_qty[]"] = qty

        plan.update({"mode": "blank", "fields": fields})
        if dry_run:
            return success("soldeazy_create_datasheet", "soldeazy", {**plan, "dry_run": True})

        _require_write_enabled()
        blank = await soldeazy.create_blank_datasheet(
            shop_idx=picked["id"], site_code=site, template_idx=template
        )
        saved = await soldeazy.save_datasheet_fields(blank["rowid"], fields) if fields else None
        return success(
            "soldeazy_create_datasheet",
            "soldeazy",
            {**plan, "dry_run": False, "rowid": blank["rowid"], "saved": saved},
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_create_datasheet", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy create error")
        return tool_error(
            "soldeazy_create_datasheet",
            EbayMcpError("SOLDEAZY_CREATE_ERROR", f"创建数据表失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_delete_datasheet(rowids: str, dry_run: bool = True) -> dict[str, Any]:
    """Delete one or more datasheets by row id (comma separated).

    Deletion submits the list form with ``table_action=bulk-delete`` and
    ``mode=dsheet_datatable``; the row must be searched first or the server
    silently ignores the request.
    """

    try:
        ids = [part.strip() for part in (rowids or "").split(",") if part.strip()]
        if not ids:
            raise EbayMcpError("SOLDEAZY_NO_ROWID", "请给出要删除的数据表编号。")
        if dry_run:
            return success(
                "soldeazy_delete_datasheet",
                "soldeazy",
                {"rowids": ids, "dry_run": True},
            )
        _require_write_enabled()
        result = await soldeazy.delete_datasheets(ids)
        return success(
            "soldeazy_delete_datasheet", "soldeazy", {**result, "dry_run": False}
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_delete_datasheet", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy delete error")
        return tool_error(
            "soldeazy_delete_datasheet",
            EbayMcpError("SOLDEAZY_DELETE_ERROR", f"删除数据表失败: {type(exc).__name__}"),
        )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_upload_photo(
    file_path: str = "",
    image_url: str = "",
    rowid: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Upload a product image, or attach an already-reachable image URL.

    * ``file_path`` → posts to ``datasheet_photo/upload_photos`` and returns the
      stored file name plus the CDN address;
    * ``image_url`` → validated with a HEAD request and used as-is (hot link);
    * ``rowid`` given → writes the result into ``dsheet_gallery`` and saves.

    ``dry_run`` defaults to true: nothing is uploaded and nothing is saved.
    """

    try:
        plan: dict[str, Any] = {"rowid": rowid, "file_path": file_path, "image_url": image_url}
        if not file_path and not image_url:
            raise EbayMcpError("SOLDEAZY_PHOTO_SOURCE", "请给出 file_path 或 image_url。")
        if dry_run:
            return success("soldeazy_upload_photo", "soldeazy", {**plan, "dry_run": True})

        _require_write_enabled()
        if file_path:
            source = Path(file_path).expanduser()
            if not source.is_file():
                raise EbayMcpError("SOLDEAZY_PHOTO_MISSING", f"文件不存在: {source}")
            uploaded = await soldeazy.upload_photo(source)
            gallery = uploaded["file_name"]
            plan.update({"uploaded": uploaded, "gallery": gallery})
        else:
            response = await soldeazy.head_url(image_url)
            if response != 200:
                raise EbayMcpError(
                    "SOLDEAZY_PHOTO_UNREACHABLE",
                    f"图片地址不可访问: HTTP {response}",
                )
            gallery = image_url
            plan.update({"gallery": gallery})

        if rowid:
            saved = await soldeazy.save_datasheet_fields(rowid, {"dsheet_gallery": gallery})
            plan["saved"] = saved
        return success("soldeazy_upload_photo", "soldeazy", {**plan, "dry_run": False})
    except EbayMcpError as exc:
        return tool_error("soldeazy_upload_photo", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy photo error")
        return tool_error(
            "soldeazy_upload_photo",
            EbayMcpError("SOLDEAZY_PHOTO_ERROR", f"图片处理失败: {type(exc).__name__}"),
        )


def _plan_dir() -> Path:
    """不可变计划的存放目录（与 manifest 同级的 soldeazy-plans/）。"""

    base = Path(settings.soldeazy_profile_dir or ".").expanduser().parent
    return base / "soldeazy-plans"


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def soldeazy_plan_changes(
    kind: str,
    site: str,
    targets: dict[str, float],
    shop: str = "",
    supersedes: str = "",
) -> dict[str, Any]:
    """Draft a change plan (read-only): what would change, row by row.

    ``kind`` is ``price`` or ``qty``. ``targets`` is ``{SKU: value}``:

    * price → SKU is the **child** SKU; the price written is exactly this value;
    * qty   → SKU is the **parent** SKU; every row under it gets this quantity.

    Nothing is written. The plan stays a rewritable draft until
    ``soldeazy_confirm_plan`` freezes it.
    """

    try:
        from ebay_mcp_server.providers.soldeazy_apply import build_items, make_plan
        from ebay_mcp_server.providers.soldeazy_plan import write_draft

        if kind not in {"price", "qty"}:
            raise EbayMcpError("SOLDEAZY_PLAN_KIND", "kind 只能是 price 或 qty。")
        if not targets:
            raise EbayMcpError("SOLDEAZY_PLAN_EMPTY", "targets 不能为空。")

        picked = await _resolve_shop_id(shop)
        live = await soldeazy.read_datasheet_values(site)
        items, report = build_items(live, kind, targets)
        plan = make_plan(kind, site, picked, items, supersedes=supersedes)

        # 没有任何改动就不落计划文件：否则会留下一份 items=0 的草稿，
        # 后面 confirm/reconcile 撞上去只会报一句看不懂的"找不到计划"。
        path = str(write_draft(_plan_dir(), plan)) if items else ""

        return success(
            "soldeazy_plan_changes",
            "soldeazy",
            {
                "plan_id": plan.plan_id if items else "",
                "path": path,
                "kind": kind,
                "site": site,
                "shop": picked,
                "rows_in_scope": len(live),
                "planned_items": len(items),
                "items": [item.as_dict() for item in items[:50]],
                "items_truncated": len(items) > 50,
                "items_total": len(items),
                "missing": report["missing"][:20],
                "missing_total": len(report["missing"]),
                "conflicts": report["conflicts"],
                "next": (
                    "确认无误后调用 soldeazy_confirm_plan 冻结"
                    if items
                    else "没有需要改的行，未生成计划文件"
                ),
            },
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_plan_changes", exc)
    except Exception as exc:  # pragma: no cover - browser safety boundary
        logger.exception("Unhandled Soldeazy plan error")
        return tool_error(
            "soldeazy_plan_changes",
            EbayMcpError("SOLDEAZY_PLAN_ERROR", f"生成计划失败: {type(exc).__name__}"),
        )


def _require_plan_id(plan_id: str) -> str:
    """计划 id 必须非空——空 id 会让后续查找报出看不懂的错误。"""

    value = (plan_id or "").strip()
    if not value:
        raise EbayMcpError(
            "SOLDEAZY_PLAN_MISSING",
            "没有可用的计划 id：先调用 soldeazy_plan_changes 生成计划。"
            "（如果它返回 planned_items=0，说明本来就没有需要改的行。）",
        )
    return value


@mcp.tool(annotations=LOCAL_SESSION_ACTION)
async def soldeazy_confirm_plan(plan_id: str) -> dict[str, Any]:
    """Freeze a draft plan: write sha256, mark read-only, refuse further edits.

    After this call the JSON can no longer be changed by any tool; execution
    verifies the hash every time. If the content turns out wrong, draft a new
    plan with ``supersedes`` and archive the old one.
    """

    try:
        from ebay_mcp_server.providers.soldeazy_plan import freeze, load_raw

        plan_id = _require_plan_id(plan_id)
        directory = _plan_dir()
        path = directory / f"{plan_id}.json"
        if not path.exists():
            raise EbayMcpError("SOLDEAZY_PLAN_MISSING", f"找不到计划 {plan_id}")
        raw = load_raw(path)
        from ebay_mcp_server.providers.soldeazy_plan import ChangePlan, PlanItem

        plan = ChangePlan(
            plan_id=raw["plan_id"],
            kind=raw["kind"],
            site=raw.get("site", ""),
            shop=raw.get("shop") or {},
            created_at=raw.get("created_at", ""),
            items=[PlanItem(**item) for item in raw.get("items", [])],
            supersedes=raw.get("supersedes", ""),
            note=raw.get("note", ""),
        )
        if not plan.items:
            raise EbayMcpError("SOLDEAZY_PLAN_EMPTY", "计划里没有任何改动，不冻结。")
        info = freeze(directory, plan)
        return success("soldeazy_confirm_plan", "soldeazy", {**info, "plan_id": plan_id})
    except PlanError as exc:
        return tool_error(
            "soldeazy_confirm_plan",
            EbayMcpError("SOLDEAZY_PLAN_INVALID", str(exc)[:200]),
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_confirm_plan", exc)
    except Exception as exc:
        logger.exception("Unhandled Soldeazy confirm error")
        return tool_error(
            "soldeazy_confirm_plan",
            EbayMcpError("SOLDEAZY_CONFIRM_ERROR", str(exc)[:200]),
        )


@mcp.tool(annotations=REMOTE_WRITE)
async def soldeazy_apply_plan(
    plan_id: str,
    dry_run: bool = True,
    sync: bool = True,
    sync_price: bool = True,
    sync_quantity: bool = False,
) -> dict[str, Any]:
    """Execute a frozen plan: export → batch edit → one upload → queue check.

    The plan file is never modified; every attempt is appended to an audit log.
    ``dry_run`` defaults to true: it verifies the hash and reports scope only.
    """

    try:
        from ebay_mcp_server.providers.soldeazy_apply import apply_plan
        from ebay_mcp_server.providers.soldeazy_plan import load_verified

        plan_id = _require_plan_id(plan_id)
        directory = _plan_dir()
        plan, digest = load_verified(directory, plan_id)

        scope = {
            "plan_id": plan_id,
            "sha256": digest,
            "kind": plan.kind,
            "site": plan.site,
            "shop": plan.shop,
            "items": len(plan.items),
            "datasheets": len({item.rowid for item in plan.items}),
        }
        if dry_run:
            return success("soldeazy_apply_plan", "soldeazy", {**scope, "dry_run": True})

        _require_write_enabled()
        result = await apply_plan(
            soldeazy, plan, directory,
            sync=bool(sync), sync_price=bool(sync_price), sync_quantity=bool(sync_quantity),
        )
        return success(
            "soldeazy_apply_plan",
            "soldeazy",
            {**scope, **result, "dry_run": False, "next": "调用 soldeazy_reconcile_plan 对账"},
        )
    except PlanError as exc:
        return tool_error(
            "soldeazy_apply_plan",
            EbayMcpError("SOLDEAZY_PLAN_INVALID", str(exc)[:200]),
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_apply_plan", exc)
    except Exception as exc:
        logger.exception("Unhandled Soldeazy apply error")
        return tool_error(
            "soldeazy_apply_plan",
            EbayMcpError("SOLDEAZY_APPLY_ERROR", str(exc)[:200]),
        )


@mcp.tool(annotations=READ_ONLY_NETWORK)
async def soldeazy_reconcile_plan(plan_id: str) -> dict[str, Any]:
    """Compare the live values against a frozen plan and write a report file.

    The report is a new file (``<plan_id>.reconcile.json``); the plan itself is
    untouched and stays the single source of what was intended.
    """

    try:
        from ebay_mcp_server.providers.soldeazy_apply import reconcile
        from ebay_mcp_server.providers.soldeazy_plan import load_verified

        plan_id = _require_plan_id(plan_id)
        directory = _plan_dir()
        plan, digest = load_verified(directory, plan_id)
        report = await reconcile(soldeazy, plan, directory)
        return success(
            "soldeazy_reconcile_plan",
            "soldeazy",
            {**report, "sha256": digest},
        )
    except PlanError as exc:
        return tool_error(
            "soldeazy_reconcile_plan",
            EbayMcpError("SOLDEAZY_PLAN_INVALID", str(exc)[:200]),
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_reconcile_plan", exc)
    except Exception as exc:
        logger.exception("Unhandled Soldeazy reconcile error")
        return tool_error(
            "soldeazy_reconcile_plan",
            EbayMcpError("SOLDEAZY_RECONCILE_ERROR", str(exc)[:200]),
        )


@mcp.tool(annotations=READ_ONLY_LOCAL)
async def soldeazy_change_history(
    limit: int = 20,
    site: str = "",
    kind: str = "",
) -> dict[str, Any]:
    """Read the local Soldeazy write history (newest first).

    Every applied write appends one JSONL record: token, site, search string,
    uploaded file, changed cells and the sync result. ``site``/``kind`` filter
    the list (kind is ``price`` or ``stock``). Corrupt lines are skipped rather
    than failing the whole history.
    """
    try:
        from ebay_mcp_server.providers.soldeazy_write import read_manifest

        if kind and kind not in {"price", "stock"}:
            raise EbayMcpError("SOLDEAZY_HISTORY_KIND", "kind 只能是 price 或 stock。")
        path = _manifest_path()
        records = read_manifest(path, limit=max(1, min(int(limit), 200)), site=site, kind=kind)
        return success(
            "soldeazy_change_history",
            "local-manifest",
            {
                "manifest": path,
                "count": len(records),
                "records": records,
            },
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_change_history", exc)
    except Exception as exc:  # pragma: no cover - 磁盘异常
        return tool_error(
            "soldeazy_change_history",
            EbayMcpError("SOLDEAZY_HISTORY_ERROR", f"读取变更历史失败: {exc}"),
        )


@mcp.tool(annotations=LOCAL_FILE_WRITE)
async def soldeazy_stock_template(out_path: str, skus: list[str]) -> dict[str, Any]:
    """Write the stock sheet that the operator fills in by hand.

    One row per actual SKU with an empty ``库存`` column; only that column is
    read back, so the operator never edits SKU spellings. Requires the
    ``soldeazy`` extra (openpyxl).
    """
    try:
        from ebay_mcp_server.providers.soldeazy_stock import write_stock_template

        target = write_stock_template(out_path, skus)
        return success(
            "soldeazy_stock_template",
            "local-writer",
            {"path": str(target), "rows": len(skus)},
        )
    except EbayMcpError as exc:
        return tool_error("soldeazy_stock_template", exc)
    except Exception as exc:  # pragma: no cover - 依赖缺失/磁盘错误
        return tool_error(
            "soldeazy_stock_template",
            EbayMcpError("SOLDEAZY_TEMPLATE_ERROR", f"生成库存模板失败: {exc}"),
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
