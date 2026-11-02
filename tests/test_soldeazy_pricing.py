"""Tests for the Soldeazy pricing and stock rules (no browser, no network)."""

from __future__ import annotations

import pytest

from ebay_mcp_server.providers.soldeazy_pricing import (
    Change,
    infer_pack_factors,
    kmp_search,
    longest_match,
    parse_quantity_marker,
    DatasheetRow,
    load_targets,
    match_target,
    parse_pack,
    plan_price_changes,
    plan_stock_changes,
    resolve_postage,
    rows_from_matrix,
    validate_write_scope,
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


def test_longest_match_allows_site_suffix_but_not_longer_numbers() -> None:
    targets = {"GJHW0031": 40.0, "PCPB0028": 35.0, "1371812": 10.9}

    # 站点后缀属于同一个货号
    assert match_target("PCPB0028US", targets) == ("PCPB0028", 1, "US")
    # 更长的数字不能被短前缀抢走
    assert match_target("GJHW00310-RED", targets) is None
    # EF-/EF2- 前缀 + 变体尾
    assert match_target("EF-1371812-XL", targets) == ("1371812", 1, "")
    assert match_target("EF2-1371812", targets) == ("1371812", 1, "")
    # 前缀打包 + 站点后缀
    assert match_target("P10PCPB0028US", targets) == ("PCPB0028", 10, "US")


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

    # 默认 pack_policy=multiply：单件 200-5=195，x2 目标 400-5=395
    assert [c.row for c in plan.changes] == [6, 8]
    assert plan.changes[0].new == pytest.approx(195.0)
    assert plan.changes[1].new == pytest.approx(395.0)
    assert plan.changes[1].group_postage == pytest.approx(5.0)


def test_prices_are_never_lowered() -> None:
    rows = [_row(3, "ABC123", 100.0, 0.0)]
    plan = plan_price_changes(rows, {"ABC123": 50.0})
    assert plan.changes == []


def test_total_equal_to_target_is_left_alone() -> None:
    rows = [_row(3, "ABC123", 45.0, 5.0)]
    assert plan_price_changes(rows, {"ABC123": 50.0}).changes == []


def test_pack_policies_from_sku_residue() -> None:
    rows = [_row(3, "ABC123 x3", 10.0, 2.0)]

    skipped = plan_price_changes(rows, {"ABC123": 100.0}, pack_policy="skip", pack_source="sku")
    assert skipped.changes == []
    assert skipped.skipped_packs == ["ABC123 x3 (x3)"]

    multiplied = plan_price_changes(
        rows, {"ABC123": 100.0}, pack_policy="multiply", pack_source="sku"
    )
    assert multiplied.changes[0].new == pytest.approx(298.0)  # 100*3 - 2

    same = plan_price_changes(rows, {"ABC123": 100.0}, pack_policy="same", pack_source="sku")
    assert same.changes[0].new == pytest.approx(98.0)


# --------------------------------------------------------------------------
# 单价/套装：按同组价格阶梯反推（2026-11-02 口径）
# --------------------------------------------------------------------------
def test_ladder_infers_factors_from_price_ratios() -> None:
    rows = [
        _row(3, "ABC1", 10.0, 0.0, rowid="G1"),
        _row(4, "ABC1 x2", 19.5, None, rowid=""),
        _row(5, "ABC1 x4", 38.0, None, rowid=""),
        _row(6, "ABC1 x8", 76.0, None, rowid=""),
    ]
    ladders = infer_pack_factors(rows)
    ladder = ladders["G1"]

    assert ladder.base_row == 3
    assert ladder.base_price == 10.0
    assert ladder.factors == {3: 1, 4: 2, 5: 4, 6: 8}   # 19.5/10=1.95→2，38/10=3.8→4，76/10=7.6→8
    assert ladder.uncertain == {}


def test_ladder_flags_a_price_that_is_not_a_multiple() -> None:
    rows = [
        _row(3, "ABC1", 10.0, 0.0, rowid="G1"),
        _row(4, "ABC1 x2", 25.0, None, rowid=""),   # 2.5 倍，离 2 和 3 都远
    ]
    ladder = infer_pack_factors(rows)["G1"]

    assert ladder.factors == {3: 1}
    assert 4 in ladder.uncertain
    assert "偏离整数" in ladder.uncertain[4]


def test_ratio_mode_uses_the_ladder_and_reports_single_row_groups() -> None:
    rows = [
        _row(3, "ABC1", 10.0, 0.0, rowid="G1"),
        _row(4, "ABC1 x2", 19.5, None, rowid=""),
        _row(5, "XYZ9", 5.0, 0.0, rowid="G2"),   # 独自成组
    ]
    plan = plan_price_changes(rows, {"ABC1": 100.0, "XYZ9": 50.0})

    assert {(c.row, c.new) for c in plan.changes} == {(3, 100.0), (4, 200.0), (5, 50.0)}
    assert any("独自成组" in note for note in plan.notes)
    assert plan.ladders["G1"].factors == {3: 1, 4: 2}


def test_ratio_mode_skips_a_row_whose_multiple_is_uncertain() -> None:
    rows = [
        _row(3, "ABC1", 10.0, 0.0, rowid="G1"),
        _row(4, "ABC1 x2", 25.0, None, rowid=""),
    ]
    plan = plan_price_changes(rows, {"ABC1": 100.0})

    assert [c.row for c in plan.changes] == [3]
    assert any("偏离整数" in note for note in plan.notes)


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
    plan = plan_stock_changes(rows, {"ZMHB0004US": 101})

    assert [(c.row, c.new) for c in plan.changes] == [(3, 101.0), (4, 50.0)]
    assert plan.no_stock == ["OTHER001"]
    assert "÷ 打包数 2" in plan.changes[1].reason


def test_stock_can_skip_pack_division() -> None:
    rows = [_row(4, "ZMHB0004US x2", 10.0, 0.0)]
    plan = plan_stock_changes(rows, {"ZMHB0004US": 101}, divide_by_pack=False)
    assert plan.changes[0].new == pytest.approx(101.0)


def test_stock_leaves_matching_rows_untouched() -> None:
    rows = [DatasheetRow(3, "1", "", "ABC123", qty=50.0, price=1.0, postage=0.0)]
    plan = plan_stock_changes(rows, {"ABC123": 50})
    assert plan.changes == []


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

def test_targets_are_split_by_site_and_strip_special_prefixes() -> None:
    targets = load_targets(
        [
            ("UKZMCL0006", 14.9),
            ("DE GJHW0031", ""),  # 空价格
            ("DEGJHW0031", 34.9),
            ("DEEF-1371812", 10.9),
            ("DEEF2-1371813", 11.9),
            ("USPCPB0028", 35.0),
            ("FRPCPB0028", 30.0),  # 站点不在允许列表
            ("DE", 1.0),  # 太短
        ]
    )

    assert sorted(targets.by_site) == ["DE", "UK", "US"]
    assert targets.for_site("UK") == {"ZMCL0006": 14.9}
    assert targets.for_site("DE") == {"GJHW0031": 34.9, "1371812": 10.9, "1371813": 11.9}
    assert [r["reason"] for r in targets.rejected] == [
        "价格更新为空",
        "站点 FR 不在 ['DE', 'UK', 'US'] 中",
        "SKU 不足 3 位，无法拆分站点与货号",
    ]


def test_duplicate_targets_keep_the_first_price_and_report_the_conflict() -> None:
    targets = load_targets([("DEABC1", 10.0), ("DEABC1", 12.0)])
    assert targets.for_site("DE") == {"ABC1": 10.0}
    assert targets.conflicts == [
        {"site": "DE", "sku": "ABC1", "kept": 10.0, "ignored": 12.0}
    ]


def test_search_string_matches_the_flow_find_input() -> None:
    targets = load_targets([("UKZMCL0006", 14.9), ("UKQPCT0005", 9.9)])
    assert targets.search_terms("uk") == ["*QPCT0005", "*ZMCL0006"]
    assert targets.search_string("UK") == "*QPCT0005 *ZMCL0006"
    assert targets.search_string("US") == ""


def test_write_scope_allows_only_qty_and_price() -> None:
    ok = [
        Change(row=3, sku="A", field="price", old=1.0, new=2.0, reason=""),
        Change(row=4, sku="B", field="qty", old=1.0, new=2.0, reason=""),
    ]
    validate_write_scope(ok)
    validate_write_scope(ok, uploaded_columns={"E", "F"})
    validate_write_scope(ok, uploaded_columns={"e", "f"})

    with pytest.raises(ValueError, match="越界字段"):
        validate_write_scope(
            [Change(row=5, sku="C", field="postage", old=0.0, new=1.0, reason="")]  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="超出白名单"):
        validate_write_scope(ok, uploaded_columns={"E", "F", "G"})

    with pytest.raises(ValueError, match="超出白名单"):
        validate_write_scope(ok, uploaded_columns={"D"})

# --------------------------------------------------------------------------
# 实际 SKU：KMP 最长匹配
# --------------------------------------------------------------------------
def test_kmp_finds_all_occurrences_including_overlaps() -> None:
    assert kmp_search("ABABABA", "ABA") == [0, 2, 4]
    assert kmp_search("P10ZMHB0004US", "ZMHB0004US") == [3]
    assert kmp_search("nothing here", "ZMHB0004US") == []
    assert kmp_search("abc", "") == []


def test_longest_match_prefers_the_longest_catalog_code() -> None:
    catalog = ["PCPB0028", "PCPB0028US", "P10PCPB0028US"]
    match = longest_match("PCPB0028US x2", catalog)

    assert match is not None
    assert match.sku == "PCPB0028US"      # 10 个字符胜过 PCPB0028 的 8 个
    assert match.matched_length == 10
    assert match.position == 0
    assert match.suffix == " x2"
    assert match.prefix == ""


def test_longest_match_reads_a_pack_prefix() -> None:
    match = longest_match("P10ZMHB0004US", ["ZMHB0004US", "ZMHB0004"])
    assert match is not None
    assert match.sku == "ZMHB0004US"
    assert match.position == 3
    assert match.prefix == "P10"
    assert match.residue == "P10"


def test_longest_match_is_case_insensitive_but_returns_catalog_spelling() -> None:
    match = longest_match("pcpb0028us x4", ["PCPB0028US"])
    assert match is not None
    assert match.sku == "PCPB0028US"
    assert match.suffix == " x4"


def test_longest_match_returns_none_without_a_candidate() -> None:
    assert longest_match("ZZZZ9999", ["ABC123"]) is None


@pytest.mark.parametrize(
    ("residue", "expected"),
    [("", 1), (" x2", 2), ("x12", 12), (" P10", 10), ("p3", 3), ("-LT-G", None), ("x", None)],
)
def test_parse_quantity_marker(residue: str, expected: int | None) -> None:
    assert parse_quantity_marker(residue) == expected


def test_stock_uses_longest_match_and_pack_prefix() -> None:
    rows = [
        DatasheetRow(3, "1", "", "ZMHB0004US", qty=50.0, price=1.0, postage=0.0),
        DatasheetRow(4, "1", "", "ZMHB0004US x2", qty=999.0, price=1.0, postage=0.0),
        DatasheetRow(5, "1", "", "P10ZMHB0004US", qty=50.0, price=1.0, postage=0.0),
    ]
    catalog = ["ZMHB0004US", "ZMHB0004"]
    plan = plan_stock_changes(rows, {"ZMHB0004US": 101}, catalog=catalog)

    assert [(c.row, c.new) for c in plan.changes] == [(3, 101.0), (4, 50.0), (5, 10.0)]
    assert [c.reason for c in plan.changes][1:] == [
        "实际 SKU ZMHB0004US 库存 101 ÷ 打包数 2",
        "实际 SKU ZMHB0004US 库存 101 ÷ 打包数 10",
    ]
    assert plan.unresolved == []


def test_stock_reports_unknown_leftovers_instead_of_guessing() -> None:
    rows = [
        DatasheetRow(3, "1", "", "ZMHB0004US-LT-G", qty=50.0, price=1.0, postage=0.0),
        DatasheetRow(4, "1", "", "QQQQ7777", qty=50.0, price=1.0, postage=0.0),
    ]
    plan = plan_stock_changes(rows, {"ZMHB0004US": 101}, catalog=["ZMHB0004US"])

    assert plan.changes == []
    assert [item["sku"] for item in plan.unresolved] == ["ZMHB0004US-LT-G", "QQQQ7777"]
    assert "认不出打包数" in plan.unresolved[0]["reason"]
    assert "找不到任何匹配" in plan.unresolved[1]["reason"]

def test_groups_follow_row_id_even_for_adjacent_rows_with_different_ids() -> None:
    # 第 20/21 行紧挨着，但各有 Row ID -> 两组，不能因为 SKU 相同就合并
    rows = [
        DatasheetRow(19, "4558719", "", "PCPB0028US", qty=200.0, price=18.65, postage=0.0),
        DatasheetRow(20, "4558721", "", "PCPB0028US", qty=200.0, price=29.65, postage=0.0),
        DatasheetRow(21, "", "", "PCPB0028US x2", qty=50.0, price=57.80, postage=None),
        DatasheetRow(22, "4558800", "", "PCPB0028US", qty=50.0, price=19.90, postage=0.0),
    ]
    from ebay_mcp_server.providers.soldeazy_pricing import group_rows

    groups = [group for group, _row in group_rows(rows)]
    assert groups == ["4558719", "4558721", "4558721", "4558800"]

    ladders = infer_pack_factors(rows)
    assert set(ladders) == {"4558719", "4558721", "4558800"}
    # 每组各自算基价：只有 4558721 那一组有两行，倍数才有意义
    assert ladders["4558721"].factors == {20: 1, 21: 2}
    assert ladders["4558719"].factors == {19: 1}

def test_lone_row_below_minimum_is_treated_as_a_single_unit() -> None:
    # 2026-11-02 确认：组内孤身且现价低于最低售价 -> 就是单件，直接改。
    # 即使 SKU 上带 x4 也不按 4 件放大。
    rows = [
        DatasheetRow(12, "4546602", "", "ZMHB0004US x4", qty=50.0, price=91.48, postage=0.0),
        DatasheetRow(13, "4546658", "", "ZMHB0004US", qty=50.0, price=28.48, postage=0.0),
    ]
    plan = plan_price_changes(rows, {"ZMHB0004": 200.0})

    assert [(c.row, c.new) for c in plan.changes] == [(12, 200.0), (13, 200.0)]
    assert all("独自成组" in note for note in plan.notes)
    assert all(
        ladder.factors == {ladder.base_row: 1} for ladder in plan.ladders.values()
    )


def test_lone_row_above_minimum_is_left_alone() -> None:
    rows = [DatasheetRow(5, "4546600", "", "P10ZMHB0004US", qty=50.0, price=299.78, postage=0.0)]
    plan = plan_price_changes(rows, {"ZMHB0004": 200.0})
    assert plan.changes == []
