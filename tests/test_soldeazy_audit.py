"""改动历史（审计）的读写契约测试。

重点是**写入方和读取方必须对得上**：``soldeazy_apply_plan`` 写
``<plan_id>.audit.jsonl``，而 ``soldeazy_change_history`` 过去只读旧链路的
``soldeazy-writes.jsonl``，旧链路一停用，历史就永远是空的。
"""

from __future__ import annotations

import asyncio
import json

from ebay_mcp_server import server
from ebay_mcp_server.providers.soldeazy_apply import append_audit, read_audit


def _plan(
    directory,
    plan_id: str,
    *,
    site: str = "US",
    kind: str = "price",
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "plan_id": plan_id,
        "kind": kind,
        "site": site,
        "shop": {"name": "EBAY FUN", "id": "159"},
        "created_at": "2026-11-09T09:00:00+00:00",
        "items": [],
    }
    (directory / f"{plan_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _raw_audit(directory, plan_id: str, *, at: str, applied: int = 1) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{plan_id}.audit.jsonl"
    line = {
        "at": at,
        "plan_id": plan_id,
        "rowid": "4522717",
        "success": True,
        "applied": applied,
        "failed": [],
        "warnings": [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def test_read_audit_works_with_the_real_writer(tmp_path):
    """真正的写入函数写出来的行，读取方必须认得。"""

    _plan(tmp_path, "price-20261109-001")
    append_audit(
        tmp_path / "price-20261109-001.audit.jsonl",
        "price-20261109-001",
        "4522717",
        {"success": True, "applied": [{"row": 3}], "failed": [], "warnings": []},
    )

    records = read_audit(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["plan_id"] == "price-20261109-001"
    assert record["site"] == "US"
    assert record["kind"] == "price"
    assert record["applied"] == 1
    assert record["source"] == "plan-audit"
    assert record["at"]


def test_read_audit_filters_by_site_and_kind_with_stock_alias(tmp_path):
    _plan(tmp_path, "p1", site="US", kind="price")
    _plan(tmp_path, "q1", site="US", kind="qty")
    _plan(tmp_path, "p2", site="UK", kind="price")
    _raw_audit(tmp_path, "p1", at="2026-11-09T01:00:00+00:00")
    _raw_audit(tmp_path, "q1", at="2026-11-09T02:00:00+00:00")
    _raw_audit(tmp_path, "p2", at="2026-11-09T03:00:00+00:00")

    assert [r["plan_id"] for r in read_audit(tmp_path)] == ["p2", "q1", "p1"]
    assert [r["plan_id"] for r in read_audit(tmp_path, site="us")] == ["q1", "p1"]
    # 计划里记的是 qty，对外说 stock，两者必须等价
    assert [r["plan_id"] for r in read_audit(tmp_path, kind="stock")] == ["q1"]
    assert [r["plan_id"] for r in read_audit(tmp_path, kind="qty")] == ["q1"]
    assert [r["plan_id"] for r in read_audit(tmp_path, kind="price")] == ["p2", "p1"]


def test_read_audit_sees_archived_plans(tmp_path):
    """计划归档后 json 和审计都挪进了 archive/，历史不能因此断掉。"""

    archive = tmp_path / "archive"
    _plan(archive, "old-1")
    _raw_audit(archive, "old-1", at="2026-11-08T10:00:00+00:00")
    _plan(tmp_path, "new-1")
    _raw_audit(tmp_path, "new-1", at="2026-11-09T10:00:00+00:00")

    records = read_audit(tmp_path)
    assert [r["plan_id"] for r in records] == ["new-1", "old-1"]


def test_read_audit_ignores_reconcile_sidecar(tmp_path):
    """真实数据上踩到的坑：<plan_id>.reconcile.json 也有 plan_id 但没有
    site/kind，且排序在计划本体之后，会把好数据覆盖成空。"""

    _plan(tmp_path, "p1", site="US", kind="price")
    sidecar = tmp_path / "p1.reconcile.json"
    sidecar.write_text(
        json.dumps(
            {"plan_id": "p1", "checked_at": "2026-11-09T08:00:00+00:00", "matched": 1},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "p1.json.sha256").write_text("deadbeef", encoding="utf-8")
    _raw_audit(tmp_path, "p1", at="2026-11-09T08:00:00+00:00")

    records = read_audit(tmp_path)
    assert len(records) == 1
    assert records[0]["site"] == "US"
    assert records[0]["kind"] == "price"
    assert len(read_audit(tmp_path, site="US")) == 1
    assert len(read_audit(tmp_path, kind="price")) == 1


def test_read_audit_skips_corrupt_lines_and_missing_dirs(tmp_path):
    _plan(tmp_path, "p1")
    path = tmp_path / "p1.audit.jsonl"
    path.write_text(
        '{"at":"2026-11-09T01:00:00+00:00","plan_id":"p1","applied":2}\n'
        "这不是 JSON\n"
        "\n"
        '{"at":"2026-11-09T02:00:00+00:00","plan_id":"p1","applied":3}\n',
        encoding="utf-8",
    )

    records = read_audit(tmp_path)
    assert [r["applied"] for r in records] == [3, 2]
    assert read_audit(tmp_path / "not-there") == []


def test_change_history_merges_new_audit_and_legacy_manifest(tmp_path, monkeypatch):
    plan_dir = tmp_path / "plans"
    _plan(plan_dir, "p-new")
    _raw_audit(plan_dir, "p-new", at="2026-11-09T10:00:00+00:00", applied=4)

    manifest = tmp_path / "soldeazy-writes.jsonl"
    manifest.write_text(
        json.dumps(
            {"site": "US", "kind": "price", "search": "*JJPC0029", "changes": []},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(server, "_plan_dir", lambda: plan_dir)
    monkeypatch.setattr(server, "_manifest_path", lambda: str(manifest))

    result = asyncio.run(server.soldeazy_change_history())
    assert result["success"] is True
    data = result["data"]
    assert data["count"] == 2
    assert data["sources"] == {"plan_audit": 1, "legacy_manifest": 1}
    # 新链路的记录在前（有时间戳），旧清单兜底在后
    assert data["records"][0]["plan_id"] == "p-new"
    assert data["records"][0]["applied"] == 4


def test_change_history_reports_empty_and_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_plan_dir", lambda: tmp_path / "no-plans")
    monkeypatch.setattr(server, "_manifest_path", lambda: str(tmp_path / "no.jsonl"))

    result = asyncio.run(server.soldeazy_change_history())
    assert result["success"] is True
    assert result["data"]["count"] == 0
    assert result["data"]["sources"] == {"plan_audit": 0, "legacy_manifest": 0}


def test_change_history_rejects_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_plan_dir", lambda: tmp_path)
    monkeypatch.setattr(server, "_manifest_path", lambda: str(tmp_path / "none.jsonl"))

    result = asyncio.run(server.soldeazy_change_history(kind="bogus"))
    assert result["success"] is False
    assert result["error"]["code"] == "SOLDEAZY_HISTORY_KIND"
