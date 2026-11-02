"""Soldeazy datasheet pricing and stock rules (pure functions, no I/O).

These rules were reverse-engineered from the production workflow
``soldeazy_2_dsheet_price.py`` plus the operator's own correction sheet, and are
validated against a real ``export_dsheet`` file:

* A datasheet row carries ``Row ID / P.SKU / SKU / Qty / Price / Post.D.``.
  ``SKU`` may carry a pack suffix (``... x2``) and/or a site suffix (``...US``).
* Postage is per datasheet, not per row: continuation rows (blank ``Row ID``)
  usually leave ``Post.D.`` empty and inherit the group's single value.
* The minimum selling price (最低售价) is a *total*: ``Price + Post.D.``. Rows
  whose total is below the target are raised so the total lands exactly on it.
  Prices are only ever raised, never lowered.
* Stock is owned by the *actual* SKU (the base code), while the listing sells
  packs; a pack listing's quantity is ``floor(stock / pack)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, Sequence

PackPolicy = Literal["same", "skip", "multiply"]
PackSource = Literal["ratio", "sku"]

#: Datasheet columns the operator is allowed to touch, by change field.
EDITABLE_COLUMNS: dict[str, str] = {"qty": "E", "price": "F"}

#: Sites the price sheet is split into.
DEFAULT_SITES: tuple[str, ...] = ("UK", "DE", "US")

#: Prefixes the price sheet strips before matching datasheet SKUs.
SPECIAL_PREFIXES: tuple[str, ...] = ("EF-", "EF2-")

#: 站点后缀，用于把 ``PCPB0028US`` 拆成货号 + 站点。
SITE_CODES: frozenset[str] = frozenset(
    {"US", "UK", "DE", "FR", "IT", "ES", "AU", "CA", "JP", "EU", "NL", "PL"}
)


@dataclass(frozen=True)
class DatasheetRow:
    """One row of a Soldeazy ``export_dsheet`` worksheet."""

    row: int
    rowid: str
    parent_sku: str
    sku: str
    qty: float
    price: float
    postage: float | None


@dataclass(frozen=True)
class Change:
    """A single planned write; ``field`` is what would be sent to Soldeazy."""

    row: int
    sku: str
    field: Literal["price", "qty"]
    old: float
    new: float
    reason: str
    group_postage: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "row": self.row,
            "sku": self.sku,
            "field": self.field,
            "old": self.old,
            "new": self.new,
            "reason": self.reason,
            "group_postage": self.group_postage,
        }


@dataclass(frozen=True)
class PostageMap:
    """Effective postage per row, plus the groups whose postage is ambiguous."""

    by_row: dict[int, float]
    ambiguous_rows: set[int]
    warnings: list[str]


@dataclass(frozen=True)
class PricePlan:
    changes: list[Change]
    unmatched_targets: list[str]
    skipped_packs: list[str]
    ambiguous_groups: list[str]
    matched_rows: int
    notes: list[str] = field(default_factory=list)
    ladders: dict[str, GroupLadder] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "changes": [change.as_dict() for change in self.changes],
            "changed_rows": len(self.changes),
            "matched_rows": self.matched_rows,
            "unmatched_targets": self.unmatched_targets,
            "skipped_packs": self.skipped_packs,
            "ambiguous_groups": self.ambiguous_groups,
            "notes": self.notes,
            "ladders": [ladder.as_dict() for ladder in self.ladders.values()],
        }


def group_rows(rows: Sequence[DatasheetRow]) -> list[tuple[str, DatasheetRow]]:
    """Pair every row with its datasheet group id.

    ``Row ID`` is only present on the first row of a datasheet; the following
    rows repeat the group implicitly, so it is filled forward.
    """

    grouped: list[tuple[str, DatasheetRow]] = []
    current = ""
    for row in rows:
        if row.rowid:
            current = row.rowid
        grouped.append((current, row))
    return grouped


def resolve_postage(rows: Sequence[DatasheetRow]) -> PostageMap:
    """Resolve the effective postage for every row.

    A row keeps its own value when present; otherwise it inherits the group's
    single distinct postage. Groups carrying several distinct values are
    ambiguous: those rows are flagged and left out of the plan instead of
    guessing a value.
    """

    grouped = group_rows(rows)
    per_group: dict[str, set[float]] = {}
    for group, row in grouped:
        if row.postage is not None:
            per_group.setdefault(group, set()).add(row.postage)

    by_row: dict[int, float] = {}
    ambiguous_rows: set[int] = set()
    warnings: list[str] = []
    for group, row in grouped:
        values = per_group.get(group) or set()
        if row.postage is not None:
            by_row[row.row] = row.postage
        elif len(values) == 1:
            by_row[row.row] = next(iter(values))
        elif not values:
            by_row[row.row] = 0.0
        else:
            ambiguous_rows.add(row.row)
            warnings.append(
                f"数据表 {group} 的运费不唯一 {sorted(values)}，第 {row.row} 行无法继承"
            )
    return PostageMap(by_row=by_row, ambiguous_rows=ambiguous_rows, warnings=warnings)


def parse_pack(sku: str) -> tuple[str, int]:
    """Split ``'ZMHB0004US x4'`` into ``('ZMHB0004US', 4)``."""

    text = (sku or "").strip()
    head, sep, tail = text.rpartition(" ")
    if sep and tail[:1].lower() == "x" and tail[1:].isdigit():
        return head, int(tail[1:])
    return text, 1


# --------------------------------------------------------------------------
# 实际 SKU 匹配：KMP 最长匹配
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SkuMatch:
    """A datasheet SKU resolved against the actual-SKU catalog."""

    sku: str  # 目录里的实际 SKU（原样大小写）
    matched_length: int
    position: int
    prefix: str  # 匹配段之前的残留，例如 "P10"
    suffix: str  # 匹配段之后的残留，例如 " x2"

    @property
    def residue(self) -> str:
        return f"{self.prefix}{self.suffix}"

    def as_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "matched_length": self.matched_length,
            "position": self.position,
            "prefix": self.prefix,
            "suffix": self.suffix,
        }


def _failure_table(pattern: str) -> list[int]:
    """KMP 的 next 数组：``table[i]`` = 前 i+1 个字符的最长真前缀=后缀长度。"""

    table = [0] * len(pattern)
    length = 0
    for index in range(1, len(pattern)):
        while length and pattern[index] != pattern[length]:
            length = table[length - 1]
        if pattern[index] == pattern[length]:
            length += 1
        table[index] = length
    return table


def kmp_search(text: str, pattern: str) -> list[int]:
    """Return every start offset where ``pattern`` occurs in ``text`` (KMP)."""

    if not pattern or len(pattern) > len(text):
        return []
    table = _failure_table(pattern)
    hits: list[int] = []
    matched = 0
    for index, char in enumerate(text):
        while matched and char != pattern[matched]:
            matched = table[matched - 1]
        if char == pattern[matched]:
            matched += 1
            if matched == len(pattern):
                hits.append(index - len(pattern) + 1)
                matched = table[matched - 1]
    return hits


def longest_match(display_sku: str, catalog: Sequence[str]) -> SkuMatch | None:
    """Pick the catalog SKU covering the largest span of ``display_sku``.

    与"剥后缀"相比，这里不预设规则：谁覆盖的字符最多谁就是实际 SKU，
    并且把匹配段前后的残留一并返回，供调用方判断打包数（`` x2``、``P10``）。
    同长度时取更靠前的匹配，再同则取字典序较小的，保证结果稳定。
    """

    text = (display_sku or "").strip().upper()
    if not text:
        return None

    best: SkuMatch | None = None
    seen: set[str] = set()
    for raw in catalog:
        entry = str(raw or "").strip()
        key = entry.upper()
        if not key or key in seen:
            continue
        seen.add(key)
        for position in kmp_search(text, key):
            candidate = SkuMatch(
                sku=entry,
                matched_length=len(key),
                position=position,
                prefix=display_sku.strip()[:position],
                suffix=display_sku.strip()[position + len(key) :],
            )
            if best is None or _better(candidate, best):
                best = candidate
    return best


def _better(candidate: SkuMatch, current: SkuMatch) -> bool:
    if candidate.matched_length != current.matched_length:
        return candidate.matched_length > current.matched_length
    if candidate.position != current.position:
        return candidate.position < current.position
    return candidate.sku < current.sku


def parse_quantity_marker(residue: str) -> int | None:
    """Read the pack multiplier out of the leftover text.

    ``''`` → 1、``' x2'`` → 2、``'P10'`` → 10；其余返回 ``None``（不认识就不猜）。
    """

    text = (residue or "").strip()
    if not text:
        return 1
    lowered = text.lower()
    if lowered.startswith("x") and lowered[1:].strip().isdigit() and len(lowered) <= 5:
        return int(lowered[1:].strip())
    if lowered.startswith("p") and lowered[1:].strip().isdigit() and len(lowered) <= 4:
        return int(lowered[1:].strip())
    return None


@dataclass(frozen=True)
class Residue:
    """什么被认出来了：站点后缀、打包数；认不出时 ``problem`` 说明原因。"""

    site: str
    pack: int
    problem: str = ""

    @property
    def ok(self) -> bool:
        return not self.problem


def split_residue(prefix: str, suffix: str) -> Residue:
    """把最长匹配留下的前缀/后缀拆成「站点后缀 + 打包数 + 变体尾」。

    认得的写法：前缀 ``''``/``EF-``/``EF2-``/``P10``；后缀 ``''``/``US``/
    ``US x2``/`` x4``/``-XL``（变体尾）。其余（如 ``0-RED``）判为认不出，
    不猜——这正是 ``GJHW00310-RED`` 不会被 ``GJHW0031`` 抢走的原因。
    """

    head = (prefix or "").strip()
    tail = (suffix or "").strip()

    site = ""
    upper_tail = tail.upper()
    if len(upper_tail) >= 2 and upper_tail[:2] in SITE_CODES:
        site = upper_tail[:2]
        tail = tail[2:].strip()

    head_pack = 1
    upper_head = head.upper()
    if not head or upper_head in {"EF-", "EF2-"}:
        head_pack = 1
    elif upper_head.startswith("P") and upper_head[1:].isdigit():
        head_pack = int(upper_head[1:])
    else:
        return Residue(site=site, pack=0, problem=f"前缀 {head!r} 认不出")

    # 变体尾：'-XL' / '-LT-G' 这种以连字符开头、到下一个空格为止的片段
    if tail.startswith("-"):
        token, _, rest = tail.partition(" ")
        if any(ch.isdigit() for ch in token):
            return Residue(site=site, pack=0, problem=f"变体尾 {token!r} 含数字，认不出")
        tail = rest.strip()

    tail_pack = parse_quantity_marker(tail)
    if tail_pack is None:
        return Residue(site=site, pack=0, problem=f"后缀 {tail!r} 认不出")

    if head_pack > 1 and tail_pack > 1 and head_pack != tail_pack:
        return Residue(
            site=site, pack=0, problem=f"前缀打包数 {head_pack} 与后缀打包数 {tail_pack} 冲突"
        )
    return Residue(site=site, pack=max(head_pack, tail_pack))


def match_target(sku: str, targets: Mapping[str, float]) -> tuple[str, int, str] | None:
    """用最长匹配把数据表 SKU 对到价格表键上，返回 ``(key, pack, site)``。

    匹配长度优先（KMP），残留文本必须能解释成「站点后缀 + 打包数」才算命中，
    所以 ``GJHW00310-RED`` 不会被 ``GJHW0031`` 抢走。
    """

    match = longest_match(sku, list(targets))
    if match is None:
        return None
    residue = split_residue(match.prefix, match.suffix)
    if not residue.ok:
        return None
    return match.sku, residue.pack, residue.site


@dataclass(frozen=True)
class PriceTargets:
    """Minimum selling prices split by site, as the price sheet is laid out."""

    by_site: dict[str, dict[str, float]]
    rejected: list[dict[str, str]]
    conflicts: list[dict[str, object]]

    def for_site(self, site: str) -> dict[str, float]:
        return dict(self.by_site.get((site or "").strip().upper(), {}))

    def search_terms(self, site: str) -> list[str]:
        """Wildcard terms for the datasheet search box (``*CORE``).

        The site accepts ``*`` so one term finds the bare SKU plus its
        ``US``/``x2``/``x4`` variants in a single query.
        """

        return [f"*{key}" for key in sorted(self.for_site(site))]

    def search_string(self, site: str) -> str:
        """Space-joined terms, matching the ``查找输入`` cell of the flow."""

        return " ".join(self.search_terms(site))


def load_targets(
    entries: Iterable[Sequence[object]],
    *,
    sites: Sequence[str] = DEFAULT_SITES,
) -> PriceTargets:
    """Build per-site targets from ``(SKU, price)`` pairs.

    The first two characters of a price-sheet SKU are the site code; the rest is
    the product code with ``EF-``/``EF2-`` stripped, mirroring the flow's
    ``SKU处理后``. Rows that cannot be attributed to a site, and duplicated SKUs
    with different prices, are reported instead of silently dropped.
    """

    allowed = {site.upper() for site in sites}
    by_site: dict[str, dict[str, float]] = {site: {} for site in allowed}
    rejected: list[dict[str, str]] = []
    conflicts: list[dict[str, object]] = []

    for entry in entries:
        raw_sku, raw_price = entry[0], entry[1]
        sku = str(raw_sku or "").strip()
        if len(sku) <= 2:
            rejected.append({"sku": sku, "reason": "SKU 不足 3 位，无法拆分站点与货号"})
            continue
        site = sku[:2].upper()
        if site not in allowed:
            rejected.append({"sku": sku, "reason": f"站点 {site} 不在 {sorted(allowed)} 中"})
            continue
        if raw_price in (None, ""):
            rejected.append({"sku": sku, "reason": "价格更新为空"})
            continue
        core = sku[2:]
        for prefix in SPECIAL_PREFIXES:
            if core.upper().startswith(prefix):
                core = core[len(prefix) :]
                break
        if not core:
            rejected.append({"sku": sku, "reason": "去掉前缀后没有货号"})
            continue

        price = float(str(raw_price).strip())
        existing = by_site[site].get(core)
        if existing is not None and existing != price:
            conflicts.append({"site": site, "sku": core, "kept": existing, "ignored": price})
            continue
        by_site[site][core] = price

    return PriceTargets(by_site=by_site, rejected=rejected, conflicts=conflicts)


def validate_write_scope(changes: Iterable[Change], *, uploaded_columns: Iterable[str] = ()) -> None:
    """Refuse a write that reaches outside the editable columns.

    Uploading a datasheet replaces the whole row, so a change landing anywhere
    but ``E`` (Qty) or ``F`` (Price) would overwrite live listing data.
    """

    bad = sorted({change.field for change in changes if change.field not in EDITABLE_COLUMNS})
    if bad:
        raise ValueError(f"改价/改库存只允许动 {EDITABLE_COLUMNS}，收到越界字段 {bad}")

    allowed = set(EDITABLE_COLUMNS.values())
    extra = sorted({str(col).strip().upper() for col in uploaded_columns} - allowed)
    if extra:
        raise ValueError(f"上传文件变化列超出白名单 {sorted(allowed)}：{extra}")


@dataclass(frozen=True)
class GroupLadder:
    """同一数据表内的价格阶梯，用来反推「这一行相当于几件」。"""

    group: str
    base_row: int
    base_price: float
    ratios: dict[int, float]
    factors: dict[int, int]
    uncertain: dict[int, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "base_row": self.base_row,
            "base_price": self.base_price,
            "ratios": {str(k): round(v, 3) for k, v in self.ratios.items()},
            "factors": {str(k): v for k, v in self.factors.items()},
            "uncertain": {str(k): v for k, v in self.uncertain.items()},
        }


def infer_pack_factors(
    rows: Sequence[DatasheetRow], *, tolerance: float = 0.15
) -> dict[str, GroupLadder]:
    """按同组内价格的倍数关系反推每行相当于「几件」。

    不再看 SKU 里的 `` x2`` / ``P10``：同一数据表的价格天然成倍数关系，
    取组内最低价作基数，其余行按 ``价格 / 基数`` 就近取整，偏离超过
    ``tolerance`` 的行标为不确定（宁可不改，也不按猜的倍数抬价）。
    """

    ladders: dict[str, GroupLadder] = {}
    buckets: dict[str, list[DatasheetRow]] = {}
    for group, row in group_rows(rows):
        buckets.setdefault(group, []).append(row)

    for group, members in buckets.items():
        priced = [row for row in members if row.price > 0]
        if not priced:
            ladders[group] = GroupLadder(group, 0, 0.0, {}, {}, {})
            continue
        base = min(priced, key=lambda row: row.price)
        ratios: dict[int, float] = {}
        factors: dict[int, int] = {}
        uncertain: dict[int, str] = {}
        for row in priced:
            ratio = row.price / base.price
            nearest = max(1, round(ratio))
            error = abs(ratio - nearest) / nearest
            ratios[row.row] = ratio
            if error > tolerance:
                uncertain[row.row] = (
                    f"价格 {row.price:g} 是基价 {base.price:g} 的 {ratio:.2f} 倍，"
                    f"偏离整数 {nearest} 已 {error:.0%}"
                )
            else:
                factors[row.row] = nearest
        ladders[group] = GroupLadder(
            group=group,
            base_row=base.row,
            base_price=base.price,
            ratios=ratios,
            factors=factors,
            uncertain=uncertain,
        )
    return ladders


def plan_price_changes(
    rows: Sequence[DatasheetRow],
    targets: Mapping[str, float],
    *,
    pack_policy: PackPolicy = "multiply",
    pack_source: PackSource = "ratio",
    tolerance: float = 0.15,
) -> PricePlan:
    """Plan price writes so every row reaches its minimum selling price.

    ``pack_source`` 决定「这一行相当于几件」从哪来：

    * ``ratio`` - 同组价格阶梯反推（默认，2026-11-02 确认的口径）
    * ``sku``   - 从最长匹配的残留（`` x2`` / ``P10``）读

    ``pack_policy`` 决定这个件数怎么用：``multiply`` 目标 = 最低售价 × 件数，
    ``same`` 一律按单件，``skip`` 打包行不动。
    """

    postage = resolve_postage(rows)
    ladders = infer_pack_factors(rows, tolerance=tolerance) if pack_source == "ratio" else {}
    groups = {row.row: group for group, row in group_rows(rows)}

    changes: list[Change] = []
    matched = 0
    skipped: list[str] = []
    notes: list[str] = []
    hit: set[str] = set()

    for row in rows:
        match = match_target(row.sku, targets)
        if match is None:
            continue
        key, sku_pack, _site = match
        hit.add(key)
        group = groups.get(row.row, "")

        if pack_source == "ratio":
            ladder = ladders.get(group)
            if ladder is None or row.row in ladder.uncertain:
                reason = (
                    ladder.uncertain.get(row.row)
                    if ladder is not None
                    else "没有可用的价格阶梯"
                )
                notes.append(f"第 {row.row} 行 {row.sku}：{reason}，未改价")
                continue
            pack = ladder.factors.get(row.row, 1)
            if len(ladder.factors) == 1:
                # 孤身行没有阶梯可比：最低售价 < 现价 说明它是套装，
                # 件数 = 现价 ÷ 最低售价；最低售价 ≥ 现价 则是单件。
                base_target = float(targets[key])
                if row.price > base_target:
                    ratio = row.price / base_target
                    inferred = max(1, round(ratio))
                    error = abs(ratio - inferred) / inferred
                    if error > tolerance:
                        notes.append(
                            f"第 {row.row} 行 {row.sku} 独自成组，现价 {row.price:g} 是"
                            f"最低售价 {base_target:g} 的 {ratio:.2f} 倍，离整数 {inferred} 已"
                            f" {error:.0%}，未改价"
                        )
                        continue
                    pack = inferred
                    notes.append(
                        f"第 {row.row} 行 {row.sku} 独自成组，现价高于最低售价，"
                        f"按 {pack} 件装处理"
                    )
                else:
                    pack = 1
                    notes.append(
                        f"第 {row.row} 行 {row.sku} 独自成组且现价不高于最低售价，按单件处理"
                    )
        else:
            pack = sku_pack

        if pack > 1 and pack_policy == "skip":
            skipped.append(f"{row.sku} (x{pack})")
            continue
        if row.row in postage.ambiguous_rows:
            continue

        matched += 1
        shipping = postage.by_row[row.row]
        multiplier = pack if pack_policy == "multiply" and pack > 1 else 1
        target = float(targets[key]) * multiplier
        total = round(row.price + shipping, 4)
        if total >= target:
            continue
        new_price = round(target - shipping, 4)
        if new_price <= row.price:
            continue
        changes.append(
            Change(
                row=row.row,
                sku=row.sku,
                field="price",
                old=row.price,
                new=new_price,
                reason=f"合计 {total:g} < 最低售价 {target:g}",
                group_postage=shipping,
            )
        )

    ambiguous_groups = sorted(
        {rowid for rowid, row in group_rows(rows) if row.row in postage.ambiguous_rows}
    )
    return PricePlan(
        changes=changes,
        unmatched_targets=sorted(set(targets) - hit),
        skipped_packs=skipped,
        ambiguous_groups=ambiguous_groups,
        matched_rows=matched,
        notes=notes,
        ladders=ladders,
    )


@dataclass(frozen=True)
class StockPlan:
    changes: list[Change]
    no_stock: list[str]  # 认出的实际 SKU 但没有库存数字
    unresolved: list[dict[str, str]]  # 连实际 SKU 都没认出来（最大匹配不够/残留不认识）

    def as_dict(self) -> dict[str, object]:
        return {
            "changes": [change.as_dict() for change in self.changes],
            "changed_rows": len(self.changes),
            "no_stock": self.no_stock,
            "unresolved": self.unresolved,
        }


def plan_stock_changes(
    rows: Sequence[DatasheetRow],
    stock_by_sku: Mapping[str, float],
    *,
    catalog: Sequence[str] | None = None,
) -> StockPlan:
    """Plan absolute stock writes against the *actual* SKU.

    ``stock_by_sku`` 里填的就是这个产品本身的件数，**不做打包换算**：
    无论该刊登是单件还是 4 件装，刊登数量直接写这个数。

    给了 ``catalog`` 时用 KMP 最长匹配找回实际 SKU；匹配到就直接用，**不看匹配残留**
    （`` x4``、``P10``、``-LT-G`` 一律忽略）——库存只认这个产品本身。
    """

    changes: list[Change] = []
    no_stock: set[str] = set()
    unresolved: list[dict[str, str]] = []

    for row in rows:
        if catalog:
            match = longest_match(row.sku, catalog)
            if match is None:
                unresolved.append({"sku": row.sku, "reason": "在 SKU 目录里找不到任何匹配"})
                continue
            base = match.sku
        else:
            base, _pack = parse_pack(row.sku)

        if base not in stock_by_sku:
            no_stock.add(base)
            continue
        stock = float(stock_by_sku[base])
        if stock == row.qty:
            continue
        changes.append(
            Change(
                row=row.row,
                sku=row.sku,
                field="qty",
                old=row.qty,
                new=stock,
                reason=f"实际 SKU {base} 库存 {stock:g}",
            )
        )

    return StockPlan(
        changes=changes,
        no_stock=sorted(no_stock),
        unresolved=unresolved,
    )


def rows_from_matrix(
    matrix: Iterable[Sequence[object]], *, first_row: int = 3
) -> list[DatasheetRow]:
    """Build rows from ``(rowid, parent_sku, sku, qty, price, postage)`` tuples."""

    rows: list[DatasheetRow] = []
    for offset, values in enumerate(matrix):
        rowid, parent_sku, sku, qty, price, postage = values
        if sku in (None, ""):
            continue
        rows.append(
            DatasheetRow(
                row=first_row + offset,
                rowid=str(rowid or "").strip(),
                parent_sku=str(parent_sku or "").strip(),
                sku=str(sku).strip(),
                qty=_number(qty),
                price=_number(price),
                postage=None if postage in (None, "") else _number(postage),
            )
        )
    return rows


def _number(value: object) -> float:
    if value is None or value == "":
        return 0.0
    return float(str(value).strip())
