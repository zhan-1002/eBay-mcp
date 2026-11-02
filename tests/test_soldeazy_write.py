"""写操作闸门测试：令牌、一次性消费、漂移检查、清单落盘（纯逻辑）。"""

from __future__ import annotations

import json
import time

from ebay_mcp_server.providers.soldeazy_pricing import Change
from ebay_mcp_server.providers.soldeazy_write import (
    PlannedWrite,
    RowState,
    WriteRegistry,
    append_manifest,
    build_token,
    check_drift,
    rows_to_state,
    same_plan,
    to_cell_changes,
)

CHANGES = [
    {"row": 6, "sku": "ZMHB0004US", "old": 31.28, "new": 195.0},
    {"row": 8, "sku": "ZMHB0004US x2", "old": 57.8, "new": 395.0},
]
EXPECTED = [
    RowState("4546601", "ZMHB0004US", 31.28, 50.0),
    RowState("4546602", "ZMHB0004US x4", 91.48, 50.0),
]


def test_token_is_deterministic_and_bound_to_content() -> None:
    a = build_token("price", "US", "*ZMHB0004", CHANGES, EXPECTED)
    b = build_token("price", "us", "*ZMHB0004", list(reversed(CHANGES)), EXPECTED)
    assert a == b  # 站点大小写/顺序不影响

    other = build_token("price", "DE", "*ZMHB0004", CHANGES, EXPECTED)
    assert other != a  # 换站点就换令牌

    tampered = [dict(CHANGES[0], new=999.0), CHANGES[1]]
    assert build_token("price", "US", "*ZMHB0004", tampered, EXPECTED) != a


def test_registry_consumes_the_token_only_once() -> None:
    registry = WriteRegistry(ttl=60)
    plan = registry.register("price", "US", "*A", CHANGES, EXPECTED)

    assert isinstance(plan, PlannedWrite)
    assert registry.consume(plan.token) is not None
    assert registry.consume(plan.token) is None  # 第二次拿不到


def test_registry_drops_expired_tokens() -> None:
    registry = WriteRegistry(ttl=0)
    plan = registry.register("stock", "US", "*A", CHANGES, EXPECTED)
    time.sleep(0.01)
    assert registry.consume(plan.token) is None


def test_registry_rejects_unknown_tokens() -> None:
    assert WriteRegistry().consume("nope") is None


def test_drift_passes_when_nothing_changed() -> None:
    report = check_drift(EXPECTED, list(EXPECTED))
    assert report.ok
    assert report.problems == []


def test_drift_detects_price_and_quantity_changes() -> None:
    current = [
        RowState("4546601", "ZMHB0004US", 32.99, 50.0),   # 价格被人改过
        RowState("4546602", "ZMHB0004US x4", 91.48, 10.0),  # 数量变了
    ]
    report = check_drift(EXPECTED, current)
    assert not report.ok
    assert any("价格已变" in p for p in report.problems)
    assert any("数量已变" in p for p in report.problems)


def test_drift_detects_missing_and_extra_datasheets() -> None:
    report = check_drift(
        EXPECTED,
        [RowState("4546601", "ZMHB0004US", 31.28, 50.0), RowState("9999", "NEW", 1.0, 1.0)],
    )
    assert not report.ok
    assert any("找不到了" in p for p in report.problems)
    assert any("多出未预期" in p for p in report.problems)


def test_same_plan_compares_rows_and_values() -> None:
    actual = [
        Change(row=6, sku="ZMHB0004US", field="price", old=31.28, new=195.0, reason=""),
        Change(row=8, sku="ZMHB0004US x2", field="price", old=57.8, new=395.0, reason=""),
    ]
    assert same_plan(CHANGES, actual).ok

    drifted = [actual[0], Change(row=8, sku="x", field="price", old=57.8, new=400.0, reason="")]
    report = same_plan(CHANGES, drifted)
    assert not report.ok
    assert report.problems


def test_to_cell_changes_maps_field_to_column() -> None:
    changes = [Change(row=3, sku="A", field="price", old=1.0, new=2.0, reason="")]
    assert to_cell_changes(changes, "price") == [("price", 3, 2.0)]
    assert to_cell_changes(changes, "stock") == [("qty", 3, 2.0)]


def test_rows_to_state_parses_search_records() -> None:
    states = rows_to_state([{"rowid": "1", "sku": "A", "price": "12.5", "qty": "50"}])
    assert states[0] == RowState(rowid="1", sku="A", price=12.5, qty=50.0)


def test_manifest_appends_one_json_line_per_write(tmp_path) -> None:
    path = tmp_path / "manifest.jsonl"
    append_manifest(path, {"token": "abc", "kind": "price"})
    append_manifest(path, {"token": "def", "kind": "stock"})

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["token"] == "abc"
    assert "at" in json.loads(lines[1])
