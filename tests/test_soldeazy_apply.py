"""计划构建器的单元测试：SKU 解析、母体展开、冲突不猜。"""

from __future__ import annotations

from ebay_mcp_server.providers.soldeazy_apply import build_items


def live_fixture() -> dict:
    return {
        ("4512957", "JJPC0029"): {"rowid": "4512957", "parent": "JJPC0029", "sku": "JJPC0029",
                                  "qty": 100, "price": 21.9},
        ("4522717", "JJPC0028"): {"rowid": "4522717", "parent": "排插-P", "sku": "JJPC0028",
                                  "qty": 100, "price": 17.99},
        ("4522717", "JJPC0029"): {"rowid": "", "parent": "排插-P", "sku": "JJPC0029",
                                  "qty": 100, "price": 21.9},
        ("4522717", "JJPC0030"): {"rowid": "", "parent": "排插-P", "sku": "JJPC0030",
                                  "qty": 100, "price": 16.9},
    }


def test_price_exact_match_writes_only_that_child() -> None:
    items, report = build_items(live_fixture(), "price", {"JJPC0029": 30.0})
    # JJPC0029 出现在两个数据表里，两条都要改
    assert len(items) == 2
    assert {item.rowid for item in items} == {"4512957", "4522717"}
    assert all(item.field == "price" for item in items)
    assert report["missing"] == []


def test_price_skips_unchanged_value() -> None:
    items, _ = build_items(live_fixture(), "price", {"JJPC0028": 17.99})
    assert items == []


def test_price_ambiguous_prefix_is_reported_not_guessed() -> None:
    items, report = build_items(live_fixture(), "price", {"JJPC002": 50.0})
    # 前缀 JJPC002 命中 JJPC0028 / JJPC0029 两个子体 → 冲突，不猜
    assert items == []
    assert report["conflicts"]["JJPC002"] == ["JJPC0028", "JJPC0029"]


def test_stock_by_parent_expands_all_children() -> None:
    items, report = build_items(live_fixture(), "qty", {"排插-P": 50})
    assert len(items) == 3
    assert {item.sku for item in items} == {"JJPC0028", "JJPC0029", "JJPC0030"}
    assert all(item.rowid == "4522717" for item in items)
    assert all(item.field == "qty" for item in items)
    assert report["missing"] == []


def test_stock_unknown_parent_is_reported() -> None:
    items, report = build_items(live_fixture(), "qty", {"没有这个母体": 10})
    assert items == []
    assert report["missing"] == ["没有这个母体"]


def test_stock_skips_rows_already_at_target() -> None:
    items, _ = build_items(live_fixture(), "qty", {"排插-P": 100})
    assert items == []
