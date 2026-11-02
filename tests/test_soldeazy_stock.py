"""库存更新表：表头校验、数值校验、重复检测（纯解析，不需要 Excel 库）。"""

from __future__ import annotations

import pytest

from ebay_mcp_server.providers.soldeazy_stock import (
    COLUMNS,
    parse_stock_rows,
)

HEADER = ["SKU", "库存", "备注"]


def test_header_columns_are_the_agreed_ones() -> None:
    assert COLUMNS == ("SKU", "库存", "备注")


def test_parses_a_clean_sheet() -> None:
    sheet = parse_stock_rows(
        [
            HEADER,
            ["ZMHB0004US", 101, "补货"],
            ["PCPB0028US", "300", None],
            [None, None, None],  # 空行忽略
        ]
    )

    assert sheet.ok
    assert sheet.entries == {"ZMHB0004US": 101.0, "PCPB0028US": 300.0}
    assert sheet.skipped == []


def test_column_order_does_not_matter() -> None:
    sheet = parse_stock_rows([["库存", "备注", "SKU"], [12, "", "JJXK0001"]])
    assert sheet.entries == {"JJXK0001": 12.0}


def test_blank_or_dash_quantity_is_skipped_not_an_error() -> None:
    sheet = parse_stock_rows(
        [HEADER, ["A1", None, ""], ["A2", "-", ""], ["A3", "  ", ""]]
    )
    assert sheet.ok
    assert sheet.entries == {}
    assert [item["sku"] for item in sheet.skipped] == ["A1", "A2", "A3"]


def test_missing_header_is_rejected() -> None:
    sheet = parse_stock_rows([["货号", "数量"], ["A1", 1]])
    assert not sheet.ok
    assert "必须同时包含 SKU 与 库存" in sheet.issues[0]


def test_non_numeric_and_negative_quantities_are_reported() -> None:
    sheet = parse_stock_rows(
        [HEADER, ["A1", "abc", ""], ["A2", -3, ""], ["A3", 1.5, ""]]
    )
    assert not sheet.ok
    assert len(sheet.issues) == 3
    assert "不是数字" in sheet.issues[0]
    assert "为负数" in sheet.issues[1]
    assert "不是整数" in sheet.issues[2]
    assert sheet.entries == {}


def test_duplicate_sku_is_reported_instead_of_last_wins() -> None:
    sheet = parse_stock_rows([HEADER, ["A1", 10, ""], ["A1", 20, ""]])
    assert not sheet.ok
    assert "与前面重复" in sheet.issues[0]
    assert sheet.entries == {"A1": 10.0}


def test_quantity_without_sku_is_reported() -> None:
    sheet = parse_stock_rows([HEADER, [None, 5, ""]])
    assert not sheet.ok
    assert "SKU 为空" in sheet.issues[0]


def test_thousands_separator_is_accepted() -> None:
    sheet = parse_stock_rows([HEADER, ["A1", "1,200", ""]])
    assert sheet.entries == {"A1": 1200.0}


def test_empty_sheet_is_rejected() -> None:
    sheet = parse_stock_rows([])
    assert not sheet.ok
    assert sheet.issues


@pytest.mark.parametrize("qty", [0, "0"])
def test_zero_stock_is_valid(qty: object) -> None:
    sheet = parse_stock_rows([HEADER, ["A1", qty, ""]])
    assert sheet.ok
    assert sheet.entries == {"A1": 0.0}
