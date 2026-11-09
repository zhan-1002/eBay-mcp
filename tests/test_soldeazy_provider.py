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
