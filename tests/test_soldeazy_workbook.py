"""导出表改写与上传前自检（纯矩阵逻辑，不需要 Excel 库）。"""

from __future__ import annotations

import pytest

from ebay_mcp_server.providers.soldeazy_workbook import (
    EDITABLE_COLUMNS,
    UnsafeUpload,
    apply_changes,
    assert_only_editable,
    build_upload_file,
    changed_columns,
    column_letter,
    header_row_count,
    read_matrix,
    diff_matrices,
    field_column,
)

HEADER = ["dsheet_row_id", "dsheet_shop_initial", "dsheet_var_parent_sku",
          "dsheet_product_code", "dsheet_qty", "dsheet_price", "dsheet_first_post",
          "dsheet_EOF"]
ROW1 = ["4544942", "LT", "PCPB0028US x2", "PCPB0028US x2", "50", "29.98", "0", "0"]
ROW2 = ["4544943", "LT", "PCPB0028US", "PCPB0028US", "50", "19.90", "0", "0"]
SHEET = [HEADER, ["Row ID", "Sales channel", "P.SKU", "SKU", "Qty", "Price", "Post.D.", "dsheet_EOF"], ROW1, ROW2]


def test_column_letters() -> None:
    assert [column_letter(i) for i in (1, 5, 6, 26, 27, 52)] == ["A", "E", "F", "Z", "AA", "AZ"]


def test_field_columns_match_the_export_layout() -> None:
    assert field_column("qty") == 5
    assert field_column("price") == 6
    with pytest.raises(ValueError):
        field_column("postage")  # 运费不在可写字段里


def test_apply_changes_writes_only_the_requested_cells() -> None:
    after = apply_changes(SHEET, [("price", 3, 35.0), ("qty", 4, 300)])

    assert after[2][5] == 35.0     # F3
    assert after[3][4] == 300      # E4
    assert SHEET[2][5] == "29.98"  # 原矩阵未被改动
    assert diff_matrices(SHEET, after) and changed_columns(diff_matrices(SHEET, after)) == {"E", "F"}


def test_apply_changes_rejects_out_of_range_rows() -> None:
    with pytest.raises(ValueError, match="超出表格范围"):
        apply_changes(SHEET, [("price", 99, 1.0)])


def test_diff_reports_row_letter_and_values() -> None:
    after = apply_changes(SHEET, [("price", 3, 35.0)])
    changes = diff_matrices(SHEET, after)

    assert len(changes) == 1
    change = changes[0]
    assert (change.row, change.letter, change.old, change.new) == (3, "F", "29.98", 35.0)
    assert change.as_dict() == {"row": 3, "column": "F", "old": "29.98", "new": 35.0}


def test_diff_detects_a_column_that_must_not_change() -> None:
    tampered = [list(row) for row in SHEET]
    tampered[2][3] = "WRONG-SKU"  # D3 被改

    changes = diff_matrices(SHEET, tampered)
    assert changed_columns(changes) == {"D"}
    with pytest.raises(UnsafeUpload, match="白名单之外"):
        assert_only_editable(changes)


def test_only_e_and_f_are_editable() -> None:
    assert EDITABLE_COLUMNS == {"E", "F"}
    assert_only_editable(diff_matrices(SHEET, apply_changes(SHEET, [("price", 3, 1.0)])))
    assert_only_editable(diff_matrices(SHEET, apply_changes(SHEET, [("qty", 3, 1)])))
    assert_only_editable([])  # 没有改动也合法


def test_assert_only_editable_names_the_offending_columns() -> None:
    tampered = [list(row) for row in SHEET]
    tampered[2][0] = "999"      # A3
    tampered[2][6] = "5"        # G3

    with pytest.raises(UnsafeUpload) as excinfo:
        assert_only_editable(diff_matrices(SHEET, tampered))
    message = str(excinfo.value)
    assert "['A', 'G']" in message
    assert "已拒绝上传" in message


def test_empty_change_list_produces_no_diff() -> None:
    assert diff_matrices(SHEET, apply_changes(SHEET, [])) == []


def test_header_row_count_handles_two_header_rows() -> None:
    matrix = [
        ["dsheet_row_id", "dsheet_shop_initial", "dsheet_var_parent_sku"],
        ["Row ID", "Sales channel", "P.SKU"],
        ["4512957", "FUN", "JJPC0029"],
    ]
    assert header_row_count(matrix) == 2


def test_trimmed_file_keeps_both_header_rows(tmp_path) -> None:
    from openpyxl import Workbook

    src = tmp_path / "export.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Worksheet"
    ws.append(["dsheet_row_id", "dsheet_shop_initial", "dsheet_var_parent_sku",
               "dsheet_product_code", "dsheet_qty", "dsheet_price",
               "dsheet_first_post", "dsheet_EOF"])
    ws.append(["Row ID", "Sales channel", "P.SKU", "SKU", "Qty", "Price", "Post.D.", "dsheet_EOF"])
    ws.append(["4512957", "FUN", "JJPC0029", "JJPC0029", "100", "21.90", "0", "0"])
    ws.append(["4512958", "FUN", "JJPC0029", "JJPC0029", "100", "21.90", "0", "0"])
    ws.append(["4522717", "FUN", "排插-P", "JJPC0028", "100", "17.99", "0", "0"])
    wb.save(src)
    wb.close()

    dst = tmp_path / "done.xlsx"
    report = build_upload_file(src, dst, [("price", 3, 22.5)], keep_rows=[3])

    _name, written = read_matrix(dst)
    assert len(written) == 3, written
    assert str(written[0][0]) == "dsheet_row_id"
    assert str(written[1][0]) == "Row ID"        # 显示表头保留
    assert str(written[2][0]) == "4512957"       # 数据行紧随其后
    assert float(written[2][5]) == 22.5
    assert report["rows"] == 1
