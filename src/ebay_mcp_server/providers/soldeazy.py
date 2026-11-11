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
import html as htmllib
import importlib.util
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError

logger = logging.getLogger("ebay_mcp.soldeazy")

BASE_URL = "https://stiger.soldeazy.com"
LIST_PATH = "/app/soldeazy/datasheet/dsheet_list?default_search_profile"
# 无头模式默认的 Chrome UA 会带 HeadlessChrome 字样，
# 站点可能把会话绑在 UA 上，导致「有头登录完、无头用不了」。
# 这里统一用常规桌面 UA，切换模式时登录态才能复用。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

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
    "login_remember": Locator(
        "记住用户名",
        '//form//input[@type="checkbox"]',
        "input[name=login_remember_username]",
    ),
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


def _shop_scope_hint(shop: str, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """如实说明这次搜索到底按哪个店铺过滤了。

    2026-11-11 踩到的坑：既没传 ``shop`` 也没有 active shop 时，``search`` 不加任何
    店铺过滤，返回的是平台默认店铺的数据（实测那次是 ``EBAY TAY``）。
    调用方很容易把它当成自己指定的账号，所以这里把过滤状态和实际店铺都回传。
    """

    scoped = bool((shop or "").strip())
    hint: dict[str, Any] = {
        "shop_filter": shop if scoped else "(未设置：平台默认店铺，可能不是你的账号)",
        "shop_filter_applied": scoped,
    }
    if records:
        seen = sorted({str(row.get("shop") or "").strip() for row in records} - {""})
        hint["shops_in_result"] = seen
        hint["shop_scope_mismatch"] = bool(
            scoped and seen and any(name != shop and shop not in name for name in seen)
        )
    return hint


def launch_error(
    directory: Path,
    errors: list[str],
    tried: list[str] | None = None,
    idle_seconds: float = 300.0,
) -> EbayMcpError:
    """把浏览器启动失败分类成可操作的错误。

    三类：profile 被别的进程占用 / 权限被拒 / 真的没浏览器。
    第一类最常见也最容易被误解成"装坏了"：Chromium 一个 user-data-dir
    同时只允许一个进程打开，所以 stdio 模式下第二个会话必然抢不到。
    """

    joined = " ".join(errors)
    lowered = joined.lower()
    locked = any(
        word in lowered
        for word in (
            "processsingleton",
            "singletonlock",
            "singleton",
            "already in use",
            "is already running",
        )
    ) or ("lock" in lowered and "profile" in lowered)
    if locked:
        return EbayMcpError(
            "SOLDEAZY_PROFILE_LOCKED",
            f"浏览器 profile 已被另一个进程占用：{directory}。"
            "Chromium 一个 user-data-dir 同时只允许一个进程打开，"
            "所以同一时间只有一个会话能用 Soldeazy 工具——"
            "这与 MCP 是否全局安装无关：stdio 模式下每个会话各自起一个服务进程，"
            "第二个进程抢不到 profile。"
            f"占用方空闲 {idle_seconds:.0f} 秒后会自动释放这把锁"
            "（SOLDEAZY_BROWSER_IDLE_SECONDS，0=不释放），稍等重试通常即可；"
            "要多会话实时共用，请改用一个常驻服务（ebay-mcp-server --transport sse）"
            "让所有会话连同一个进程；或给每个会话配不同的 SOLDEAZY_PROFILE_DIR。",
            details={"attempts": errors},
        )
    if any(
        word in joined
        for word in ("Permission", "EPERM", "Access is denied", "拒绝访问", "EACCES")
    ):
        return EbayMcpError(
            "SOLDEAZY_BROWSER_LAUNCH_DENIED",
            "浏览器已找到，但启动被拒绝（权限/沙箱）。"
            f"进程需要对 profile 目录 {directory} 和临时目录有写权限；"
            "如果 MCP 跑在沙箱里，请把这两个目录加入白名单，"
            "或把它们指到工作区内的可写路径。",
            details={"attempts": errors},
        )
    return EbayMcpError(
        "SOLDEAZY_BROWSER_LAUNCH_FAILED",
        "浏览器启动失败：本机没有可用的 Chrome / Edge / Chromium。"
        "最省事的修法是执行 uv run playwright install chromium，"
        "装好后重试即可；也可以安装 Chrome 或 Edge。",
        details={
            "tried": tried or [],
            "attempts": errors,
            "hint": "LOCALAPPDATA=" + (os.environ.get("LOCALAPPDATA") or "(未设置)"),
        },
    )


def looks_logged_in(html: str) -> bool:
    """用页面 HTML 判断 cookie 是否还有效（不开浏览器的轻量校验）。

    登录页有密码输入框；已登录的数据表页有 ``#tbl_dSheet``。
    两个标记都不在时保守返回 False。
    """

    lowered = html.lower()
    if "tbl_dsheet" in lowered:
        return True
    if 'type="password"' in lowered or 'name="password"' in lowered:
        return False
    return False


_FORM_CONTROL = re.compile(
    r"<select\b.*?</select>|<input\b[^>]*>|<textarea\b.*?</textarea>",
    re.S | re.I,
)
_OPTION = re.compile(r"<option\b([^>]*)>(.*?)</option>", re.S | re.I)
_ATTR = re.compile(r"(\w[\w-]*)\s*=\s*[\"']([^\"']*)[\"']", re.I)
_CELL = re.compile(r"<t[dh]\b.*?</t[dh]>", re.S | re.I)
_ROW = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _tag_attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _ATTR.finditer(tag)}


def parse_form_state(html: str) -> dict[str, list[str]]:
    """把搜索表单的当前状态读成 ``{name: [values]}``（多选/重名保留多值）。

    和浏览器提交时的序列化口径一致：checkbox/radio 只取 checked，
    select 取 selected（一个都没有就取第一项），hidden/text 取 value。
    定位方式是找含 ``btn_search`` 的那个 form——页面有嵌套 form，
    按 ``<form>...</form>`` 直接切会切错。
    """

    anchor = html.find("btn_search")
    if anchor < 0:
        return {}
    start = html.rfind("<form", 0, anchor)
    end = html.find("</form>", anchor)
    if start < 0 or end < 0:
        return {}
    block = html[start:end]

    state: dict[str, list[str]] = {}

    def add(name: str, value: str) -> None:
        if not name:
            return
        state.setdefault(name, []).append(value)

    for match in _FORM_CONTROL.finditer(block):
        tag = match.group(0)
        head = tag[: tag.find(">") + 1]
        attrs = _tag_attrs(head)
        name = attrs.get("name", "")
        kind = tag.split()[0][1:].lower()
        if kind == "select":
            options = _OPTION.findall(tag)
            picked = [
                (_tag_attrs(raw).get("value", htmllib.unescape(_TAG.sub("", body)).strip()))
                for raw, body in options
                if "selected" in raw.lower()
            ]
            if not picked and options:
                first_raw, first_body = options[0]
                picked = [
                    _tag_attrs(first_raw).get(
                        "value", htmllib.unescape(_TAG.sub("", first_body)).strip()
                    )
                ]
            for value in picked:
                add(name, value)
        elif kind == "textarea":
            add(name, htmllib.unescape(_TAG.sub("", tag[tag.find(">") + 1 :])).strip())
        else:
            input_type = (attrs.get("type") or "text").lower()
            if input_type in {"submit", "button", "image", "reset"} and name != "btn_search":
                continue
            if input_type in {"checkbox", "radio"} and "checked" not in head.lower():
                continue
            add(name, attrs.get("value", ""))
    return state


def cell_text_from_html(cell: str) -> str:
    """<td> 片段转单元格文本：<br> 是变体分隔符，要变成换行。"""

    text = re.sub(r"<br\s*/?>", "\n", cell, flags=re.I)
    text = _TAG.sub("", text)
    return htmllib.unescape(text).strip()


def parse_result_table(html: str) -> list[list[str]]:
    """从搜索结果 HTML 里抠出 ``#tbl_dSheet`` 的单元格矩阵（含表头行）。

    两个真机坑（2026-11-11）：
    - 单元格里嵌着子表格，非贪心的 ``.*?</table>`` 会在子表格处截断；
    - 数据行里也嵌着 ``<tr>``（变体/标题子表），非贪心的 ``.*?</tr>`` 会把
      外层行在嵌套 ``</tr>`` 处切断，丢掉尾部 SKU/价格列。
    表格和行都按嵌套深度切；单元格则保留全部后代 td/th 的文档序——
    与 DOM 通道 ``locator("th,td")`` 的口径一致。
    """

    match = re.search(r"<table\b[^>]*id=[\"']tbl_dSheet[\"']", html, re.I)
    if not match:
        return []
    block = _slice_table(html, match.start())
    return [
        [cell_text_from_html(cell) for cell in _CELL.findall(row)]
        for row in _top_level_rows(block)
    ]


def _top_level_rows(block: str) -> list[str]:
    """按 <tr> 嵌套深度切出顶层行（嵌套子表的行并入父行文本）。"""

    rows: list[str] = []
    depth = 0
    start = -1
    for match in re.finditer(r"<tr\b|</tr>", block, re.I):
        if match.group(0).lower().startswith("<tr"):
            depth += 1
            if depth == 1:
                start = match.start()
        else:
            depth -= 1
            if depth == 0 and start >= 0:
                rows.append(block[start : match.end()])
                start = -1
    return rows


def _slice_table(html: str, start: int) -> str:
    """从 start 处的 <table> 起，按嵌套深度切到配对的 </table>。"""

    depth = 0
    for match in re.finditer(r"<table\b|</table>", html[start:], re.I):
        depth += 1 if match.group(0).lower().startswith("<table") else -1
        if depth == 0:
            return html[start : start + match.end()]
    return html[start:]


def extract_total_records(html: str) -> int:
    """分页条上的总记录数（形如「1,636 笔记录」），读不到返回 0。"""

    match = re.search(r"([\d,]+)\s*笔记录", html)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def extract_sql_token(html: str) -> str:
    """搜索页里的 ``sql_cache_token``（单双引号都见过），同步接口要用。"""

    match = re.search(
        r"name=[\"']sql_cache_token[\"'][^>]*value=[\"']([^\"']*)[\"']", html, re.I
    )
    if match:
        return htmllib.unescape(match.group(1))
    match = re.search(
        r"value=[\"']([^\"']*)[\"'][^>]*name=[\"']sql_cache_token[\"']", html, re.I
    )
    return htmllib.unescape(match.group(1)) if match else ""


def parse_shop_options(html: str) -> list[dict[str, str]]:
    """从列表页 HTML 里读渠道账号下拉（``listshop[]``）的选项。"""

    match = re.search(r"<select\b[^>]*name=[\"']listshop\[\][\"'].*?</select>", html, re.S | re.I)
    if not match:
        return []
    options = []
    for raw, body in _OPTION.findall(match.group(0)):
        attrs = _tag_attrs(raw)
        value = attrs.get("value", "")
        name = htmllib.unescape(_TAG.sub("", body)).strip()
        if value and name:
            options.append({"id": value, "name": name})
    return options


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
        #: 最近一次 read_datasheet_values 导出的数据里出现的渠道账号名。
        #: 对账时要靠它确认"读的是不是计划所属的店铺"，否则没设 active_shop 时
        #: 会读到平台默认店铺，把每一行都判成查不到。
        self.last_export_shops: list[str] = []
        self._last_query: str = ""
        self._last_site: str = ""
        self._last_status: str = ""
        self._last_status_value: str = ""
        self._last_date: str = ""
        self._last_date_value: str = ""
        #: 最近一次搜索页下发的同步令牌；同步接口必须用它，不能沿用旧值
        self._last_sql_token: str = ""
        self.browser_channel_used: str = ""
        self.session_save_error: str = ""
        self.session_cookie_count: int = 0
        #: 空闲自动释放：最后一次碰浏览器的时间 + 挂着的释放任务
        self._last_used: float = time.monotonic()
        self._idle_task: asyncio.Task | None = None

    # ---------- 浏览器空闲释放 ----------
    def _touch(self) -> None:
        """记录"浏览器刚被用过"，并把空闲释放的计时器往后推。"""

        self._last_used = time.monotonic()
        self._schedule_idle_release()

    def _schedule_idle_release(self) -> None:
        idle = float(self.settings.soldeazy_browser_idle_seconds or 0)
        if idle <= 0:
            return
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        try:
            self._idle_task = asyncio.ensure_future(self._idle_release(idle))
        except RuntimeError:  # 没有事件循环（纯单测里直接构造对象）
            self._idle_task = None

    async def _idle_release(self, idle: float) -> None:
        """空闲满 idle 秒就关浏览器、交还 profile 锁。

        关闭前先落盘 cookie（close() 里做），所以下一个抢到锁的进程
        不用重新登录。正在跑 search（持有 _lock）时顺延一轮，不掐业务。
        """

        await asyncio.sleep(idle)
        if self._context is None:
            return
        if self._lock.locked():
            self._schedule_idle_release()
            return
        logger.info("Soldeazy 浏览器空闲 %.0f 秒，释放 profile 锁", idle)
        # 先摘引用再关：close() 会取消 _idle_task，不能取消正在运行的自己
        self._idle_task = None
        await self.close()

    # ---------- 生命周期 ----------
    @property
    def profile_dir(self) -> Path | None:
        raw = (self.settings.soldeazy_profile_dir or "").strip()
        return Path(raw).expanduser() if raw else None

    def profile_ready(self) -> bool:
        directory = self.profile_dir
        return bool(directory and directory.is_dir() and any(directory.iterdir()))

    async def status(self) -> dict[str, Any]:
        session_file = self._session_file() if self.profile_dir else None
        session_cookies = 0
        if session_file and session_file.is_file():
            try:
                session_cookies = len(json.loads(session_file.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                session_cookies = -1  # 文件坏了
        return {
            "name": "soldeazy",
            "base_url": self.base_url,
            "playwright_installed": _selector_available(),
            "profile_dir": str(self.profile_dir) if self.profile_dir else "",
            "profile_ready": self.profile_ready(),
            "credentials_configured": bool(
                self.settings.soldeazy_username and self.settings.soldeazy_password
            ),
            "session_file": str(session_file) if session_file else "",
            "session_file_exists": bool(session_file and session_file.is_file()),
            "session_cookie_count": session_cookies,
            # 不开浏览器问一次站点：cookie 还活着吗。文件不存在直接 False，不发请求。
            "session_valid": (
                await self.session_alive_http()
                if session_file and session_file.is_file()
                else False
            ),
            "session_save_error": self.session_save_error,
            "write_enabled": self.settings.soldeazy_write_enabled,
            "browser_open": self._page is not None,
            "browser_channel_configured": self.settings.soldeazy_browser_channel or "(内置 Chromium)",
            "browser_channel_used": self.browser_channel_used or "(未启动)",
            "browser_idle_release_seconds": self.settings.soldeazy_browser_idle_seconds,
            "headless": self.settings.soldeazy_headless,
            "dirs": self.dir_health(),
        }

    async def _launch_context(self, directory: Path) -> Any:
        """按候选计划逐个尝试启动浏览器，成功后记住选择。

        站点本身不挑浏览器；换机器、没装 Chrome、Playwright 版本不匹配，
        都不该让整条链路失败。
        """

        from ebay_mcp_server.providers import soldeazy_browser as browser_probe

        configured = (self.settings.soldeazy_browser_channel or "").strip()
        plan = browser_probe.build_plan(configured)
        plan = browser_probe.reorder(plan, browser_probe.load_cache(directory))

        errors: list[str] = []
        for step in plan:
            label = step["label"]
            kwargs: dict[str, Any] = {
                "headless": self.settings.soldeazy_headless,
                "args": ["--disable-blink-features=AutomationControlled"],
                "locale": "zh-CN",
            }
            if self.settings.soldeazy_headless:
                # 固定 UA：否则无头用 HeadlessChrome UA，站点会把登录态当成新会话
                kwargs["user_agent"] = DESKTOP_UA
            if step["executable"]:
                kwargs["executable_path"] = step["executable"]
            elif step["channel"]:
                kwargs["channel"] = step["channel"]
            try:
                context = await self._playwright.chromium.launch_persistent_context(
                    str(directory), **kwargs
                )
                self.browser_channel_used = label
                browser_probe.save_cache(directory, step)
                return context
            except Exception as exc:  # noqa: BLE001 - 换下一个候选
                errors.append(f"{label}: {str(exc).splitlines()[0][:150]}")

        # 分清「没装浏览器」和「装了但起不来（权限/沙箱/被占用）」，别用一句话糊弄过去
        raise launch_error(
            directory,
            errors,
            tried=[step["label"] for step in plan],
            idle_seconds=self.settings.soldeazy_browser_idle_seconds,
        )

    async def _ensure_page(self) -> Any:
        self._touch()
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
        self._ensure_temp_dirs()

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._context = await self._launch_context(directory)
        await self._restore_session()
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        self._page.set_default_timeout(self.settings.soldeazy_navigation_timeout * 1000)
        return self._page

    @staticmethod
    def _ensure_temp_dirs() -> None:
        """TEMP/TMP 指向的目录必须先存在，否则 Playwright 解压内核时会 EPERM。

        新机器常见坑：配置里写了 TEMP=C:\\...\\temp，但这个目录没人建。
        """

        for name in ("TEMP", "TMP", "TMPDIR"):
            raw = (os.environ.get(name) or "").strip()
            if not raw:
                continue
            try:
                Path(raw).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def dir_health(self) -> dict[str, Any]:
        """报告 profile 与临时目录是否可写——部署到新机器时最常用的一次自检。"""

        def probe(directory: Path | None) -> dict[str, Any]:
            if directory is None:
                return {"path": "", "exists": False, "writable": False}
            try:
                directory.mkdir(parents=True, exist_ok=True)
                probe_file = directory / ".write_probe"
                probe_file.write_text("ok", encoding="utf-8")
                probe_file.unlink()
                writable = True
            except OSError as exc:
                return {
                    "path": str(directory),
                    "exists": directory.is_dir(),
                    "writable": False,
                    "error": f"{type(exc).__name__}: {exc}"[:150],
                }
            return {"path": str(directory), "exists": True, "writable": writable}

        temp_raw = (os.environ.get("TEMP") or "").strip()
        return {
            "profile": probe(self.profile_dir),
            "temp": probe(Path(temp_raw) if temp_raw else None),
        }

    def _session_file(self) -> Path:
        return self.profile_dir / "session_cookies.json"

    def _cookie_dict(self) -> dict[str, str]:
        """读落盘 cookie，变成 {name: value}。没有/坏了就返回空。"""

        path = self._session_file() if self.profile_dir else None
        if path is None or not path.is_file():
            return {}
        try:
            cookies = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {
            str(item.get("name")): str(item.get("value"))
            for item in cookies
            if isinstance(item, dict) and item.get("name")
        }

    def _http_client(self) -> Any:
        """不依赖浏览器的 HTTP 客户端：cookie 直接来自落盘文件。

        导出/上传/工序查询这些步骤本来就只有"cookie + 表单"两样东西，
        之前借 page.context.request 只是借 cookie。浏览器被空闲释放后，
        这些步骤仍能继续跑，不必重新抢 profile 锁。
        """

        import httpx

        return httpx.AsyncClient(
            cookies=self._cookie_dict(),
            headers={"User-Agent": DESKTOP_UA},
            follow_redirects=True,
            timeout=180.0,
        )

    async def session_alive_http(self) -> bool:
        """不开浏览器，用落盘 cookie 问一次站点：登录态还活着吗。"""

        if not self._cookie_dict():
            return False
        async with self._http_client() as client:
            try:
                response = await client.get(f"{self.base_url}{LIST_PATH}")
            except Exception:  # noqa: BLE001 - 网络不通当作失效
                return False
        return looks_logged_in(response.text)

    async def _save_session(self) -> None:
        """把 cookie 落盘（含会话级 _ht_ses_），重启后仍能复用登录态。

        写盘失败不能静默——那正是"cookie 存不下来、每次都要重新登录"的根因，
        失败原因记在 ``session_save_error`` 里，由 status 暴露出来。
        """

        self.session_save_error = ""
        if self._context is None:
            self.session_save_error = "浏览器上下文未启动，跳过了 cookie 落盘"
            return
        try:
            cookies = await self._context.cookies()
            self.session_cookie_count = len(cookies)
            self._session_file().write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001 - 记录但不再吞掉
            self.session_save_error = f"{type(exc).__name__}: {exc}"[:200]

    async def _restore_session(self) -> None:
        path = self._session_file()
        if self._context is None or not path.exists():
            return
        try:
            cookies = json.loads(path.read_text(encoding="utf-8"))
            if cookies:
                await self._context.add_cookies(cookies)
        except Exception:  # noqa: BLE001 - 文件坏了就当没有
            pass

    async def close(self) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None
        if self._context is not None:
            await self._save_session()
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = self._page = self._playwright = None

    # ---------- 基础动作 ----------
    async def _locate(self, key: str, timeout: int = 8000) -> Any:
        page = await self._ensure_page()
        entry = SELECTORS[key]
        last: Exception | None = None
        for selector in entry.candidates():
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
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

    async def _goto(self, url: str, *, attempts: int = 3) -> None:
        """打开页面并重试：站点偶发超时会让整条流程误报成业务错误。"""

        page = await self._ensure_page()
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                return
            except Exception as exc:  # noqa: BLE001 - 网络抖动重试
                last = exc
                if attempt < attempts:
                    await asyncio.sleep(2 * attempt)
        raise EbayMcpError(
            "SOLDEAZY_NAV_FAILED",
            f"打开页面失败（已重试 {attempts} 次）：{url}",
            details={"error": str(last)[:160]},
        )

    # ---------- 登录 ----------
    async def _session_alive(self) -> bool:
        """用现有 cookie 探一下列表页；不碰登录框，也不触发登录。"""

        page = await self._ensure_page()
        try:
            await self._goto(f"{self.base_url}{LIST_PATH}")
            await asyncio.sleep(1.0)
        except Exception:  # noqa: BLE001 - 网络问题交给上层重试
            return False
        if "/login" in (page.url or "").lower():
            return False
        return await page.evaluate(
            "() => !!document.querySelector('select') || !!document.querySelector('#tbl_dSheet')"
        )

    async def interactive_login(self) -> dict[str, Any]:
        page = await self._ensure_page()

        # 先探活：cookie 还有效就直接复用，连登录页都不打开
        if await self._session_alive():
            await self._dismiss_popup()
            return {
                "success": True,
                "reused_session": True,
                "url": page.url,
                "profile_dir": str(self.profile_dir),
            }

        await self._goto(f"{self.base_url}{LOGIN_PATH}")
        await asyncio.sleep(2)
        await self._dismiss_popup()

        # profile 里已有会话时，站点直接跳过登录页——绝不再登一次
        if "/login" not in (page.url or "").lower():
            await self._goto(f"{self.base_url}{LIST_PATH}")
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
            # 「记住用户名」不勾，登录态撑不过一次重启——这是会话丢失的根因
            try:
                remember = await self._locate("login_remember", timeout=3000)
                if not await remember.is_checked():
                    await remember.check(timeout=3000)
            except Exception:  # noqa: BLE001 - 没有这个勾选框就照常登录
                pass
            await (await self._locate("login_submit")).click()
        else:
            # 无凭据：无头模式下没有窗口可点，别干等——直接给出可执行的下一步
            if self.settings.soldeazy_headless:
                raise EbayMcpError(
                    "SOLDEAZY_CREDENTIALS_MISSING",
                    "当前是无头模式且没有配置凭据，无法自动登录，也没有窗口可人工登录。"
                    "请在 .env 设置 SOLDEAZY_USERNAME / SOLDEAZY_PASSWORD；"
                    "或设 SOLDEAZY_HEADLESS=0 后调用 soldeazy_open_login 手动登录一次，"
                    "登录态会写入 profile，之后改回无头仍然可用。",
                    details={
                        "headless": True,
                        "profile_dir": str(self.profile_dir),
                        "profile_ready": self.profile_ready(),
                    },
                )
            # 有窗口：留给人工，最多等 120 秒
            deadline = min(120.0, self.settings.soldeazy_navigation_timeout * 4)
            await self._wait_logged_in(page, deadline)

        await self._wait_logged_in(page, self.settings.soldeazy_navigation_timeout * 2)
        await self._goto(f"{self.base_url}{LIST_PATH}")
        await self._dismiss_popup()
        await self._save_session()
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
    async def search(
        self, sku_terms: str, site: str, shop: str = "", *, only_listed: bool = True
    ) -> dict[str, Any]:
        """搜索并读回结果。**HTTP 通道优先**（不碰浏览器、不抢 profile 锁），
        HTTP 不可用时回退 DOM 通道。

        `only_listed` 默认开启：只搜「已刊登」的数据表。
        改价/改库存只对已刊登的有意义——未刊登的同步不到 eBay，
        混进来只会让上传数和同步数对不上。
        """

        self._last_query = sku_terms or ""
        self._last_site = site or ""
        shop = shop or ((self.active_shop or {}).get("name") or "")
        async with self._lock:
            try:
                return await self._search_via_http(sku_terms, site, shop, only_listed)
            except EbayMcpError as exc:
                if exc.code == "SOLDEAZY_LOGIN_REQUIRED":
                    raise
                logger.warning("HTTP 搜索失败（%s），回退 DOM 通道", exc.code)
            except Exception as exc:  # noqa: BLE001 - 回退总比整条链路死掉好
                logger.warning("HTTP 搜索异常（%s），回退 DOM 通道", type(exc).__name__)
            return await self._search_via_page(sku_terms, site, shop, only_listed)

    async def _search_via_http(
        self, sku_terms: str, site: str, shop: str, only_listed: bool, *, limit: int = 200
    ) -> dict[str, Any]:
        """和浏览器做的一模一样：GET 列表页拿表单当前状态 → 改筛选 → POST。

        比 DOM 通道还多两个好处：结果表是服务端渲染的完整 200 行/页
        （DOM 通道受虚拟化影响只能读到约 65 行），以及顺带拿到
        ``sql_cache_token`` 供同步接口使用。
        """

        shop_id = ""
        if shop:
            known = {o["name"]: o["id"] for o in await self.list_shop_options()}
            shop_id = known.get(shop, "")
            if not shop_id:
                upper = shop.upper()
                for name, oid in known.items():
                    if upper in name.upper():
                        shop_id = oid
                        break

        status_value = "All" if only_listed else ""
        self._last_status = "已刊登(所有)" if only_listed else "(空=全部)"
        self._last_status_value = status_value
        self._last_date = "(空)"
        self._last_date_value = ""

        async with self._http_client() as client:
            got = await client.get(f"{self.base_url}{LIST_PATH}")
            if not looks_logged_in(got.text):
                raise EbayMcpError(
                    "SOLDEAZY_LOGIN_REQUIRED",
                    "cookie 缺失或已失效：先调 soldeazy_open_login 登录一次。",
                    details={"session_file": str(self._session_file())},
                )
            state = parse_form_state(got.text)
            overrides = {
                "txtproductcode": sku_terms or "",
                "listshop[]": shop_id,
                "listsite": SITE_CODES.get((site or "").strip().upper(), "") if site else "",
                "listactive": status_value,
                "listdate": "",
                "page": "1",
                "limit": str(max(1, min(int(limit), 200))),
            }
            pairs: list[tuple[str, str]] = [
                (name, value)
                for name, values in state.items()
                if name not in overrides
                for value in values
            ]
            pairs.extend(overrides.items())
            pairs.append(("table_action", "show"))
            pairs.append(("mode", "dsheet_list"))

            html = ""
            for url in (
                f"{self.base_url}/app/soldeazy/datasheet",
                f"{self.base_url}/app/soldeazy/datasheet/dsheet_list",
            ):
                # 重名字段（listshop[] / view_profile[] / search_filters[]）必须保留多值，
                # 而 httpx 的 AsyncClient 对 data=list 会生成同步流直接报错，
                # 所以自己 urlencode 成 content 发。
                posted = await client.post(
                    url,
                    content=urlencode(pairs).encode("utf-8"),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                # 只有真的 <table id=tbl_dSheet> 才算搜到了；CSS 里也出现过
                # 这个 id（选择器文本），不能用子串判断。
                if posted.status_code == 200 and re.search(
                    r"<table\b[^>]*id=[\"']tbl_dSheet[\"']", posted.text, re.I
                ):
                    html = posted.text
                    break
            if not html:
                raise EbayMcpError(
                    "SOLDEAZY_HTTP_SEARCH_FAILED",
                    "HTTP 搜索两个候选地址都没拿回结果表，回退 DOM 通道。",
                )

        self._last_sql_token = extract_sql_token(html)
        matrix = parse_result_table(html)
        if not matrix:
            return {
                "site": site,
                "shop": shop,
                "search": sku_terms,
                "status_filter": self._last_status,
                "columns": [],
                "row_count": 0,
                "rows": [],
                "page_limit": int(overrides["limit"]),
                "total_records": extract_total_records(html),
                **_shop_scope_hint(shop),
                "empty_reason": (
                    "没有匹配的数据表"
                    + ("（当前只查已刊登，可能被状态过滤掉了）" if only_listed else "")
                ),
            }
        header, records = parse_rows(matrix)
        return {
            "site": site,
            "shop": shop,
            "search": sku_terms,
            "status_filter": self._last_status,
            "date_filter": self._last_date,
            "columns": header,
            "row_count": len(records),
            "rows": records,
            "page_limit": int(overrides["limit"]),
            "total_records": extract_total_records(html),
            **_shop_scope_hint(shop, records),
        }

    async def _search_via_page(
        self, sku_terms: str, site: str, shop: str, only_listed: bool
    ) -> dict[str, Any]:
        """DOM 通道（回退用）：调用方已持有 ``self._lock``。"""

        page = await self._ensure_page()
        await self._goto(f"{self.base_url}{LIST_PATH}")
        await self._dismiss_popup()

        await (await self._locate("search_sku")).fill(sku_terms)
        if site:
            await self._select_site(site)
        if shop:
            await self._select_shop(shop)
        # 修改日期默认留空，避免沿用上次筛选导致漏数据
        await self._clear_date_filter()
        # 改价/改库存只对「已刊登」有意义：未刊登的数据表同步不到 eBay，
        # 传上去只会让上传数和同步数对不上。
        if only_listed:
            await self._select_status_listed()
        else:
            # 不限状态时必须把档位清回空（=全部）：页面 select 会沿用上次的值，
            # 不清的话 include_unlisted=true 实际仍按「已刊登」过滤。
            await self._select_status_all()
        await self._select_scope_whole_result()
        await (await self._locate("search_button")).click()
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(self.settings.soldeazy_min_delay)

        try:
            table = await self._locate("result_table")
        except EbayMcpError:
            # 没有结果表 = 这次搜索 0 条，不是错误。
            # 典型场景：只查「已刊登」但该账号全是未刊登。
            return {
                "site": site,
                "shop": shop,
                "search": sku_terms,
                "status_filter": self._last_status
                or ("已刊登" if only_listed else "不限"),
                "columns": [],
                "row_count": 0,
                "rows": [],
                **_shop_scope_hint(shop),
                "empty_reason": (
                    "没有匹配的数据表"
                    + ("（当前只查已刊登，可能被状态过滤掉了）" if only_listed else "")
                ),
            }

        # 搜索提交会把每页条数重置回 25，所以要在搜索**之后**调大页；
        # 调档是 AJAX 重拉，会保留本次搜索条件（实测 308 笔不变）。
        # 注意（2026-11-11 实机）：调档的 AJAX 重拉会换掉导出按钮的点击绑定，
        # 之后再点「导出」弹层不再出现。所以 search 里**只读不改**，
        # 真正需要大页的勾选动作在 select_datasheets 里自己调档。
        page_limit = await self._read_page_limit()
        table = await self._locate("result_table")
        trs = table.locator("tr")
        total = await trs.count()
        cell_rows: list[list[str]] = []
        for index in range(total):
            cells = await trs.nth(index).locator("th,td").all_inner_texts()
            cell_rows.append(cells)  # 原样交给 parse_rows：换行是变体分隔符
        header, records = parse_rows(cell_rows)
        self._last_sql_token = await self._eval_with_retry(
            page,
            "() => ((document.querySelector('input[name=sql_cache_token]')||{}).value || '')",
        )
        return {
            "site": site,
            "shop": shop,
            "search": sku_terms,
            "status_filter": self._last_status or ("已刊登" if only_listed else "不限"),
            "date_filter": self._last_date or "(空)",
            "columns": header,
            "row_count": len(records),
            "rows": records,
            "page_limit": page_limit,
            "total_records": await self._read_total_records(),
            **_shop_scope_hint(shop, records),
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

        if self._context is None:
            # 免浏览器：渠道账号列表就在列表页 HTML 里，不必为它抢 profile 锁
            async with self._http_client() as client:
                got = await client.get(f"{self.base_url}{LIST_PATH}")
            if not looks_logged_in(got.text):
                raise EbayMcpError(
                    "SOLDEAZY_LOGIN_REQUIRED",
                    "cookie 缺失或已失效：先调 soldeazy_open_login 登录一次。",
                    details={"session_file": str(self._session_file())},
                )
            return parse_shop_options(got.text)

        page = await self._ensure_page()
        if not (page.url or "").startswith(self.base_url):
            await self._goto(f"{self.base_url}{LIST_PATH}")
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
        if not options:
            # 可能停在登录页：确保登录后再读一次
            await self.interactive_login()
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

    async def _select_page_limit(self, limit: int = 200) -> int:
        """把结果表每页条数调到最大档（实测档位 25/50/100/200，默认 25）。

        平台默认一页只渲染 25 行（308 笔记录分 13 页），而**勾选和同步只作用于
        渲染出来的行**——历史审计里"计划 209 个数据表、实际只勾选到 18 个"就是这个
        造成的。导出不受影响（走 whole_result），但搜索回显和勾选都吃这个亏。

        注意（2026-11-11 实测）：调档后 DOM 里确实会出现 200 行，但页面是虚拟化
        渲染的，视口外的行 `innerText` 读出来是空串，所以**搜索回显仍然只能读到
        约 60 来行**。要拿全量数据请走导出（``read_datasheet_values`` /
        ``export``，范围是 whole_result）；这里调档的意义是让勾选框覆盖更多行。
        返回实际设置的档位；找不到控件返回 0，不阻断。
        """

        page = await self._ensure_page()
        before = await page.evaluate(
            "() => document.querySelectorAll('#tbl_dSheet tr').length"
        )
        picked = await page.evaluate(
            """
            (wanted) => {
              const s = document.querySelector('.pagination select.limit');
              if (!s) return null;
              const values = Array.from(s.options)
                .map((o) => parseInt(o.value, 10))
                .filter((v) => !isNaN(v));
              if (!values.length) return null;
              const target = Math.min(wanted, Math.max(...values));
              if (String(target) !== s.value) {
                s.value = String(target);
                s.dispatchEvent(new Event('change', { bubbles: true }));
                if (window.jQuery) { try { jQuery(s).trigger('chosen:updated'); } catch (e) {} }
              }
              return target;
            }
            """,
            int(limit),
        )
        if picked:
            # 换档后表格异步重拉：等行数变化，等不到就按固定延时兜底
            try:
                await page.wait_for_function(
                    "(prev) => document.querySelectorAll('#tbl_dSheet tr').length !== prev",
                    before,
                    timeout=8000,
                    polling=300,
                )
            except Exception:  # noqa: BLE001 - 结果不足一页时行数本来就不变
                pass
            await asyncio.sleep(max(1.0, self.settings.soldeazy_min_delay / 2))
        return int(picked or 0)

    async def _read_page_limit(self) -> int:
        """只读当前每页条数档位，不做任何修改。"""

        page = await self._ensure_page()
        value = await self._eval_with_retry(
            page,
            "() => (document.querySelector('.pagination select.limit') || {}).value || ''",
        )
        try:
            return int(value)
        except ValueError:
            return 0

    async def _read_total_records(self) -> int:
        """读分页条上的总记录数（形如「308 笔记录」），读不到返回 0。"""

        page = await self._ensure_page()
        text = await self._eval_with_retry(
            page,
            """
            () => {
              const hits = Array.from(document.querySelectorAll('.pagination a, .pagination li'))
                .map((e) => (e.textContent || '').trim())
                .filter((t) => /\\d/.test(t) && t.length < 30);
              return hits[0] || '';
            }
            """,
        )
        digits = "".join(ch for ch in str(text or "") if ch.isdigit())
        return int(digits) if digits else 0

    async def _eval_with_retry(self, page: Any, script: str, arg: Any = None, *, tries: int = 4) -> Any:
        """页面 AJAX 重拉时 evaluate 会撞导航（context destroyed），重试即可。"""

        last: Exception | None = None
        for _ in range(tries):
            try:
                return await page.evaluate(script, arg) if arg is not None else await page.evaluate(script)
            except Exception as exc:  # noqa: BLE001 - 只吞导航竞态
                last = exc
                text = str(exc)
                if "destroyed" not in text and "navigation" not in text.lower():
                    raise
                await asyncio.sleep(2)
        raise last or EbayMcpError("SOLDEAZY_EVAL_FAILED", "页面脚本执行失败")

    async def _goto_next_page(self) -> bool:
        """翻到下一页；没有下一页（或按钮禁用）返回 False。"""

        page = await self._ensure_page()
        moved = await self._eval_with_retry(
            page,
            """
            () => {
              const a = document.querySelector('.pagination a.next.btn_goto:not(.disabled)');
              if (!a) return false;
              a.click();
              return true;
            }
            """,
        )
        if moved:
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(self.settings.soldeazy_min_delay)
        return bool(moved)

    async def _clear_date_filter(self) -> None:
        """修改日期默认留空，不沿用页面上次的值。找不到就跳过。"""

        page = await self._ensure_page()
        try:
            cleared = await page.evaluate(
                """
                () => {
                  const sel = Array.from(document.querySelectorAll('select'))
                    .find((x) => x.name === 'listdate');
                  if (!sel) return null;
                  const blank = Array.from(sel.options).find((o) => !(o.value || '').trim());
                  if (!blank) return null;
                  sel.value = blank.value;
                  sel.dispatchEvent(new Event('change', { bubbles: true }));
                  return { value: blank.value, text: (blank.textContent || '').trim() };
                }
                """
            )
            if cleared is not None:
                self._last_date = str(cleared.get("text") or "")
                self._last_date_value = str(cleared.get("value") or "")
        except Exception:  # noqa: BLE001 - 尽力而为，不阻断搜索
            pass

    async def _select_status_listed(self) -> None:
        """把状态筛成「已刊登(所有)」。找不到就跳过，不阻断搜索。"""

        page = await self._ensure_page()
        picked = await page.evaluate(
            """
            () => {
              const sel = Array.from(document.querySelectorAll('select'))
                .find((x) => x.name === 'listactive');
              if (!sel) return null;
              const options = Array.from(sel.options);
              // 英文界面 Listed(All)，中文界面 已刊登(所有)；排除 Unlisted / 未刊登
              const hit = options.find((o) => {
                const text = (o.textContent || '').trim();
                const lower = text.toLowerCase();
                if (lower.includes('unlisted') || text.includes('未刊登')) return false;
                return lower.includes('listed') || text.includes('已刊登');
              });
              if (!hit) return null;
              if (sel.value !== hit.value) {
                sel.value = hit.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
              }
              return { value: hit.value, text: (hit.textContent || '').trim() };
            }
            """
        )
        if picked:
            self._last_status = str(picked.get("text") or "")
            self._last_status_value = str(picked.get("value") or "")

    async def _select_status_all(self) -> None:
        """把状态档位清回空（= 全部）。页面 select 会沿用上次的值。"""

        page = await self._ensure_page()
        picked = await page.evaluate(
            """
            () => {
              const sel = Array.from(document.querySelectorAll('select'))
                .find((x) => x.name === 'listactive');
              if (!sel) return null;
              const blank = Array.from(sel.options).find((o) => !(o.value || '').trim());
              if (!blank) return null;
              if (sel.value !== blank.value) {
                sel.value = blank.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
              }
              return { value: blank.value, text: (blank.textContent || '').trim() };
            }
            """
        )
        if picked:
            self._last_status = str(picked.get("text") or "") or "(空=全部)"
            self._last_status_value = str(picked.get("value") or "")

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
    async def export_via_api(self, dest: Path, *, profile: str = "55") -> dict[str, Any]:
        """不导航页面，直接用会话 cookie 提交导出表单。

        2026-11-11 起作为**默认导出通道**：页面通道的弹层（`#jqizoo`）在部分
        会话下点「导出」后不出现（FUN 实机复现），而本通道的筛选参数直接取自
        最近一次 search（`_last_query` / `_last_site` / `_last_status_value` /
        `_last_date_value`），行集与计划一致，且实测一次拿到全量 7075 行。

        **浏览器被空闲释放后本通道仍可工作**：没有 context 时改用落盘 cookie
        的独立 HTTP 客户端，不再抢 profile 锁。cookie 失效会明确报
        ``SOLDEAZY_LOGIN_REQUIRED``，而不是让用户猜。
        """

        shop_id = (self.active_shop or {}).get("id", "")
        site_code = SITE_CODES.get((self._last_site or "").upper(), "")

        base_form = {
            "second_mode": "dsheet_list",
            "txtproductcode": self._last_query,
            "listshop[]": shop_id,
            "listsite": site_code,
            # 筛选条件必须和最近一次 search 完全一致，否则导出的行集对不上计划：
            # 日期默认留空（search 里清过），状态沿用 search 选中的档位
            # （only_listed=True 时是「已刊登(所有)」，False 时留空=全部）。
            "listdate": self._last_date_value or "",
            "listactive": self._last_status_value or "",
            "view_profile_id": "Default",
            "radioEditTypeValue": "schedule",
            "bulk_option_from": "1",
            "bulk_option_to": "1",
            "listExppf": profile,
            "listExpfmt": "xlsx",
        }
        # 实测：导出用的是 bulk-export + dsheet_datatable，不是搜索用的 show/dsheet_list
        extra = {
            "table_action": "bulk-export",
            "mode": "dsheet_datatable",
            "bulk_option": "whole_result",
        }
        url = f"{self.base_url}/app/soldeazy/datasheet"
        if self._context is not None:
            page = await self._ensure_page()
            if not (page.url or "").startswith(self.base_url):
                await self._goto(f"{self.base_url}{LIST_PATH}")
                await asyncio.sleep(1.0)
            response = await page.context.request.post(
                url, form={**base_form, **extra}, timeout=180_000
            )
            body = await response.body()
            status = response.status
        else:
            # 浏览器已被空闲释放（或本进程根本没开过）：用落盘 cookie 直接发请求
            if not await self.session_alive_http():
                raise EbayMcpError(
                    "SOLDEAZY_LOGIN_REQUIRED",
                    "没有可用登录态：cookie 缺失或已失效，且浏览器未启动。"
                    "先调 soldeazy_open_login 登录一次（或等占用 profile 的会话释放）。",
                    details={"session_file": str(self._session_file())},
                )
            async with self._http_client() as client:
                http_response = await client.post(url, data={**base_form, **extra})
            body = http_response.content
            status = http_response.status_code
        if not body or body[:2] != b"PK":
            raise EbayMcpError(
                "SOLDEAZY_EXPORT_API_FAILED",
                "cookie 导出没有返回 xlsx",
                details={
                    "status": status,
                    "head": body[:160].decode("utf-8", "ignore") if body else "",
                    "form": extra,
                },
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return {"path": str(dest), "size": len(body), "channel": "cookie", "form": extra}

    async def export(self, dest: Path) -> dict[str, Any]:
        """导出明细。通道由 `SOLDEAZY_EXPORT_CHANNEL` 决定：

        - `page`（默认）：走页面表单，已长期验证；
        - `cookie`：纯会话请求，待实机验证后再切默认。
        """

        if (self.settings.soldeazy_export_channel or "page").lower() == "cookie":
            return await self.export_via_api(dest)
        return await self._export_via_page(dest)

    async def _export_via_page(self, dest: Path) -> dict[str, Any]:
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
        await self._goto(f"{self.base_url}{UPLOAD_PATH}")
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

    async def select_datasheets(self, rowids: Sequence[str], *, max_pages: int = 40) -> dict[str, Any]:
        """只勾选指定的数据表（BULK SYNC 作用于勾选行）。

        返回 ``{selected, wanted, pages_walked, found, missing}``：
        勾选和同步**只作用于当前页渲染出来的行**，而结果表是分页的
        （默认 25 行/页，可调到 200）。历史审计里"计划 209 个数据表、实际只勾选到
        18 个"就是因为目标行在后面的页上。这里先把每页条数调到最大档再逐页翻找，
        直到全部勾上或翻完。

        勾选只是尽力而为：``sync_up_via_api`` 现在按完整清单传 ``table_row_ids``，
        服务端以参数为准；勾不全只会记警告（见 apply_plan），同步任务的实际条数
        仍由工序队列核对兜底。
        """

        wanted = {str(item).strip() for item in rowids if str(item).strip()}
        if not wanted:
            return {"selected": 0, "wanted": 0, "pages_walked": 0, "found": [], "missing": []}
        page = await self._ensure_page()
        # 导出已改走 cookie/API 通道，不再依赖页面弹层，这里调档是安全的；
        # 每页渲染上限约 65 行（虚拟化），调大档能显著减少翻页次数。
        await self._select_page_limit(200)

        async def _click_page() -> dict[str, Any]:
            # 调档/翻页都是 AJAX 重拉，evaluate 可能正好撞在导航上
            # （2026-11-11 实机：Execution context was destroyed）。重试即可。
            return await self._eval_with_retry(
                page,
                """
                (wanted) => {
                  const set = new Set(wanted);
                  let count = 0;
                  const hit = [];
                  document.querySelectorAll('#tbl_dSheet tr').forEach((r) => {
                    const box = r.querySelector('input[type=checkbox]');
                    if (!box) return;
                    const cells = Array.from(r.cells).map((c) => (c.innerText || '').trim());
                    const id = cells.find((t) => set.has(t));
                    if (id && !box.checked) {
                      box.click();
                      count += 1;
                      hit.push(id);
                    } else if (id && box.checked) {
                      count += 1;
                      hit.push(id);
                    } else if (!id && box.checked) {
                      box.click();
                    }
                  });
                  return { count, hit };
                }
                """,
                list(wanted),
            )

        found: set[str] = set()
        pages_walked = 1
        result = await _click_page()
        found.update(result.get("hit") or [])

        while len(found) < len(wanted) and pages_walked < max_pages:
            if not await self._goto_next_page():
                break
            pages_walked += 1
            result = await _click_page()
            found.update(result.get("hit") or [])

        return {
            "selected": len(found),
            "wanted": len(wanted),
            "pages_walked": pages_walked,
            "found": sorted(found),
            "missing": sorted(wanted - found),
        }

    async def sync_up_via_api(
        self, *, price_postage: bool = True, quantity: bool = False,
        row_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """用接口提交「同步上平台」，替代点弹框。

        前提：当前页面已在搜索结果上、且目标行已勾选（`table_row_ids`）。
        `sql_cache_token` 由本次搜索下发，必须从页面上取，不能沿用旧值。

        ``row_ids`` 显式传入时直接用它——勾选框只在当前页存在，跨页勾选后
        页面上读到的勾选集合不完整，接口参数必须按计划的完整清单给。
        """

        if row_ids:
            row_ids = [str(item).strip() for item in row_ids if str(item).strip()]

        form_head = {
            "mode": "bulk_dalign",
            "second_mode": "dsheet_list",
            "table_action": "show",
            "bulk_option": "selected_items",
            "dalign_price": "1" if price_postage else "0",
            "dalign_imghttps": "1",
            "dalign_option": "2",
        }
        if quantity:
            form_head["dalign_qty"] = "1"
        url = f"{self.base_url}/app/soldeazy/datasheet"

        if self._context is not None:
            page = await self._ensure_page()
            token = await self._eval_with_retry(
                page,
                "() => ((document.querySelector('input[name=sql_cache_token]')||{}).value || '')",
            )
            if not row_ids:
                row_ids = await self._eval_with_retry(page, """
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
            response = await page.context.request.post(
                url,
                form={**form_head, "table_row_ids": ",".join(row_ids), "sql_cache_token": token},
                timeout=120_000,
            )
            text = (await response.text()) or ""
            status = response.status
        else:
            # 免浏览器：令牌用最近一次 HTTP 搜索存下的；没有就先搜索
            token = self._last_sql_token
            if not token:
                raise EbayMcpError(
                    "SOLDEAZY_TOKEN_MISSING",
                    "没有可用的同步令牌：先跑一次 search（HTTP 通道会顺带取令牌）。",
                )
            if not row_ids:
                raise EbayMcpError(
                    "SOLDEAZY_NO_SELECTION", "没有勾选行也没传显式清单，无法同步。"
                )
            async with self._http_client() as client:
                posted = await client.post(
                    url,
                    data={
                        **form_head,
                        "table_row_ids": ",".join(row_ids),
                        "sql_cache_token": token,
                    },
                )
            text = posted.text or ""
            status = posted.status_code

        hints = []
        for marker in ("没有在线刊登", "New D-Align", "同步成功", "已加入", "失败"):
            if marker in text:
                hints.append(marker)
        return {
            "success": status == 200,
            "status": status,
            "rows": len(row_ids),
            "table_row_ids": row_ids,
            "hints": hints,
        }

    async def create_blank_datasheet(
        self, *, shop_idx: str, site_code: str = "US", template_idx: str = ""
    ) -> dict[str, Any]:
        """从0创建一条空数据表，返回新 rowid（模板只预设刊登参数，不含产品数据）。"""

        page = await self._ensure_page()
        await self._goto(f"{self.base_url}{LIST_PATH}")
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

        await self._goto(f"{self.base_url}{LIST_PATH}")
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
        await self._goto(f"{self.base_url}{LIST_PATH}")
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

    async def _open_edit(self, rowid: str) -> Any:
        """打开某条数据表的编辑表单（POST table_action=edit）。"""

        page = await self._ensure_page()
        await self._goto(f"{self.base_url}{LIST_PATH}")
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
        # 明细字段是页面加载后由脚本渲染的，等它出现再继续
        try:
            await page.wait_for_selector(
                'input[name="dsku_price[]"], input[name="dsku_qty[]"]', timeout=20_000
            )
        except Exception:  # noqa: BLE001 - 没有明细字段时也要继续（例如新建页）
            pass
        await asyncio.sleep(1.0)
        return page

    async def apply_datasheet_changes(
        self, rowid: str, changes: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        """【已封存，不用于计划执行】把一组字段改动写进同一条数据表并保存。

        2026-11-07 起计划执行统一走「导出→批量改→一次上传」，
        这个逐条通道只在需要单独修一条记录时才会用到。

        ``changes`` 每项：``{"sku": 子体SKU, "field": "price"|"qty", "new": 数值}``。
        多变体表按 ``dsku_product_code[]`` 的下标对齐，写对应下标的价格/数量。
        """

        page = await self._open_edit(rowid)
        result = await page.evaluate(
            """
            (changes) => {
              const arr = (name) =>
                Array.from(document.querySelectorAll('[name="' + name + '"]'));
              const codes = arr('dsku_product_code[]').map(el => (el.value || '').trim());
              const applied = [];
              const failed = [];
              for (const ch of changes) {
                let index = codes.indexOf(String(ch.sku).trim());
                if (index < 0 && codes.length === 1) index = 0;
                if (index < 0) {
                  failed.push({...ch, reason: '这个数据表里没有该 SKU', available: codes});
                  continue;
                }
                const field = ch.field === 'price' ? 'dsku_price[]' : 'dsku_qty[]';
                const target = arr(field)[index];
                if (!target) {
                  failed.push({...ch, reason: '找不到字段 ' + field});
                  continue;
                }
                target.value = ch.new;
                target.dispatchEvent(new Event('input', {bubbles: true}));
                target.dispatchEvent(new Event('change', {bubbles: true}));
                applied.push({...ch, index: index});
              }
              return {applied: applied, failed: failed, codes: codes};
            }
            """,
            list(changes),
        )

        if not result["applied"]:
            return {
                "success": False,
                "rowid": str(rowid),
                "applied": [],
                "failed": result["failed"],
                "notice": "",
            }

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
        await asyncio.sleep(5)
        notice = await page.evaluate(
            """
            () => {
              const el = document.querySelector('[class*=ajax-error], [class*=error-msg], [class*=notice]');
              return el && el.offsetParent ? (el.innerText || '').trim().slice(0, 200) : '';
            }
            """
        )
        # 页面提示不等于本次字段没写进去（例如"品类需要填写标准产品目录"与价格无关），
        # 所以只当警告记下来；真正的成败由对账步骤判定。
        return {
            "success": clicked is not None and not result["failed"],
            "rowid": str(rowid),
            "applied": result["applied"],
            "failed": result["failed"],
            "warnings": [notice] if notice else [],
        }

    async def read_datasheet_values(
        self,
        site: str = "US",
        query: str = "",
        *,
        search: bool = True,
        only_listed: bool = True,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """搜索并导出一次，返回 ``{(母体rowid, 子体SKU): {qty, price, parent, ...}}``。

        子体行没有 Row ID，按"最近一个带 rowid 的行"归属。
        """

        from ebay_mcp_server.providers.soldeazy_workbook import read_matrix

        if search:
            await self.search(query, site, only_listed=only_listed)

        workdir = Path(self.profile_dir).parent / "reconcile"
        workdir.mkdir(parents=True, exist_ok=True)
        target = workdir / f"state_{int(asyncio.get_running_loop().time())}.xlsx"
        await self.export_via_api(target)

        from ebay_mcp_server.providers.soldeazy_workbook import header_row_count

        _sheet, matrix = read_matrix(target)
        values: dict[tuple[str, str], dict[str, Any]] = {}
        current = ""
        parent = ""
        header = header_row_count(matrix)
        self.last_export_shops = sorted(
            {
                str(row[1] or "").strip()
                for row in matrix[header:]
                if len(row) > 1 and str(row[1] or "").strip()
            }
        )
        for row in matrix[header:]:
            rowid = str(row[0] or "").strip()
            psku = str(row[2] or "").strip()
            sku = str(row[3] or "").strip()
            if rowid:
                current = rowid
                parent = psku
            if not sku:
                continue
            values[(current, sku)] = {
                "rowid": rowid,
                "parent": parent,
                "sku": sku,
                "qty": row[4],
                "price": row[5],
            }
        return values

    async def queue_jobs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """读工序管理任务列表（``queue-job/ajax/get-queue-jobs``）。"""

        url = f"{self.base_url}/app/soldeazy/queue-job/ajax/get-queue-jobs"
        if self._context is not None:
            page = await self._ensure_page()
            await self._goto(f"{self.base_url}/app/soldeazy/queue-job")
            await asyncio.sleep(1.5)
            response = await page.context.request.post(url, form={}, timeout=60_000)
            text = (await response.text()).lstrip("\ufeff").strip()
        else:
            async with self._http_client() as client:
                posted = await client.post(url, data={})
            text = posted.text.lstrip("\ufeff").strip()
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise EbayMcpError(
                "SOLDEAZY_QUEUE_BAD_RESPONSE",
                "工序管理列表不是 JSON",
                details={"head": text[:160]},
            ) from exc
        jobs = ((payload.get("body") or {}).get("queue_jobs") or [])[:limit]
        return jobs

    async def queue_result(self, job_id: str) -> dict[str, Any]:
        """读某个任务的逐行处理结果（``queue/result?job_id=…``，返回 HTML）。"""

        url = f"{self.base_url}/app/soldeazy/queue/result"
        if self._context is not None:
            page = await self._ensure_page()
            response = await page.context.request.post(
                url, params={"job_id": str(job_id)}, timeout=60_000
            )
            html = await response.text()
        else:
            async with self._http_client() as client:
                posted = await client.post(url, params={"job_id": str(job_id)})
            html = posted.text

        def pick(pattern: str) -> str:
            match = re.search(pattern, html, re.S)
            return re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else ""

        rows = []
        for block in re.findall(r"<tr>(.*?)</tr>", html, re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)
            if len(cells) < 3:
                continue
            file_name = re.sub(r"<[^>]+>", "", cells[0]).strip()
            rowid = re.sub(r"<[^>]+>", "", cells[1]).strip()
            outcome = re.sub(r"<[^>]+>", "", cells[2]).strip()
            if rowid.isdigit():
                rows.append({"rowid": rowid, "file": file_name, "result": outcome})

        return {
            "job_id": str(job_id),
            "act": pick(r"<div class='job-act-label'>([^<]+)</div>"),
            "processed": pick(r"已处理:</th><td>([^<]+)</td>"),
            "success": pick(r"成功:</th><td>([^<]+)</td>"),
            "failed": pick(r"失败:</th><td>([^<]+)</td>"),
            "rows": rows,
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
        await self._goto(f"{self.base_url}{LIST_PATH}")
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

        payload = path.read_bytes()
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        url = f"{self.base_url}{UPLOAD_PATH}/upload"
        if self._context is not None:
            page = await self._ensure_page()
            response = await page.context.request.post(
                url,
                multipart={
                    "filePackage": {"name": path.name, "mimeType": mime, "buffer": payload}
                },
                timeout=120_000,
            )
            status = response.status
            text = (await response.text()).lstrip("\ufeff").strip()
        else:
            # 免浏览器：multipart 直接发，cookie 来自落盘文件
            async with self._http_client() as client:
                posted = await client.post(
                    url, files={"filePackage": (path.name, payload, mime)}
                )
            status = posted.status_code
            text = posted.text.lstrip("\ufeff").strip()
        if status != 200:
            raise EbayMcpError("SOLDEAZY_UPLOAD_FAILED", f"上传接口返回 HTTP {status}")
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
    """解析金额。``0;8`` 这种带分号的取分号前那一段（运费列常见格式）。"""

    raw = (text or "").strip()
    for splitter in (";", "；"):
        if splitter in raw:
            raw = raw.split(splitter, 1)[0]
            break
    cleaned = raw.strip().replace(",", "").replace("£", "").replace("€", "")
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
