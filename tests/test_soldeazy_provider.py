"""Tests for the Soldeazy browser provider's pure parts (no browser needed)."""

from __future__ import annotations

import pytest

from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.providers.soldeazy import (
    COLUMN_ALIASES,
    SELECTORS,
    Locator,
    parse_table,
    resolve_columns,
)

# 生产列表页的真实表头（archive/02_soldeazy详情补数/文档/接口探查记录_20260914.md）
REAL_HEADER = (
    "序号\t数据表编号\t功能选项\t状态\t渠道帐号\t站点\t标题\t图\tSKU\t价格\t运费(当地)\t促销刊登\teBay促销"
)


def test_all_25_yingdao_selectors_are_mapped() -> None:
    assert len(SELECTORS) == 25
    for key, entry in SELECTORS.items():
        assert isinstance(entry, Locator), key
        assert entry.name and entry.xpath.startswith("//"), key
        assert entry.candidates()


def test_resolve_columns_reads_the_real_header() -> None:
    mapping = resolve_columns(REAL_HEADER.split("\t"))
    assert mapping["rowid"] == 1
    assert mapping["sku"] == 8
    assert mapping["price"] == 9
    assert mapping["postage"] == 10
    assert mapping["shop"] == 4
    assert mapping["site"] == 5


def test_every_column_has_aliases() -> None:
    for field, aliases in COLUMN_ALIASES.items():
        assert aliases, field
        assert all(isinstance(alias, str) and alias for alias in aliases), field


def test_parse_table_returns_typed_records() -> None:
    data = (
        "1\t4551545\t...\tListed\tEB\tUK\ttitle\timg\tZMHB0004US\t28.48\t£5.00\t\t\n"
        "2\t4551546\t...\tListed\tEB\tUK\ttitle\timg\tZMHB0004US x2\t57.80\t-\t\t"
    )
    header, records = parse_table([REAL_HEADER, data.splitlines()[0], data.splitlines()[1]])

    assert header[8] == "SKU"
    assert [r["sku"] for r in records] == ["ZMHB0004US", "ZMHB0004US x2"]
    assert records[0]["price"] == pytest.approx(28.48)
    assert records[0]["postage"] == pytest.approx(5.0)
    assert records[1]["postage"] is None
    assert records[0]["rowid"] == "4551545"


def test_parse_table_handles_thousands_separator_and_currency() -> None:
    row = "1\t9\t..\tListed\tEB\tDE\tt\timg\tABC1\t1,234.50\t€12.90\t\t"
    _, records = parse_table([REAL_HEADER, row])
    assert records[0]["price"] == pytest.approx(1234.5)
    assert records[0]["postage"] == pytest.approx(12.9)


def test_parse_table_rejects_an_unexpected_layout() -> None:
    with pytest.raises(EbayMcpError, match="找不到 SKU 列"):
        parse_table(["随便\t两列", "1\t2"])


def test_parse_table_skips_blank_and_skuless_rows() -> None:
    _, records = parse_table([REAL_HEADER, "", "1\t4551545\t\t\tEB\tUK\tt\timg\t\t28.48\t0"])
    assert records == []
