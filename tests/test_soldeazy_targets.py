"""目标文件入口：把成百上千条目标从对话搬到磁盘。"""

from __future__ import annotations

import pytest

from ebay_mcp_server.providers.soldeazy_targets import (
    parse_target_rows,
    parse_targets_text,
    read_targets_file,
)


def test_text_parses_equals_and_comma_lines() -> None:
    text = """
# 注释行
ZMHB0004US=23.0
JJPC0029,19.9
ZMFL0012 x2\t48.9
"""
    batch = parse_targets_text(text, kind="price")

    assert batch.ok
    assert batch.targets == {
        "ZMHB0004US": 23.0,
        "JJPC0029": 19.9,
        "ZMFL0012 x2": 48.9,
    }


def test_text_skips_header_row_from_exported_csv() -> None:
    text = "SKU,价格\nZMHB0004US,23.0\n"
    batch = parse_targets_text(text, kind="price")

    assert batch.ok
    assert batch.targets == {"ZMHB0004US": 23.0}


def test_text_keeps_sku_with_spaces_intact() -> None:
    """套装 SKU 自带空格，不能按空格切。"""

    batch = parse_targets_text("ZMFL0012 x4 = 88.8", kind="price")
    assert batch.targets == {"ZMFL0012 x4": 88.8}


def test_text_reports_duplicates_and_bad_numbers() -> None:
    text = "A=10\nA=12\nB=abc\nC=\n"
    batch = parse_targets_text(text, kind="price")

    assert not batch.ok
    assert len(batch.issues) == 2                 # 重复 + 非数字
    assert batch.skipped[0]["sku"] == "C"         # 留空是跳过，不算错误
    assert batch.targets == {"A": 10}


def test_qty_rejects_negative_and_fractional() -> None:
    batch = parse_targets_text("A=-1\nB=1.5\nC=10", kind="qty")

    assert not batch.ok
    assert len(batch.issues) == 2
    assert batch.targets == {"C": 10}


def test_price_rejects_non_positive() -> None:
    batch = parse_targets_text("A=0\nB=-3\nC=9.9", kind="price")

    assert len(batch.issues) == 2
    assert batch.targets == {"C": 9.9}


def test_excel_rows_use_sku_and_value_columns() -> None:
    matrix = [
        ["SKU", "库存", "备注"],
        ["A", 50, ""],
        ["B", "80", "手填"],
        ["C", None, ""],
    ]
    batch = parse_target_rows(matrix, kind="qty")

    assert batch.ok
    assert batch.targets == {"A": 50.0, "B": 80.0}
    assert batch.skipped[0]["sku"] == "C"


def test_excel_rows_accept_price_header() -> None:
    matrix = [["SKU", "价格"], ["A", 23.0]]
    batch = parse_target_rows(matrix, kind="price")
    assert batch.targets == {"A": 23.0}


def test_excel_rows_reject_missing_sku_column() -> None:
    batch = parse_target_rows([["货号", "库存"], ["A", 1]], kind="qty")
    assert not batch.ok
    assert "SKU" in batch.issues[0]


def test_missing_file_is_reported_not_raised(tmp_path) -> None:
    batch = read_targets_file(tmp_path / "nope.csv", kind="price")
    assert not batch.ok
    assert "找不到" in batch.issues[0]


def test_reads_a_real_text_file(tmp_path) -> None:
    path = tmp_path / "targets.csv"
    path.write_text("A,10\nB,20\n", encoding="utf-8")
    batch = read_targets_file(path, kind="price")

    assert batch.ok
    assert batch.targets == {"A": 10.0, "B": 20.0}
    assert batch.source == str(path)


def test_reads_a_real_excel_file(tmp_path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "库存更新.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "库存"
    sheet.append(["SKU", "库存", "备注"])
    sheet.append(["A", 50, None])
    sheet.append(["B", 80, None])
    workbook.save(str(path))

    batch = read_targets_file(path, kind="qty")

    assert batch.ok
    assert batch.targets == {"A": 50.0, "B": 80.0}


def test_target_file_is_much_cheaper_than_inline_dict() -> None:
    """这条是这次改动的目的：几千条目标不该进对话。"""

    import json

    from ebay_mcp_server.server import _estimate_tokens

    targets = {f"ZMHB{n:04d}US": round(19.9 + n * 0.01, 2) for n in range(2000)}
    inline = len(json.dumps({str(k): v for k, v in targets.items()}, ensure_ascii=False))
    path_only = len("C:/data/targets.csv")

    inline_tokens = _estimate_tokens("x" * inline)
    path_tokens = _estimate_tokens("x" * path_only)

    # 仓库口径（ASCII 4 字符/token）：2000 条约一万出头，真实分词通常还要更高
    assert inline_tokens > 8000
    assert path_tokens < 20
    assert inline_tokens > path_tokens * 100
