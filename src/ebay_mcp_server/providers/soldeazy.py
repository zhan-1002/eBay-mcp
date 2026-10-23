"""Soldeazy datasheet browser provider (Playwright, persistent profile).

The production 影刀 flow is *not* an API client: it drives the Soldeazy web UI
(login → search → export xlsx → offline pricing → upload → BULK SYNC). This
module reproduces that path in Playwright so the MCP server can do the same
without 影刀.

Selector policy:

* every locator is declared once in :data:`SELECTORS` with the 影刀 XPath,
  plus a stable ``css``/``name`` alternative when the site offers one;
* locators are tried in order (css → xpath) so a cosmetic page change only
  breaks one entry;
* text-anchored locators (buttons, banners) are matched on their visible label.

Status: the login/search/read path is written against the live page structure
recorded in ``archive/02_soldeazy详情补数``; export/upload/sync are written from
the 影刀 selector list and still need one live run before they are trusted.
"""

from __future__ import annotations

import asyncio
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError

BASE_URL = "https://stiger.soldeazy.com"
LIST_PATH = "/app/soldeazy/datasheet/dsheet_list?default_search_profile"
LOGIN_PATH = "/app/soldeazy/login"
UPLOAD_PATH = "/app/soldeazy/upload-datasheet"


@dataclass(frozen=True)
class Locator:
    """One UI element: a stable alternative first, the 影刀 XPath as fallback."""

    name: str
    xpath: str
    css: str = ""

    def candidates(self) -> list[str]:
        if self.css:
            return [self.css, f"xpath={self.xpath}"]
        return [f"xpath={self.xpath}"]


SELECTORS: dict[str, Locator] = {
    # --- 登录页 ---
    "login_user": Locator("输入框_login_user", '//form//input[@type="text"]', "input[name=login_user]"),
    "login_pass": Locator("密码框", '//form//input[@type="password"]', "input[name=login_pass]"),
    "login_submit": Locator("Login", '//form//button[@type="submit"]', "form button[type=submit]"),
    "ad_popup": Locator("soldeazy-广告弹框", '//div[@class="fancybox-skin"]', ".fancybox-skin"),
    "ad_dismiss": Locator(
        "弹框-(不再显示此消息)",
        '//ul/li//input',
        "#fancybox_dismiss_option",
    ),
    "ad_close": Locator(
        "弹框-关闭",
        '//ul/li//a[normalize-space(.)="关闭"][contains(@class,"fancybox_dismiss")]',
    ),
    # --- datasheet 搜索页 ---
    "search_sku": Locator("SKU输入框", "//form//input", "form input[name=txtproductcode]"),
    "search_site": Locator("Channel Site", "//form//select", "form select[name=listsite]"),
    "search_format": Locator("Listing Format", "//form//select", "form select[name=listformat]"),
    "search_status": Locator("Status", "//form//select", "form select[name=listactive]"),
    "search_date": Locator("Date Modified", "//form//select", "form select[name=listdate]"),
    "search_scope": Locator("Scope", "//form//table//tr/td//select", "form select[name=listlimit]"),
    "search_button": Locator("Search", '//form//input[@type="button"][@name="btn_search"][@id="btn_search"]'),
    "result_table": Locator("搜索结果table", '//form//table[@id="tbl_dSheet"]', "#tbl_dSheet"),
    "export_button": Locator(
        "Export",
        '//form//table//tr/td/input[@type="button"][contains(@class,"btn_01")]'
        '[contains(@class,"bulk-action-btn")][contains(@class,"export")]',
        "input.bulk-action-btn.export",
    ),
    "export_options": Locator("Bulk Export Options", "//select", "#divBulkExportDialog select"),
    "export_profile": Locator("Add / edit an Export Profile", "//select", "#divBulkExportDialog select"),
    "export_confirm": Locator("Bulk Export Options_export", "//button"),
    "bulk_sync_button": Locator("Bulk SYNC", '//form//table//tr/td/input[@type="button"][@id="btn_bulkdalign"]', "#btn_bulkdalign"),
    "sync_dialog": Locator("同步弹框", '//div[@id="jqizoo"]', "#jqizoo"),
    "sync_price_postage": Locator("Price Postage", "//input"),
    "sync_up_button": Locator("SYNC UP", '//button[normalize-space(.)="SYNC UP"]'),
    "sync_banner": Locator(
        "New D-Align bul...",
        '//form//div[starts-with(normalize-space(.),"New D-Align bulk job added")]',
    ),
    # --- 上传页 ---
    "upload_file": Locator("选择文件_filePackage", '//form//input[@type="file"]', "form input[type=file]"),
    "upload_done": Locator("Upload Completed", '//form/div[normalize-space(.)="Upload Completed"]'),
}

#: Column labels of the result table, as seen in the production list page.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "rowid": ("数据表编号", "Row ID", "dsheet_row_id"),
    "shop": ("渠道帐号", "Sales channel"),
    "site": ("站点", "Site"),
    "sku": ("SKU", "dsheet_product_code"),
    "price": ("价格", "Price"),
    "postage": ("运费(当地)", "运费", "Post.D."),
    "qty": ("数量", "Qty"),
    "total": ("合计", "Total"),
}


def _selector_available() -> bool:
    return importlib.util.find_spec("playwright.async_api") is not None


class SoldeazyBrowser:
    """Drive the Soldeazy datasheet UI with one persistent browser profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = (settings.soldeazy_base_url or BASE_URL).rstrip("/")
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lock = asyncio.Lock()

    # ---------- 生命周期 ----------
    @property
    def profile_dir(self) -> Path | None:
        raw = (self.settings.soldeazy_profile_dir or "").strip()
        return Path(raw).expanduser() if raw else None

    def profile_ready(self) -> bool:
        directory = self.profile_dir
        return bool(directory and directory.is_dir() and any(directory.iterdir()))

    async def status(self) -> dict[str, Any]:
        return {
            "name": "soldeazy",
            "base_url": self.base_url,
            "playwright_installed": _selector_available(),
            "profile_dir": str(self.profile_dir) if self.profile_dir else "",
            "profile_ready": self.profile_ready(),
            "write_enabled": self.settings.soldeazy_write_enabled,
            "browser_open": self._page is not None,
        }

    async def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        if not _selector_available():
            raise EbayMcpError(
                "SOLDEAZY_BROWSER_MISSING",
                "playwright is not installed; run `uv run playwright install chromium`.",
            )
        directory = self.profile_dir
        if directory is None:
            raise EbayMcpError(
                "SOLDEAZY_PROFILE_MISSING",
                "Configure SOLDEAZY_PROFILE_DIR before opening the Soldeazy browser.",
            )
        directory.mkdir(parents=True, exist_ok=True)

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(directory),
            headless=self.settings.soldeazy_headless,
            channel=self.settings.soldeazy_browser_channel or None,
            args=["--disable-blink-features=AutomationControlled"],
            locale="zh-CN",
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        self._page.set_default_timeout(self.settings.soldeazy_navigation_timeout * 1000)
        return self._page

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = self._page = self._playwright = None

    # ---------- 基础动作 ----------
    async def _locate(self, key: str) -> Any:
        page = await self._ensure_page()
        entry = SELECTORS[key]
        last: Exception | None = None
        for selector in entry.candidates():
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=8000)
                return locator
            except Exception as exc:  # noqa: BLE001 - 逐个候选试探
                last = exc
        raise EbayMcpError(
            "SOLDEAZY_ELEMENT_MISSING",
            f"找不到页面元素 {entry.name}",
            details={"candidates": entry.candidates(), "error": str(last)[:200]},
        )

    async def _dismiss_popup(self) -> None:
        page = await self._ensure_page()
        for key in ("ad_dismiss", "ad_close"):
            try:
                locator = page.locator(SELECTORS[key].candidates()[-1]).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=3000)
                    await asyncio.sleep(0.5)
            except Exception:  # noqa: BLE001 - 弹框是尽力而为
                continue

    # ---------- 登录 ----------
    async def interactive_login(self) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.goto(f"{self.base_url}{LOGIN_PATH}", wait_until="domcontentloaded")
        await self._dismiss_popup()

        username = self.settings.soldeazy_username
        password = self.settings.soldeazy_password
        if username and password:
            await (await self._locate("login_user")).fill(username)
            await (await self._locate("login_pass")).fill(password)
            await (await self._locate("login_submit")).click()
        else:
            # 无凭据时留给人工：最多等 manual_recovery_timeout
            deadline = self.settings.soldeazy_navigation_timeout * 20
            await self._wait_logged_in(page, deadline)

        await self._wait_logged_in(page, self.settings.soldeazy_navigation_timeout * 2)
        await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
        await self._dismiss_popup()
        return {"success": True, "url": page.url, "profile_dir": str(self.profile_dir)}

    async def _wait_logged_in(self, page: Any, timeout_seconds: float) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if "/login" not in (page.url or ""):
                return
            await asyncio.sleep(1.0)
        raise EbayMcpError(
            "SOLDEAZY_LOGIN_TIMEOUT",
            "登录未完成：请在弹出的浏览器窗口里手动登录，或检查 SOLDEAZY_USERNAME/PASSWORD。",
        )

    # ---------- 搜索 ----------
    async def search(self, sku_terms: str, site: str) -> dict[str, Any]:
        """Search one site by a space-joined SKU string and read the results."""

        async with self._lock:
            page = await self._ensure_page()
            await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
            await self._dismiss_popup()

            await (await self._locate("search_sku")).fill(sku_terms)
            if site:
                await self._select_site(site)
            await (await self._locate("search_button")).click()
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(self.settings.soldeazy_min_delay)

            table = await self._locate("result_table")
            rows = await table.locator("tr").all_inner_texts()
            header, records = parse_table(rows)
            return {
                "site": site,
                "search": sku_terms,
                "columns": header,
                "row_count": len(records),
                "rows": records,
            }

    async def _select_site(self, site: str) -> None:
        locator = await self._locate("search_site")
        try:
            await locator.select_option(label=site)
        except Exception:
            await locator.select_option(site)

    # ---------- 导出 / 上传 / 同步（需真机验证） ----------
    async def export(self, dest: Path) -> dict[str, Any]:
        page = await self._ensure_page()
        await (await self._locate("export_button")).click()
        await (await self._locate("sync_dialog")).wait_for(state="visible")
        async with page.expect_download() as download_info:
            await page.get_by_role("button", name="导出 Excel").click()
        download = await download_info.value
        dest.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(dest))
        return {"success": True, "path": str(dest)}

    async def upload(self, path: Path) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.goto(f"{self.base_url}{UPLOAD_PATH}", wait_until="domcontentloaded")
        await (await self._locate("upload_file")).set_input_files(str(path))
        await (await self._locate("upload_done")).wait_for(
            state="visible", timeout=self.settings.soldeazy_navigation_timeout * 2 * 1000
        )
        return {"success": True, "path": str(path)}

    async def sync_up(self, *, price_postage: bool = True, quantity: bool = False) -> dict[str, Any]:
        if not (price_postage or quantity):
            raise EbayMcpError("SOLDEAZY_SYNC_SCOPE_EMPTY", "至少选择一项同步范围。")
        await (await self._locate("bulk_sync_button")).click()
        await (await self._locate("sync_dialog")).wait_for(state="visible")
        dialog = await self._locate("sync_dialog")
        if price_postage:
            await dialog.get_by_text("价格及邮费").first.click()
        if quantity:
            await dialog.get_by_text("刊登数量").first.click()
        await (await self._locate("sync_up_button")).click()
        await (await self._locate("sync_banner")).wait_for(
            state="visible", timeout=self.settings.soldeazy_navigation_timeout * 2 * 1000
        )
        return {"success": True, "price_postage": price_postage, "quantity": quantity}


# ---------- 纯解析（可单测） ----------
def resolve_columns(header: Sequence[str]) -> dict[str, int]:
    """Map logical field names to column indexes using the table header."""

    normalized = [str(cell).strip() for cell in header]
    mapping: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for index, cell in enumerate(normalized):
            if cell in aliases:
                mapping[field] = index
                break
    return mapping


def _number(text: str) -> float | None:
    cleaned = (text or "").strip().replace(",", "").replace("£", "").replace("€", "")
    if not cleaned or cleaned in {"-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_table(rows: Iterable[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Turn ``#tbl_dSheet`` rows (inner text) into records.

    The first row that yields a usable column map is treated as the header.
    """

    texts = [row for row in rows if str(row).strip()]
    if not texts:
        return [], []

    header_cells: list[str] = []
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(texts):
        cells = [cell.strip() for cell in str(raw).split("\t")]
        if index == 0:
            header_cells = cells
            columns = resolve_columns(cells)
            if "sku" not in columns:
                raise EbayMcpError(
                    "SOLDEAZY_TABLE_UNEXPECTED",
                    "搜索结果表里找不到 SKU 列，页面结构可能已改版。",
                    details={"header": cells[:20]},
                )
            continue
        if len(cells) < len(header_cells):
            cells += [""] * (len(header_cells) - len(cells))
        record: dict[str, Any] = {}
        for field, col in columns.items():
            value = cells[col] if col < len(cells) else ""
            if field in {"price", "postage", "qty"}:
                record[field] = _number(value)
            else:
                record[field] = value
        if record.get("sku"):
            records.append(record)
    return header_cells, records
