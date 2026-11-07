"""不可变计划的单元测试：起草 → 冻结 → 校验 → 篡改必被拒 → 归档。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ebay_mcp_server.providers import soldeazy_plan as plan_mod
from ebay_mcp_server.providers.soldeazy_plan import (
    ChangePlan,
    PlanError,
    PlanItem,
    archive,
    freeze,
    load_verified,
    new_plan_id,
    write_draft,
)


def make_plan(tmp_path: Path) -> ChangePlan:
    return ChangePlan(
        plan_id="price-test-1",
        kind="price",
        site="US",
        shop={"id": "159", "name": "FUN"},
        created_at="2026-11-07T00:00:00+00:00",
        items=[
            PlanItem(rowid="4512957", sku="JJPC0029", field="price", old=21.9, new=25.0),
            PlanItem(rowid="4512958", sku="JJPC0029", field="price", old=21.9, new=25.0),
        ],
    )


def test_draft_can_be_rewritten(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    plan.items[0].new = 26.0
    write_draft(tmp_path, plan)  # 草稿允许覆盖
    path = tmp_path / "price-test-1.json"
    assert json.loads(path.read_text(encoding="utf-8"))["items"][0]["new"] == 26.0


def test_freeze_creates_sidecar_and_readonly(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    info = freeze(tmp_path, plan)
    assert len(info["sha256"]) == 64
    path = tmp_path / "price-test-1.json"
    assert path.with_suffix(".json.sha256").exists()
    assert not os.access(path, os.W_OK), "冻结后的文件应当是只读的"


def test_load_verified_accepts_untouched_plan(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    info = freeze(tmp_path, plan)
    loaded, digest = load_verified(tmp_path, "price-test-1")
    assert digest == info["sha256"]
    assert [item.rowid for item in loaded.items] == ["4512957", "4512958"]
    assert loaded.status == "confirmed"


def test_load_verified_rejects_tampering(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    freeze(tmp_path, plan)
    path = tmp_path / "price-test-1.json"
    os.chmod(path, 0o644)  # 模拟有人绕过只读去改
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][0]["new"] = 99.0
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(PlanError, match="被改过"):
        load_verified(tmp_path, "price-test-1")


def test_load_verified_requires_confirmation(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    # 没有旁车文件
    with pytest.raises(PlanError, match="sha256"):
        load_verified(tmp_path, "price-test-1")


def test_freeze_refuses_second_confirmation(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    freeze(tmp_path, plan)
    plan.items[0].new = 30.0
    with pytest.raises(PlanError, match="已经冻结"):
        freeze(tmp_path, plan)


def test_archive_moves_plan_and_sidecar(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    write_draft(tmp_path, plan)
    freeze(tmp_path, plan)
    archive(tmp_path, "price-test-1")
    assert not (tmp_path / "price-test-1.json").exists()
    assert (tmp_path / "archive" / "price-test-1.json").exists()
    assert (tmp_path / "archive" / "price-test-1.json.sha256").exists()


def test_digest_changes_with_content(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    first = plan.digest()
    plan.items[0].new = 26.0
    assert plan.digest() != first


def test_new_plan_id_is_kind_prefixed() -> None:
    assert new_plan_id("stock").startswith("stock-")
