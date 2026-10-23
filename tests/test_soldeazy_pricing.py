"""Tests for the Soldeazy pricing and stock rules (no browser, no network)."""

from __future__ import annotations

import pytest

from ebay_mcp_server.providers.soldeazy_pricing import (
    DatasheetRow,
    match_target,
    parse_pack,
    plan_price_changes,
    plan_stock_changes,
    resolve_postage,
    rows_from_matrix,
)


def _row(row: int, sku: str, price: float, postage: float | None, rowid: str = "1") -> DatasheetRow:
    return DatasheetRow(
        row=row, rowid=rowid, parent_sku="", sku=sku, qty=50, price=price, postage=postage
    )


def test_parse_pack_variants() -> None:
    assert parse_pack("ZMHB0004US x4") == ("ZMHB0004US", 4)
    assert parse_pack("ZMHB0004US") == ("ZMHB0004US", 1)
    assert parse_pack("PCPB0028US x 2") == ("PCPB0028US x 2", 1)
    assert parse_pack("A x0") == ("A", 0)


def test_prefix_match_allows_site_suffix_but_not_longer_numbers() -> None:
    targets = {"GJHW0031": 40.0, "PCPB0028": 35.0, "1371812": 10.9}

    # site suffix is part of the SKU, not another product
    assert match_target("PCPB0028US", targets)[0] == "PCPB0028"
    # a longer number must not be hijacked by a shorter prefix
    assert match_target("GJHW00310-RED", targets) is None
    # EF- variants are acknowledged
    assert match_target("EF-1371812-XL", targets)[0] == "1371812"
    assert match_target("EF2-1371812", targets)[0] == "1371812"


def test_postage_is_inherited_within_a_datasheet() -> None:
    rows = [
        _row(6, "ZMHB0004US", 31.28, 5.0, rowid="4546601"),
        _row(7, "P10ZMHB0004US", 212.61, None, rowid=""),
        _row(8, "ZMHB0004US x2", 57.80, None, rowid=""),
    ]
    postage = resolve_postage(rows)
    assert postage.by_row == {6: 5.0, 7: 5.0, 8: 5.0}
    assert postage.ambiguous_rows == set()


def test_missing_postage_everywhere_is_zero() -> None:
    rows = [_row(3, "ABC123", 10.0, None)]
    assert resolve_postage(rows).by_row == {3: 0.0}


def test_conflicting_postage_is_flagged_not_guessed() -> None:
    rows = [
        _row(3, "ABCUS", 10.0, 2.0, rowid="9"),
        _row(4, "ABCUS", 10.0, 7.0, rowid=""),
        _row(5, "ABCUS", 10.0, None, rowid=""),  # 无法判断该继承 2 还是 7
    ]
    postage = resolve_postage(rows)
    # 自带运费的行走自己的值；只有缺值的那一行被标为歧义
    assert postage.by_row == {3: 2.0, 4: 7.0}
    assert postage.ambiguous_rows == {5}
    assert postage.warnings

    plan = plan_price_changes(rows, {"ABC": 50.0})
    assert [c.row for c in plan.changes] == [3, 4]
    assert plan.ambiguous_groups == ["9"]


def test_price_is_raised_so_the_total_lands_on_the_minimum() -> None:
    rows = [
        _row(6, "ZMHB0004US", 31.28, 5.0, rowid="4546601"),
        _row(8, "ZMHB0004US x2", 57.80, None, rowid=""),
    ]
    plan = plan_price_changes(rows, {"ZMHB0004": 200.0})

    assert [c.row for c in plan.changes] == [6, 8]
    # single unit: 200 - 5 = 195 (total 200)
    assert plan.changes[0].new == pytest.approx(195.0)
    # pack row inherits the same 5 of postage -> same price under pack_policy=same
    assert plan.changes[1].new == pytest.approx(195.0)
    assert plan.changes[1].group_postage == pytest.approx(5.0)


def test_prices_are_never_lowered() -> None:
    rows = [_row(3, "ABC123", 100.0, 0.0)]
    plan = plan_price_changes(rows, {"ABC123": 50.0})
    assert plan.changes == []


def test_total_equal_to_target_is_left_alone() -> None:
    rows = [_row(3, "ABC123", 45.0, 5.0)]
    assert plan_price_changes(rows, {"ABC123": 50.0}).changes == []


def test_pack_policies() -> None:
    rows = [_row(3, "ABC123 x3", 10.0, 2.0)]

    skipped = plan_price_changes(rows, {"ABC123": 100.0}, pack_policy="skip")
    assert skipped.changes == []
    assert skipped.skipped_packs == ["ABC123 x3 (x3)"]

    multiplied = plan_price_changes(rows, {"ABC123": 100.0}, pack_policy="multiply")
    assert multiplied.changes[0].new == pytest.approx(298.0)  # 100*3 - 2

    same = plan_price_changes(rows, {"ABC123": 100.0}, pack_policy="same")
    assert same.changes[0].new == pytest.approx(98.0)


def test_unmatched_targets_are_reported() -> None:
    rows = [_row(3, "ABC123", 1.0, 0.0)]
    plan = plan_price_changes(rows, {"ABC123": 10.0, "ZZZ999": 5.0})
    assert plan.unmatched_targets == ["ZZZ999"]
    assert plan.matched_rows == 1


def test_stock_targets_the_actual_sku_and_divides_packs() -> None:
    rows = [
        _row(3, "ZMHB0004US", 10.0, 0.0),
        DatasheetRow(4, "1", "", "ZMHB0004US x2", qty=999.0, price=10.0, postage=0.0),
        _row(5, "OTHER001", 10.0, 0.0),
    ]
    changes, unmatched = plan_stock_changes(rows, {"ZMHB0004US": 101})

    assert [(c.row, c.new) for c in changes] == [(3, 101.0), (4, 50.0)]
    assert unmatched == ["OTHER001"]
    assert "÷ 打包数 2" in changes[1].reason


def test_stock_can_skip_pack_division() -> None:
    rows = [_row(4, "ZMHB0004US x2", 10.0, 0.0)]
    changes, _ = plan_stock_changes(rows, {"ZMHB0004US": 101}, divide_by_pack=False)
    assert changes[0].new == pytest.approx(101.0)


def test_stock_leaves_matching_rows_untouched() -> None:
    rows = [DatasheetRow(3, "1", "", "ABC123", qty=50.0, price=1.0, postage=0.0)]
    changes, _ = plan_stock_changes(rows, {"ABC123": 50})
    assert changes == []


def test_rows_from_matrix_handles_text_numbers_and_blanks() -> None:
    rows = rows_from_matrix(
        [
            ("4544942", "PCPB0028US x2", "PCPB0028US x2", "50", "29.98", "0"),
            (None, "ZMHB000XX", "ZMHB0004US", "50", "31.28", "5"),
            (None, "ZMHB000XX", "ZMHB0004US x2", "50", "57.80", None),
        ]
    )
    assert [r.row for r in rows] == [3, 4, 5]
    assert rows[0].postage == 0.0
    assert rows[2].postage is None
    assert rows[1].rowid == ""
