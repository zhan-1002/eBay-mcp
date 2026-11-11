"""Soldeazy 浏览器 provider 的纯解析测试（不启动浏览器）。"""

from __future__ import annotations

import asyncio

import pytest

from ebay_mcp_server.providers.soldeazy import (
    COLUMN_ALIASES,
    SELECTORS,
    SITE_CODES,
    SITE_LABELS,
    Locator,
    parse_rows,
    resolve_columns,
)

# 真机表头（2026-11-02，14 个 th，首列是勾选框）
REAL_HEADER = [
    "",
    "序号",
    "数据表 编号",
    "功能选项",
    "状态",
    "渠道 帐号",
    "站点",
    "标题",
    "",
    "SKU",
    "价格",
    "运费 (当地)",
    "促销 刊登",
    "eBay促销",
]

# 真机数据行（16 个 td：多出勾选框 + 一个重复标题格）
ROW_SINGLE = [
    "",
    "1",
    "4567313",
    "edit delete previewSYOSUERV",
    "",
    "EBAY TUD",
    "US",
    "Portable Power Bank 7USB",
    "",
    "Portable Power Bank 7USB",
    "",
    "PCPB0028US",
    "20.99",
    "0",
    "-",
    "-",
]

# 多属性行：SKU / 价格单元格里多行挤在一起
ROW_MULTI = [
    "",
    "2",
    "4567312",
    "edit delete previewSYOSUERV",
    "",
    "EBAY TUD",
    "US",
    "Mini Portable Charger",
    "",
    "Mini Portable Charger",
    "16",
    "PCPB0028US\nPCPB0028US -1\nPCPB0028US -2",
    "20.99\n20.99\n21.99",
    "0",
    "-",
    "-",
]

# 变体展开行：只有 2 个单元格
ROW_EXPAND = ["", "Portable Power Bank 7USB"]


# 影刀工程里那 25 个选择器，必须一个不少地映射到 provider
YINGDAO_SELECTOR_NAMES = (
    "输入框_login_user", "密码框", "Login", "soldeazy-广告弹框",
    "弹框-(不再显示此消息)", "弹框-关闭",
    "SKU输入框", "Channel Site", "Listing Format", "Status", "Date Modified",
    "Search", "搜索结果table", "Scope", "Export", "Bulk Export Options",
    "Add / edit an Export Profile", "Bulk Export Options_export", "Bulk SYNC",
    "同步弹框", "Price Postage", "SYNC UP", "New D-Align bul...",
    "选择文件_filePackage", "Upload Completed",
)


def test_all_yingdao_selectors_are_mapped() -> None:
    names = {entry.name for entry in SELECTORS.values()}
    missing = [name for name in YINGDAO_SELECTOR_NAMES if name not in names]
    assert not missing, missing

    for key, entry in SELECTORS.items():
        assert isinstance(entry, Locator), key
        assert entry.name and entry.xpath.startswith("//"), key
        assert entry.candidates()


def test_export_selectors_cover_the_real_export_dialog() -> None:
    # 实测：导出档案为空时页面 JS 直接 return false，所以必须能选到这两个下拉
    assert SELECTORS["export_dialog"].css == "#jqizoo"
    assert "listExppf" in SELECTORS["export_profile_select"].css
    assert "listExpfmt" in SELECTORS["export_format_select"].css


def test_site_labels_match_the_real_dropdown() -> None:
    # 实测：DE 在下拉里叫 Germany，值 77；US 的值是 0，UK 是 3
    assert SITE_LABELS["DE"] == "Germany"
    assert SITE_LABELS["US"] == "US"
    assert SITE_CODES["DE"] == "77"
    assert SITE_CODES["US"] == "0"
    assert SITE_CODES["UK"] == "3"


def test_resolve_columns_ignores_header_line_breaks() -> None:
    mapping = resolve_columns(REAL_HEADER)
    assert mapping["rowid"] == 2
    assert mapping["site"] == 6
    assert mapping["sku"] == 9
    assert mapping["price"] == 10
    assert mapping["postage"] == 11


def test_every_column_has_aliases() -> None:
    for field, aliases in COLUMN_ALIASES.items():
        assert aliases, field
        assert all(isinstance(alias, str) and alias for alias in aliases), field


def test_parse_rows_uses_the_measured_cell_positions() -> None:
    header, records = parse_rows([REAL_HEADER, ROW_SINGLE])

    assert header[1] == "序号"
    assert len(records) == 1
    record = records[0]
    assert record["rowid"] == "4567313"
    assert record["shop"] == "EBAY TUD"
    assert record["site"] == "US"
    assert record["sku"] == "PCPB0028US"
    assert record["price"] == pytest.approx(20.99)
    assert record["postage"] == pytest.approx(0.0)
    assert record["variants"] == 1


def test_parse_rows_marks_multi_variant_rows() -> None:
    _, records = parse_rows([REAL_HEADER, ROW_MULTI])
    record = records[0]

    assert record["rowid"] == "4567312"
    assert record["variants"] == 3
    assert record["sku"] == "PCPB0028US"      # 取第一行作代表
    assert record["price"] == pytest.approx(20.99)


def test_parse_rows_skips_variant_expansion_rows() -> None:
    _, records = parse_rows([REAL_HEADER, ROW_SINGLE, ROW_EXPAND])
    assert [r["rowid"] for r in records] == ["4567313"]


def test_parse_rows_tolerates_an_empty_page() -> None:
    assert parse_rows([]) == ([], [])
    assert parse_rows([["", "  "]]) == ([], [])


def test_parse_rows_ignores_rows_without_a_datasheet_id() -> None:
    _, records = parse_rows([REAL_HEADER, [""] + ["x"] * 15])
    assert records == []

# 筛选后列表少一列（勾选框不见了），内容锚定仍应取对
ROW_SINGLE_15 = ROW_SINGLE[1:]


def test_parse_rows_survives_a_column_shift() -> None:
    _, records = parse_rows([REAL_HEADER, ROW_SINGLE_15])
    record = records[0]
    assert record["rowid"] == "4567313"
    assert record["shop"] == "EBAY TUD"
    assert record["site"] == "US"
    assert record["sku"] == "PCPB0028US"
    assert record["price"] == pytest.approx(20.99)


def test_shop_scope_hint_admits_when_no_shop_filter_was_applied() -> None:
    """2026-11-11：不传 shop 时搜索不做过滤，返回的是平台默认店铺。

    那次实际返回的是 EBAY TAY 的数据，却很容易被当成 FUN 的，所以必须如实回传。
    """

    from ebay_mcp_server.providers.soldeazy import _shop_scope_hint

    hint = _shop_scope_hint("")
    assert hint["shop_filter_applied"] is False
    assert "未设置" in hint["shop_filter"]


def test_shop_scope_hint_lists_the_shops_actually_returned() -> None:
    from ebay_mcp_server.providers.soldeazy import _shop_scope_hint

    records = [{"shop": "EBAY TAY"}, {"shop": "EBAY TAY"}]

    hint = _shop_scope_hint("FUN", records)
    assert hint["shop_filter_applied"] is True
    assert hint["shops_in_result"] == ["EBAY TAY"]
    assert hint["shop_scope_mismatch"] is True     # 说是 FUN，回来的是 TAY

    same = _shop_scope_hint("FUN", [{"shop": "FUN"}])
    assert same["shop_scope_mismatch"] is False


def test_shop_scope_hint_tolerates_prefixed_shop_names() -> None:
    """平台里的店铺名是 EBAY LT 这种，查询用简称 LT，不能算不一致。"""

    from ebay_mcp_server.providers.soldeazy import _shop_scope_hint

    hint = _shop_scope_hint("LT", [{"shop": "EBAY LT"}])
    assert hint["shop_scope_mismatch"] is False


def test_launch_error_tells_profile_lock_apart_from_missing_browser():
    """抢不到 profile 绝不能报成"找不到 Chrome"——那是两个完全不同的病。"""

    from pathlib import Path

    from ebay_mcp_server.providers.soldeazy import launch_error

    locked = launch_error(
        Path("x"),
        ["chrome: BrowserType.launch_persistent_context: ProcessSingleton: "
         "user data directory is already in use"],
        tried=["chrome"],
    )
    assert locked.code == "SOLDEAZY_PROFILE_LOCKED"
    assert "只有一个会话" in locked.message

    denied = launch_error(Path("x"), ["chrome: EPERM access denied"], tried=["chrome"])
    assert denied.code == "SOLDEAZY_BROWSER_LAUNCH_DENIED"

    missing = launch_error(Path("x"), ["chrome: Executable doesn't exist"], tried=["chrome"])
    assert missing.code == "SOLDEAZY_BROWSER_LAUNCH_FAILED"
    assert missing.details["tried"] == ["chrome"]


def test_looks_logged_in_reads_the_two_markers() -> None:
    from ebay_mcp_server.providers.soldeazy import looks_logged_in

    assert looks_logged_in('<table id="tbl_dSheet"></table>') is True
    assert looks_logged_in('<form><input type="password" name="pwd"></form>') is False
    assert looks_logged_in("<html>whatever</html>") is False


def test_cookie_dict_reads_the_session_file(tmp_path) -> None:
    import json
    from dataclasses import replace

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "session_cookies.json").write_text(
        json.dumps([{"name": "a", "value": "1"}, {"name": "_ht_ses_", "value": "x"}, "junk"]),
        encoding="utf-8",
    )
    browser = SoldeazyBrowser(replace(Settings.load(), soldeazy_profile_dir=str(profile)))
    assert browser._cookie_dict() == {"a": "1", "_ht_ses_": "x"}


def test_session_alive_http_is_false_without_cookies(tmp_path) -> None:
    import asyncio
    from dataclasses import replace

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    browser = SoldeazyBrowser(
        replace(Settings.load(), soldeazy_profile_dir=str(tmp_path / "empty"))
    )
    assert asyncio.run(browser.session_alive_http()) is False


def test_export_without_browser_and_without_cookies_fails_loudly(tmp_path) -> None:
    """没开浏览器 + 没 cookie：必须明确说要登录，不能静默导出一份错的。"""

    import asyncio
    from dataclasses import replace

    import pytest

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.errors import EbayMcpError
    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    browser = SoldeazyBrowser(
        replace(Settings.load(), soldeazy_profile_dir=str(tmp_path / "empty"))
    )
    with pytest.raises(EbayMcpError) as caught:
        asyncio.run(browser.export_via_api(tmp_path / "x.xlsx"))
    assert caught.value.code == "SOLDEAZY_LOGIN_REQUIRED"


def test_idle_release_closes_browser_after_idle() -> None:
    """空闲到点就关浏览器、交还 profile 锁；cookie 由 close() 落盘。"""

    import asyncio
    import dataclasses

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers import soldeazy as mod

    browser = mod.SoldeazyBrowser(Settings.load())
    browser.settings = dataclasses.replace(
        browser.settings, soldeazy_browser_idle_seconds=0.05
    )
    closed: list[bool] = []

    async def fake_close() -> None:
        closed.append(True)
        browser._context = None

    browser.close = fake_close  # type: ignore[method-assign]
    browser._context = object()

    async def run() -> None:
        browser._touch()
        await asyncio.sleep(0.25)

    asyncio.run(run())
    assert closed == [True]
    assert browser._context is None


def test_idle_release_disabled_when_zero() -> None:
    import dataclasses

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers import soldeazy as mod

    browser = mod.SoldeazyBrowser(Settings.load())
    browser.settings = dataclasses.replace(
        browser.settings, soldeazy_browser_idle_seconds=0
    )
    browser._touch()
    assert browser._idle_task is None


def test_idle_release_defers_while_search_lock_held() -> None:
    """search 跑到一半绝不能被释放：持锁时顺延一轮。"""

    import asyncio
    import dataclasses

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers import soldeazy as mod

    browser = mod.SoldeazyBrowser(Settings.load())
    browser.settings = dataclasses.replace(
        browser.settings, soldeazy_browser_idle_seconds=0.05
    )
    closed: list[bool] = []

    async def fake_close() -> None:
        closed.append(True)

    browser.close = fake_close  # type: ignore[method-assign]
    browser._context = object()

    async def run() -> None:
        async with browser._lock:
            browser._touch()
            await asyncio.sleep(0.12)
            assert closed == []          # 计时器到点但锁还在 → 顺延
        await asyncio.sleep(0.25)        # 放锁后的下一轮才真正释放
        assert closed == [True]

    asyncio.run(run())


def test_status_exposes_session_state_without_credentials(tmp_path) -> None:
    """无凭据时 status 必须明说，而不是让调用方去猜"为什么要人工登录"。"""

    from dataclasses import replace

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    settings = replace(
        Settings.load(),
        soldeazy_username="",
        soldeazy_password="",
        soldeazy_profile_dir=str(tmp_path / "profile"),
    )
    browser = SoldeazyBrowser(settings)
    state = asyncio.run(browser.status())

    assert state["credentials_configured"] is False
    assert state["session_file_exists"] is False
    assert state["session_cookie_count"] == 0
    assert state["session_save_error"] == ""


def test_save_session_records_error_instead_of_swallowing(tmp_path) -> None:
    from dataclasses import replace

    from ebay_mcp_server.config import Settings
    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    settings = replace(
        Settings.load(), soldeazy_profile_dir=str(tmp_path / "profile")
    )
    browser = SoldeazyBrowser(settings)
    browser._context = object()  # 有上下文但没有 cookies() 方法
    asyncio.run(browser._save_session())
    assert "AttributeError" in browser.session_save_error


def test_search_defaults_to_listed_only():
    import inspect

    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    sig = inspect.signature(SoldeazyBrowser.search)
    assert sig.parameters["only_listed"].default is True
    assert sig.parameters["only_listed"].kind is inspect.Parameter.KEYWORD_ONLY


def test_listed_status_selector_exists():
    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    assert hasattr(SoldeazyBrowser, "_select_status_listed")


def test_number_takes_amount_before_semicolon():
    """运费列常见 `0;8` 这种写法，取分号前那一段。"""

    from ebay_mcp_server.providers.soldeazy import _number

    assert _number("0;8") == 0.0
    assert _number("0;8.5") == 0.0
    assert _number("0；8") == 0.0
    assert _number("1.25;9") == 1.25
    assert _number("12.50") == 12.5
    assert _number("-") is None
    assert _number("") is None


def test_search_clears_date_filter_and_defaults_to_listed():
    """规则 1 与规则 2：状态默认已刊登，修改日期默认留空。"""

    import inspect

    from ebay_mcp_server.providers.soldeazy import SoldeazyBrowser

    assert hasattr(SoldeazyBrowser, "_clear_date_filter")
    assert hasattr(SoldeazyBrowser, "_select_status_listed")

    source = inspect.getsource(SoldeazyBrowser.search)
    assert "_clear_date_filter" in source
    assert "_select_scope_whole_result" in source
