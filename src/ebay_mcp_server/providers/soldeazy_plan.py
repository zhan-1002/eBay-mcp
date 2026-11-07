"""不可变改动计划：起草 → 用户确认冻结 → 只读执行 → 对账。

规则（2026-11-07 与用户确认）：

1. 计划是一份 JSON，``status=draft`` 时可以重新生成；
2. 用户确认后 ``freeze()``：写入 sha256 旁车文件并把文件设成只读，
   之后任何程序都不得修改它——``load_verified()`` 每次执行前重算哈希，
   对不上直接拒绝；
3. 冻结后的计划只用于执行与对账，执行结果写进**另一个**审计文件，不回写计划；
4. 发现计划有误时另起一份新计划（``supersedes`` 指向旧计划），旧的原样归档。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DRAFT = "draft"
CONFIRMED = "confirmed"
APPLIED = "applied"


class PlanError(Exception):
    """计划文件状态不对（被改过、没确认、不存在）。"""


@dataclass
class PlanItem:
    rowid: str
    sku: str
    field: str  # "price" | "qty"
    old: float
    new: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "rowid": self.rowid,
            "sku": self.sku,
            "field": self.field,
            "old": self.old,
            "new": self.new,
        }


@dataclass
class ChangePlan:
    plan_id: str
    kind: str
    site: str
    shop: dict[str, str]
    created_at: str
    items: list[PlanItem] = field(default_factory=list)
    status: str = DRAFT
    supersedes: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "kind": self.kind,
            "site": self.site,
            "shop": self.shop,
            "created_at": self.created_at,
            "status": self.status,
            "supersedes": self.supersedes,
            "note": self.note,
            "items": [item.as_dict() for item in self.items],
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def new_plan_id(kind: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"{kind}-{stamp}"


def plan_file(directory: Path, plan: ChangePlan) -> Path:
    return directory / f"{plan.plan_id}.json"


def digest_file(directory: Path, plan: ChangePlan) -> Path:
    return directory / f"{plan.plan_id}.json.sha256"


def write_draft(directory: Path, plan: ChangePlan) -> Path:
    """写一份可再生成的草稿（只有 draft 允许覆盖）。"""

    directory.mkdir(parents=True, exist_ok=True)
    path = plan_file(directory, plan)
    if path.exists():
        existing = load_raw(path)
        if existing.get("status") != DRAFT:
            raise PlanError(
                f"{path.name} 已冻结（status={existing.get('status')}），不能覆盖；"
                "请另起一份新计划"
            )
    plan.status = DRAFT
    path.write_text(
        json.dumps(plan.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def freeze(directory: Path, plan: ChangePlan) -> dict[str, Any]:
    """确认冻结：写最终文件 + sha256 旁车 + 只读属性。"""

    path = plan_file(directory, plan)
    if path.exists():
        existing = load_raw(path)
        if existing.get("status") == CONFIRMED:
            raise PlanError(f"{path.name} 已经冻结过了，不能重复确认")

    plan.status = CONFIRMED
    path.write_text(
        json.dumps(plan.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    digest = plan.digest()
    digest_file(directory, plan).write_text(digest + "\n", encoding="utf-8")
    os.chmod(path, 0o444)  # 只读，防手滑
    return {"path": str(path), "sha256": digest, "items": len(plan.items)}


def load_raw(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_verified(directory: Path, plan_id: str) -> tuple[ChangePlan, str]:
    """读计划并校验哈希；被改过就拒绝执行。"""

    path = directory / f"{plan_id}.json"
    sidecar = directory / f"{plan_id}.json.sha256"
    if not path.exists():
        raise PlanError(f"找不到计划 {plan_id}")
    if not sidecar.exists():
        raise PlanError(f"{plan_id} 没有 sha256 旁车文件，来源不可信，拒绝执行")

    expected = sidecar.read_text(encoding="utf-8").strip()
    raw = load_raw(path)
    plan = ChangePlan(
        plan_id=raw["plan_id"],
        kind=raw["kind"],
        site=raw.get("site", ""),
        shop=raw.get("shop") or {},
        created_at=raw.get("created_at", ""),
        items=[PlanItem(**item) for item in raw.get("items", [])],
        status=raw.get("status", DRAFT),
        supersedes=raw.get("supersedes", ""),
        note=raw.get("note", ""),
    )
    actual = plan.digest()
    if actual != expected:
        raise PlanError(
            f"{plan_id} 的内容与确认时不一致（文件被改过），拒绝执行"
        )
    if plan.status != CONFIRMED:
        raise PlanError(f"{plan_id} 状态是 {plan.status}，未确认的计划不能执行")
    return plan, expected


def archive(directory: Path, plan_id: str) -> Path:
    """把旧计划整体挪进 archive/，保持原样。"""

    target_dir = directory / "archive"
    target_dir.mkdir(parents=True, exist_ok=True)
    moved = None
    for suffix in (".json", ".json.sha256"):
        source = directory / f"{plan_id}{suffix}"
        if source.exists():
            target = target_dir / source.name
            shutil.move(str(source), str(target))
            moved = target_dir
    if moved is None:
        raise PlanError(f"没有可归档的 {plan_id}")
    return moved
