"""写操作的两道闸：预览签名（confirm_token）与现场漂移检查。

写工具不接受「直接改」：必须先用预览工具拿到 ``confirm_token``，令牌绑定
站点 + 搜索串 + 逐行新旧值。真正写之前再搜一次，如果线上行与预览时不一致
（多了行、少了行、价格被别人改过），整批拒绝——这对应影刀流程里那个
「人工核对弹框」，只是换成了机器可校验的形式。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

WriteKind = Literal["price", "stock"]

#: 令牌有效期（秒）。过期就得重新预览。
DEFAULT_TTL = 900


@dataclass(frozen=True)
class RowState:
    """预览时看到的一行的关键值，用来和现场比对。"""

    rowid: str
    sku: str
    price: float
    qty: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "rowid": self.rowid,
            "sku": self.sku,
            "price": self.price,
            "qty": self.qty,
        }


@dataclass(frozen=True)
class PlannedWrite:
    token: str
    kind: WriteKind
    site: str
    query: str
    changes: list[dict[str, Any]]
    expected: list[RowState]
    created_at: float
    expires_at: float
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "kind": self.kind,
            "site": self.site,
            "query": self.query,
            "changes": self.changes,
            "expected": [row.as_dict() for row in self.expected],
            "expires_in": max(0, int(self.expires_at - time.time())),
        }


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_token(kind: WriteKind, site: str, query: str, changes: Sequence[dict[str, Any]],
                expected: Sequence[RowState]) -> str:
    """同样的预览内容必然得到同样的令牌，便于日志关联。"""

    payload = {
        "kind": kind,
        "site": site.strip().upper(),
        "query": query.strip(),
        "changes": sorted(
            (
                {"row": c.get("row"), "old": c.get("old"), "new": c.get("new")}
                for c in changes
            ),
            key=lambda c: (c["row"] or 0),
        ),
        "expected": sorted(
            ({"rowid": r.rowid, "price": r.price, "qty": r.qty} for r in expected),
            key=lambda r: r["rowid"],
        ),
    }
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return digest[:24]


class WriteRegistry:
    """进程内的待写队列：预览登记，写入时消费（一次性）。"""

    def __init__(self, ttl: int = DEFAULT_TTL) -> None:
        self.ttl = ttl
        self._pending: dict[str, PlannedWrite] = {}

    def register(
        self,
        kind: WriteKind,
        site: str,
        query: str,
        changes: Sequence[dict[str, Any]],
        expected: Sequence[RowState],
        context: dict[str, Any] | None = None,
    ) -> PlannedWrite:
        now = time.time()
        token = build_token(kind, site, query, changes, expected)
        plan = PlannedWrite(
            token=token,
            kind=kind,
            site=site.strip().upper(),
            query=query.strip(),
            changes=list(changes),
            expected=list(expected),
            created_at=now,
            expires_at=now + self.ttl,
            context=dict(context or {}),
        )
        self.prune()
        self._pending[token] = plan
        return plan

    def consume(self, token: str) -> PlannedWrite | None:
        """取出并作废；过期或不存在都返回 ``None``。"""

        self.prune()
        plan = self._pending.pop(token.strip(), None)
        if plan is None or plan.expired:
            return None
        return plan

    def prune(self) -> None:
        for token in [t for t, plan in self._pending.items() if plan.expired]:
            self._pending.pop(token, None)

    def __len__(self) -> int:  # pragma: no cover - 便于调试
        return len(self._pending)


@dataclass(frozen=True)
class DriftReport:
    ok: bool
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "problems": self.problems}


def check_drift(expected: Sequence[RowState], current: Iterable[RowState]) -> DriftReport:
    """比对「预览时看到的行」与「现在线上的行」，任何不一致都算漂移。"""

    problems: list[str] = []
    by_rowid = {row.rowid: row for row in current if row.rowid}

    for want in expected:
        got = by_rowid.pop(want.rowid, None)
        if got is None:
            problems.append(f"数据表 {want.rowid}（{want.sku}）在线上找不到了")
            continue
        if abs(got.price - want.price) > 0.005:
            problems.append(
                f"数据表 {want.rowid}（{want.sku}）价格已变：预览 {want.price:g} → 现在 {got.price:g}"
            )
        if abs(got.qty - want.qty) > 0.005:
            problems.append(
                f"数据表 {want.rowid}（{want.sku}）数量已变：预览 {want.qty:g} → 现在 {got.qty:g}"
            )

    for leftover in by_rowid.values():
        problems.append(f"多出未预期的数据表 {leftover.rowid}（{leftover.sku}）")

    return DriftReport(ok=not problems, problems=problems)


def append_manifest(path: str | Path, record: dict[str, Any]) -> Path:
    """每笔写入落一行 JSONL，便于事后追溯（对应影刀那边的写操作清单）。"""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = _canonical({**record, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
    return target


def rows_to_state(records: Iterable[dict[str, Any]]) -> list[RowState]:
    """把搜索结果转成可比对的状态行。"""

    states: list[RowState] = []
    for record in records:
        states.append(
            RowState(
                rowid=str(record.get("rowid") or "").strip(),
                sku=str(record.get("sku") or "").strip(),
                price=float(record.get("price") or 0),
                qty=float(record.get("qty") or 0),
            )
        )
    return states

def same_plan(planned: Sequence[dict[str, Any]], actual: Sequence[Any]) -> DriftReport:
    """预览登记的改动与「现在重新算一遍」的结果是否一致。

    `actual` 是 `Change` 列表（有 row/old/new 三个属性）。
    """

    want = sorted((int(c["row"]), round(float(c["old"]), 4), round(float(c["new"]), 4))
                  for c in planned)
    got = sorted((int(c.row), round(float(c.old), 4), round(float(c.new), 4)) for c in actual)
    if want == got:
        return DriftReport(ok=True)
    problems = [f"预览 {len(want)} 行、现在 {len(got)} 行"] if len(want) != len(got) else []
    for w, g in zip(want, got):
        if w != g:
            problems.append(f"行 {w[0]}：预览 {w[1]:g}->{w[2]:g}，现在 {g[1]:g}->{g[2]:g}")
    return DriftReport(ok=False, problems=problems[:10])


def to_cell_changes(changes: Sequence[Any], field: Literal["price", "stock"]) -> list[tuple[str, int, Any]]:
    """把 Change 列表转成 (字段, 行号, 新值)，供 soldeazy_workbook 改写。"""

    column = "price" if field == "price" else "qty"
    return [(column, int(change.row), change.new) for change in changes]
