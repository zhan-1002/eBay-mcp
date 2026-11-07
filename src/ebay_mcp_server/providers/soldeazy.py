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
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError

BASE_URL = "https://stiger.soldeazy.com"
LIST_PATH = "/app/soldeazy/datasheet/dsheet_list?default_search_profile"
LOGIN_PATH = "/app/soldeazy/login"
UPLOAD_PATH = "/app/soldeazy/upload-datasheet"

#: 站点下拉里显示的是英文站点名（实测 listsite），不是 US/DE 代码
SITE_LABELS: dict[str, str] = {
    "US": "US",
    "UK": "UK",
    "DE": "Germany",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "AU": "Australia",
    "CA": "Canada",
    "PL": "Poland",
    "NL": "Netherlands",
    "JP": "Japan",
    "IE": "Ireland",
    "SG": "Singapore",
    "HK": "HongKong",
    "MY": "Malaysia",
}

#: 站点下拉的 value（实测）
SITE_CODES: dict[str, str] = {
    "US": "0",
    "UK": "3",
    "DE": "77",
    "FR": "71",
    "IT": "101",
    "ES": "186",
    "AU": "15",
    "CA": "2",
    "PL": "212",
    "NL": "146",
    "JP": "903",
    "IE": "205",
}


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
    "export_dialog": Locator("批量导出弹层", '//div[@id="jqizoo"]', "#jqizoo"),
    "export_profile_select": Locator(
        "导出档案下拉",
        "//div[@id='jqizoo']//select[@name='listExppf']",
        "#jqizoo select[name=listExppf]",
    ),
    "export_format_select": Locator(
        "导出格式下拉",
        "//div[@id='jqizoo']//select[@name='listExpfmt']",
        "#jqizoo select[name=listExpfmt]",
    ),
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
        self.active_shop: dict[str, str] | None = None

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
        await asyncio.sleep(2)
        await self._dismiss_popup()

        # profile 里已有会话时，站点直接跳过登录页——绝不再登一次
        if "/login" not in (page.url or "").lower():
            await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
            await self._dismiss_popup()
            return {
                "success": True,
                "reused_session": True,
                "url": page.url,
                "profile_dir": str(self.profile_dir),
            }

        username = self.settings.soldeazy_username
        password = self.settings.soldeazy_password
        if username and password:
            await (await self._locate("login_user")).fill(username)
            await (await self._locate("login_pass")).fill(password)
            await (await self._locate("login_submit")).click()
        else:
            # 无凭据时留给人工，但别干等十分钟：120 秒没登上就直接报错
            deadline = min(120.0, self.settings.soldeazy_navigation_timeout * 4)
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
    async def search(self, sku_terms: str, site: str, shop: str = "") -> dict[str, Any]:
        """Search one site by a space-joined SKU string and read the results."""

        async with self._lock:
            page = await self._ensure_page()
            await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
            await self._dismiss_popup()

            await (await self._locate("search_sku")).fill(sku_terms)
            if site:
                await self._select_site(site)
            shop = shop or ((self.active_shop or {}).get("name") or "")
            if shop:
                await self._select_shop(shop)
            await self._select_scope_whole_result()
            await (await self._locate("search_button")).click()
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(self.settings.soldeazy_min_delay)

            table = await self._locate("result_table")
            trs = table.locator("tr")
            total = await trs.count()
            cell_rows: list[list[str]] = []
            for index in range(total):
                cells = await trs.nth(index).locator("th,td").all_inner_texts()
                cell_rows.append(cells)  # 原样交给 parse_rows：换行是变体分隔符
            header, records = parse_rows(cell_rows)
            return {
                "site": site,
                "shop": shop,
                "search": sku_terms,
                "columns": header,
                "row_count": len(records),
                "rows": records,
            }

    async def _ensure_rows_selected(self) -> int:
        """导出弹层只在「有勾选」时出现，所以导出前先全选当前结果。"""

        page = await self._ensure_page()
        boxes = page.locator("#tbl_dSheet input[type=checkbox]")
        total = await boxes.count()
        if not total:
            raise EbayMcpError(
                "SOLDEAZY_NO_RESULT", "搜索结果里没有可勾选的数据表，无法导出。"
            )

        head = page.locator("#tbl_dSheet tr").first.locator("input[type=checkbox]").first
        try:
            if await head.count():
                if not await head.is_checked():
                    await head.check(force=True)
                selected = await page.locator("#tbl_dSheet input[type=checkbox]:checked").count()
                if selected > 0:
                    return selected
        except Exception:  # noqa: BLE001 - 表头没有全选就逐行勾
            pass

        selected = 0
        for index in range(min(total, 25)):
            box = boxes.nth(index)
            try:
                if not await box.is_checked():
                    await box.check(force=True)
                    selected += 1
            except Exception:  # noqa: BLE001
                continue
        return selected

    async def list_shop_options(self) -> list[dict[str, str]]:
        """列出可用渠道账号（搜索表单里 `select[name='listshop[]']` 的选项）。

        这是站点给当前登录账号授权的门店清单，比 /ebayac 页面更可靠。
        """

        page = await self._ensure_page()
        if not (page.url or "").startswith(self.base_url):
            await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
            await asyncio.sleep(1.5)

        options = await page.evaluate("""
        () => {
          const sel = Array.from(document.querySelectorAll('select'))
            .find(x => x.name === 'listshop[]');
          if (!sel) return [];
          return Array.from(sel.options)
            .map(o => ({id: o.value, name: o.textContent.trim()}))
            .filter(o => o.id && o.name);
        }
        """)
        return options

    async def switch_shop(self, shop: str) -> dict[str, str]:
        """切换当前渠道账号（后续搜索/预览/写入默认用它）。"""

        wanted = (shop or "").strip()
        if not wanted:
            raise EbayMcpError("SOLDEAZY_SHOP_REQUIRED", "请给出渠道账号简称或 id")
        options = await self.list_shop_options()
        if not options:
            raise EbayMcpError("SOLDEAZY_SHOP_LIST_EMPTY", "没能读到渠道账号列表")

        hit = next((o for o in options if o["id"] == wanted), None)
        if hit is None:
            upper = wanted.upper()
            hit = next((o for o in options if o["name"].upper() == upper), None)
        if hit is None:
            hit = next((o for o in options if upper in o["name"].upper()), None)
        if hit is None:
            raise EbayMcpError(
                "SOLDEAZY_SHOP_NOT_FOUND",
                f"渠道账号里没有 {shop}",
                details={"available": [o["name"] for o in options][:20]},
            )

        self.active_shop = hit
        return hit

    async def _select_shop(self, shop: str) -> None:
        """按渠道账号过滤。控件是 Chosen 多选，原生 select 被隐藏，
        只能直接设 selected 再触发 change/chosen:updated。"""

        page = await self._ensure_page()
        picked = await page.evaluate("""
        (shop) => {
          const s = document.querySelector("select[name='listshop[]']");
          if (!s) return null;
          Array.from(s.options).forEach(o => { o.selected = false; });
          const opt = Array.from(s.options).find(o => o.textContent.trim() === shop)
                   || Array.from(s.options).find(o => o.textContent.includes(shop));
          if (!opt) return null;
          opt.selected = true;
          s.dispatchEvent(new Event("change", {bubbles: true}));
          if (window.jQuery) { try { jQuery(s).trigger("chosen:updated"); } catch (e) {} }
          return {value: opt.value, text: opt.textContent.trim()};
        }
        """, shop)
        if not picked:
            raise EbayMcpError(
                "SOLDEAZY_SHOP_NOT_FOUND",
                f"渠道账号下拉里找不到 {shop}",
            )

    async def _select_scope_whole_result(self) -> None:
        """导出范围要覆盖整个搜索结果，不能只导勾选行。

        真机上这是表单里的 `select[name=bulk_option]`：`whole_result` /
        `partial_result` / `selected_items`。找不到就当页面不提供该控件。
        """

        page = await self._ensure_page()
        scope = page.locator("select[name=bulk_option]").first
        try:
            if await scope.count():
                await scope.select_option("whole_result", timeout=5000)
        except Exception:  # noqa: BLE001 - 只是尽力设置
            pass

    async def _select_site(self, site: str) -> None:
        """站点下拉里用的是英文站点名（US/UK/Germany…），不是 US/DE 这种代码。"""

        locator = await self._locate("search_site")
        code = (site or "").strip().upper()
        label = SITE_LABELS.get(code, code)
        for candidate in (label, code):
            try:
                await locator.select_option(label=candidate, timeout=5000)
                return
            except Exception:  # noqa: BLE001 - 依次试下一个写法
                continue
        try:
            await locator.select_option(str(SITE_CODES.get(code, "")), timeout=5000)
            return
        except Exception as exc:  # noqa: BLE001
            raise EbayMcpError(
                "SOLDEAZY_SITE_OPTION_MISSING",
                f"站点下拉里找不到 {site}（试过 {label!r} / {code!r}）",
            ) from exc

    # ---------- 导出 / 上传 / 同步（需真机验证） ----------
    async def export(self, dest: Path) -> dict[str, Any]:
        """导出当前搜索结果（导出档案 quanty &price&postage，xlsx）。

        实测：点「导出 Excel」后表单 POST 到新标签页直接下载；导出档案为空时
        页面 JS 会直接 return false，所以档案必须显式指定。
        """

        page = await self._ensure_page()
        profile = (self.settings.soldeazy_export_profile or "55").strip()

        selected = await self._ensure_rows_selected()
        if not selected:
            raise EbayMcpError("SOLDEAZY_NO_SELECTION", "未能勾选任何数据表，导出中止。")

        await (await self._locate("export_button")).click()
        dialog = await self._locate("export_dialog")
        await dialog.wait_for(state="visible")

        await (await self._locate("export_profile_select")).select_option(profile)
        await (await self._locate("export_format_select")).select_option("xlsx")

        async with page.context.expect_event("download") as info:
            await dialog.get_by_text("导出 Excel", exact=True).first.click()
        download = await info.value

        dest.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(dest))
        return {
            "success": True,
            "path": str(dest),
            "profile": profile,
            "source_name": download.suggested_filename,
            "url": download.url,
        }

    async def upload(self, path: Path) -> dict[str, Any]:
        """上传 _done.xlsx，等待页面出现 `Upload Completed`。

        影刀块 108→118 的做法就是「选文件 → 等 3 秒 → 等 Upload Completed」，
        中间没有别的点击；这里照做，并把失败时的页面提示带回来便于定位。
        """

        page = await self._ensure_page()
        await page.goto(f"{self.base_url}{UPLOAD_PATH}", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        await (await self._locate("upload_file")).set_input_files(str(path))
        await asyncio.sleep(3)

        # 站点语言不同，成功提示也不一样：英文 Upload Completed，中文 完成刊登数据上载
        markers = ("Upload Completed", "完成刊登数据上载", "上载完成", "上传完成")
        try:
            for marker in markers:
                try:
                    await page.get_by_text(marker, exact=False).first.wait_for(
                        state="visible", timeout=15000
                    )
                    break
                except Exception:  # noqa: BLE001 - 换下一个候选文案
                    continue
            else:
                raise TimeoutError("no success marker appeared")
        except Exception as exc:  # noqa: BLE001 - 把页面提示捞出来再抛
            text = ""
            try:
                text = (await page.evaluate("() => document.body.innerText || ''"))[:400]
            except Exception:  # noqa: BLE001
                pass
            raise EbayMcpError(
                "SOLDEAZY_UPLOAD_NOT_COMPLETED",
                "上传后没有等到 Upload Completed",
                details={"page_text": " | ".join(text.split())[:300]},
            ) from exc

        return {"success": True, "path": str(path), "file": path.name}

    async def sync_up_via_api(
        self, *, price_postage: bool = True, quantity: bool = False
    ) -> dict[str, Any]:
        """用接口提交「同步上平台」，替代点弹框。

        前提：当前页面已在搜索结果上、且目标行已勾选（`table_row_ids`）。
        `sql_cache_token` 由本次搜索下发，必须从页面上取，不能沿用旧值。
        """

        page = await self._ensure_page()
        token = await page.evaluate(
            "() => ((document.querySelector('input[name=sql_cache_token]')||{}).value || '')"
        )
        row_ids = await page.evaluate("""
        () => {
          const out = [];
          Array.from(document.querySelectorAll('#tbl_dSheet tr')).forEach(r => {
            const box = r.querySelector('input[type=checkbox]');
            if (!box || !box.checked) return;
            const cells = Array.from(r.cells).map(c => (c.innerText || '').trim());
            const hit = cells.find(t => /^[0-9]{6,}$/.test(t));
            if (hit) out.push(hit);
          });
          return out;
        }
        """)
        if not row_ids:
            raise EbayMcpError("SOLDEAZY_NO_SELECTION", "没有勾选任何数据表，无法同步。")

        form = {
            "mode": "bulk_dalign",
            "second_mode": "dsheet_list",
            "table_action": "show",
            "bulk_option": "selected_items",
            "table_row_ids": ",".join(row_ids),
            "dalign_price": "1" if price_postage else "0",
            "dalign_imghttps": "1",
            "dalign_option": "2",
            "sql_cache_token": token,
        }
        if quantity:
            form["dalign_qty"] = "1"

        response = await page.context.request.post(
            f"{self.base_url}/app/soldeazy/datasheet", form=form, timeout=120_000
        )
        text = (await response.text()) or ""
        hints = []
        for marker in ("没有在线刊登", "New D-Align", "同步成功", "已加入", "失败"):
            if marker in text:
                hints.append(marker)
        return {
            "success": response.status == 200,
            "status": response.status,
            "rows": len(row_ids),
            "table_row_ids": row_ids,
            "hints": hints,
        }

    async def create_blank_datasheet(
        self, *, shop_idx: str, site_code: str = "US", template_idx: str = ""
    ) -> dict[str, Any]:
        """从0创建一条空数据表，返回新 rowid（模板只预设刊登参数，不含产品数据）。"""

        page = await self._ensure_page()
        await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)
        before = await self._row_ids(page)

        response = await page.context.request.post(
            f"{self.base_url}/app/soldeazy/datasheet-create/index",
            form={
                "mode": "dsheet_datatable",
                "table_action": "create",
                "new_dsheet_shop_initial_idx": str(shop_idx),
                "new_dsheet_site_code": site_code,
                "new_dsheet_biz_profile_idx": "",
                "new_dsheet_listing_template_idx": str(template_idx),
                "new_dsheet_price_margin": "NaN",
                "new_dsheet_channel_service_fee": "NaN",
                "new_dsheet_price": "NaN",
            },
            timeout=120_000,
        )
        html = (await response.text()).lstrip("\ufeff")
        match = re.search(r"dsheet_row_id[^>]*value=['\"](\d+)", html) or re.search(
            r"table_row_id=(\d+)", html
        )
        if match:
            return {"success": True, "rowid": match.group(1), "source": "response"}

        await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        after = await self._row_ids(page)
        new = [rowid for rowid in after if rowid not in before]
        if not new:
            raise EbayMcpError(
                "SOLDEAZY_CREATE_NO_ROWID", "创建后没能确定新数据表编号"
            )
        return {"success": True, "rowid": new[0], "source": "list_diff"}

    async def _row_ids(self, page: Any) -> list[str]:
        return await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('#tbl_dSheet tr'))
              .map(r => Array.from(r.cells).map(c => (c.innerText || '').trim()))
              .map(c => c.find(t => /^\\d{6,}$/.test(t))).filter(Boolean)
            """
        )

    async def save_datasheet_fields(
        self, rowid: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        """打开数据表编辑页，按字段名填值并点「储存」。

        价格/数量/SKU 在 ``dsku_price[]`` / ``dsku_qty[]`` / ``dsku_product_code[]``，
        用 ``dsheet_price`` 之类会静默丢字段。
        """

        page = await self._ensure_page()
        await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)
        await page.evaluate(
            """
            (rowid) => {
              const f = document.createElement('form');
              f.method = 'POST';
              f.action = '/app/soldeazy/datasheet';
              const add = (n, v) => {
                const i = document.createElement('input');
                i.type = 'hidden'; i.name = n; i.value = v;
                f.appendChild(i);
              };
              add('mode', 'dsheet_datatable');
              add('table_action', 'edit');
              add('table_row_id', rowid);
              document.body.appendChild(f);
              f.submit();
            }
            """,
            str(rowid),
        )
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2.5)

        applied = await page.evaluate(
            """
            (values) => {
              const done = {};
              Object.entries(values).forEach(([name, value]) => {
                const el = document.querySelector('[name="' + name + '"]');
                if (!el) { done[name] = 'missing'; return; }
                if (el.tagName === 'SELECT') {
                  const opt = Array.from(el.options)
                    .find(o => o.value === String(value) || o.textContent.trim() === String(value));
                  if (!opt) { done[name] = 'no option'; return; }
                  opt.selected = true;
                } else {
                  el.value = value;
                }
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                done[name] = 'ok';
              });
              return done;
            }
            """,
            values,
        )

        await asyncio.sleep(0.5)
        clicked = await page.evaluate(
            """
            () => {
              const btns = Array.from(document.querySelectorAll('button,input[type=button],a'))
                .filter(el => el.offsetParent);
              const hit = btns.find(b => (b.value || b.innerText || '').trim() === '储存');
              if (!hit) return null;
              hit.click();
              return '储存';
            }
            """
        )
        await asyncio.sleep(6)
        notice = await page.evaluate(
            """
            () => {
              const el = document.querySelector('[class*=ajax-error], [class*=error-msg], [class*=notice]');
              return el && el.offsetParent ? (el.innerText || '').trim().slice(0, 200) : '';
            }
            """
        )
        # 字段名不存在或没有对应选项时，页面照样会提交成功——必须自己判失败
        rejected = {
            name: state
            for name, state in applied.items()
            if state in {"missing", "no option"}
        }
        return {
            "success": clicked is not None and not notice and not rejected,
            "rowid": str(rowid),
            "filled": applied,
            "rejected": rejected,
            "notice": notice,
        }

    async def head_url(self, url: str) -> int:
        """探测图片地址是否可访问，返回 HTTP 状态（不可达返回 0）。"""

        page = await self._ensure_page()
        try:
            response = await page.context.request.head(url, timeout=30_000)
            return response.status
        except Exception:  # noqa: BLE001 - 任何网络异常都按不可达处理
            return 0

    async def upload_photo(self, path: Path) -> dict[str, Any]:
        """上传产品图片，返回数据表 gallery 字段应填的文件名与 CDN 地址。"""

        page = await self._ensure_page()
        response = await page.context.request.post(
            f"{self.base_url}/app/soldeazy/datasheet_photo/upload_photos",
            multipart={
                "photofile": {
                    "name": path.name,
                    "mimeType": "image/jpeg",
                    "buffer": path.read_bytes(),
                }
            },
            timeout=180_000,
        )
        text = await response.text()
        match = re.search(r"upload_res\s*=\s*(\{.*?\})\s*;", text, re.S)
        if not match:
            raise EbayMcpError(
                "SOLDEAZY_PHOTO_UPLOAD_FAILED",
                "图片上传没有返回 upload_res",
                details={"head": text[:200]},
            )
        body = json.loads(match.group(1))
        return {
            "success": True,
            "file_name": body.get("file_name"),
            "real_name": body.get("real_name"),
            "gallery_type": body.get("gallery_type"),
        }

    async def delete_datasheets(self, rowids: Sequence[str]) -> dict[str, Any]:
        """删除数据表（实测：整表单提交，不是 AJAX）。

        关键参数：`table_action=bulk-delete` + `mode=dsheet_datatable`
        + `table_row_ids`。`mode` 必须是 `dsheet_datatable`，
        用搜索的 `dsheet_list` 提交不会生效（也不会报错）。
        """

        ids = [str(rowid).strip() for rowid in rowids if str(rowid).strip()]
        if not ids:
            raise EbayMcpError("SOLDEAZY_NO_ROWID", "没有给出要删除的数据表编号")

        page = await self._ensure_page()
        await page.goto(f"{self.base_url}{LIST_PATH}", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # 删除表单必须带着当前搜索上下文提交，先把目标行搜出来
        await page.locator("input[name=txtdsheetrowid]").first.fill(ids[0])
        await page.locator("#btn_search").first.click()
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        await page.evaluate("""
        ([ids]) => {
          const form = document.querySelector('form');
          if (!form) return false;
          const put = (id, name, value) => {
            let el = form.querySelector('#' + id);
            if (!el) {
              el = document.createElement('input');
              el.type = 'hidden'; el.id = id; el.name = name;
              form.appendChild(el);
            }
            el.value = value;
          };
          put('table_action', 'table_action', 'bulk-delete');
          put('mode', 'mode', 'dsheet_datatable');
          put('second_mode', 'second_mode', 'dsheet_list');
          put('table_row_ids', 'table_row_ids', ids.join(','));
          form.submit();
          return true;
        }
        """, [ids])
        await asyncio.sleep(6)
        return {"success": True, "requested": ids, "url": page.url}

    async def create_from_listing_spy(
        self,
        item_ids: str,
        shop_idx: str,
        *,
        channel_type: str = "EBAY",
        template_idx: str = "",
        profile_idx: str = "",
    ) -> dict[str, Any]:
        """用刊登编号创建数据表（封存文档里验证过的接口）。

        先过协议门禁 `mode=agree`，再调 `mode=create_datasheet_from_listing_spy`。
        注意：`res_flag=0` 不代表内容是真的，调用方仍需校验返回标题。
        """

        page = await self._ensure_page()
        request = page.context.request
        ajax = f"{self.base_url}/app/soldeazy/datasheet_ajax"

        await request.post(ajax, form={"mode": "agree"}, timeout=60_000)
        response = await request.post(
            ajax,
            form={
                "mode": "create_datasheet_from_listing_spy",
                "channel_type": channel_type,
                "item_ids": item_ids,
                "shop_idx": str(shop_idx),
                "template_idx": template_idx,
                "profile_idx": profile_idx,
            },
            timeout=180_000,
        )
        text = (await response.text()).lstrip("\ufeff").strip()
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise EbayMcpError(
                "SOLDEAZY_CREATE_BAD_RESPONSE",
                "创建接口返回的不是 JSON",
                details={"head": text[:200]},
            ) from exc

        items = payload if isinstance(payload, list) else [payload]
        summary = []
        for item in items:
            dsheet = item.get("res_dsheet") or {}
            summary.append(
                {
                    "item_id": item.get("res_item_id"),
                    "rowid": item.get("res_rowid"),
                    "flag": item.get("res_flag"),
                    "message": item.get("res_message"),
                    "title": dsheet.get("dsheet_titleexternal") or dsheet.get("dsheet_titleinternal"),
                    "site": dsheet.get("dsheet_sitecode"),
                    "product_code": dsheet.get("dsheet_product_code"),
                }
            )
        return {"success": True, "created": len(summary), "items": summary}

    async def upload_via_api(self, path: Path) -> dict[str, Any]:
        """用页面同款接口上传 _done.xlsx（multipart，字段 filePackage）。

        与点页面等价，但省掉 UI 等待，返回服务端的 `handle` 便于后续追踪。
        """

        page = await self._ensure_page()
        payload = path.read_bytes()
        response = await page.context.request.post(
            f"{self.base_url}{UPLOAD_PATH}/upload",
            multipart={
                "filePackage": {
                    "name": path.name,
                    "mimeType": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                    "buffer": payload,
                }
            },
            timeout=120_000,
        )
        if response.status != 200:
            raise EbayMcpError(
                "SOLDEAZY_UPLOAD_FAILED",
                f"上传接口返回 HTTP {response.status}",
            )
        # 服务端会带 UTF-8 BOM，直接 response.json() 会炸
        text = (await response.text()).lstrip("\ufeff").strip()
        body = json.loads(text) if text else {}
        handle = (body.get("handle") or {}) if isinstance(body, dict) else {}
        return {
            "success": True,
            "path": str(path),
            "file": path.name,
            "handle": handle.get(path.name),
            "response": body,
        }

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
    """Map logical field names to column indexes using the table header.

    真机表头会把文字折行（`数据表\n编号`），所以比对前先把空白全部去掉。
    """

    def squash(value: object) -> str:
        return re.sub(r"\s+", "", str(value or ""))

    normalized = [squash(cell) for cell in header]
    mapping: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        wanted = {squash(alias) for alias in aliases}
        for index, cell in enumerate(normalized):
            if cell in wanted:
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


def parse_rows(rows: Sequence[Sequence[str]]) -> tuple[list[str], list[dict[str, Any]]]:
    """把 `#tbl_dSheet` 的单元格矩阵解析成数据表记录。

    真机实测的坑（2026-11-02）：表头 14 个 `th`，数据行却是 15~16 个 `td`
    （多出勾选框、重复标题格），**按表头下标取列会整体串位**；筛选前后列数还会变。
    这里改用内容锚定：

    * 行尾 5 列固定为 `SKU / 价格 / 运费 / 促销刊登 / eBay促销`，用负下标取；
    * 站点按内容识别（US / UK / Germany…），渠道账号取站点左边那一格；
    * 数据表编号取前 6 格里第一个 6 位以上数字。
    """

    def tidy(value: object) -> str:
        # 只压缩空格/制表符，保留换行——多属性行的变体是靠换行分隔的
        return re.sub(r"[ \t]+", " ", str(value or "")).strip()

    cleaned = [[tidy(cell) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return [], []

    header = cleaned[0]
    records: list[dict[str, Any]] = []
    site_names = {name.upper() for name in SITE_LABELS.values()} | set(SITE_LABELS)

    for cells in cleaned[1:]:
        if len(cells) < 8:            # 变体展开行
            continue
        rowid = ""
        for cell in cells[:6]:
            if cell.isdigit() and len(cell) >= 6:
                rowid = cell
                break
        if not rowid:
            continue

        def tail(offset: int) -> str:
            return cells[-offset] if len(cells) >= offset else ""

        site = ""
        site_index = -1
        for index in range(4, min(9, len(cells))):
            token = cells[index].strip().upper()
            if token and (token in site_names or token in SITE_CODES):
                site, site_index = cells[index].strip(), index
                break
        shop = cells[site_index - 1] if site_index > 0 else (cells[5] if len(cells) > 5 else "")

        sku_raw = tail(5)
        price_raw = tail(4)
        postage_raw = tail(3)
        sku_lines = [line.strip() for line in sku_raw.splitlines() if line.strip()]
        price_lines = [line.strip() for line in price_raw.splitlines() if line.strip()]

        records.append(
            {
                "rowid": rowid,
                "shop": " ".join(shop.split()),
                "site": site,
                "title": cells[7] if len(cells) > 7 else "",
                "sku": sku_lines[0] if sku_lines else "",
                "price": _number(price_lines[0]) if price_lines else None,
                "postage": _number(postage_raw.splitlines()[0]) if postage_raw else None,
                "variants": len(sku_lines),
            }
        )

    return header, records
