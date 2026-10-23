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

from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Sequence

PackPolicy = Literal["same", "skip", "multiply"]

#: Datasheet columns the operator is allowed to touch, by change field.
EDITABLE_COLUMNS: dict[str, str] = {"qty": "E", "price": "F"}

#: Sites the price sheet is split into.
DEFAULT_SITES: tuple[str, ...] = ("UK", "DE", "US")

#: Prefixes the price sheet strips before matching datasheet SKUs.
SPECIAL_PREFIXES: tuple[str, ...] = ("EF-", "EF2-")


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

    def as_dict(self) -> dict[str, object]:
        return {
            "changes": [change.as_dict() for change in self.changes],
            "changed_rows": len(self.changes),
            "matched_rows": self.matched_rows,
            "unmatched_targets": self.unmatched_targets,
            "skipped_packs": self.skipped_packs,
            "ambiguous_groups": self.ambiguous_groups,
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


def _matches(prefix: str, sku: str) -> bool:
    """Prefix match that refuses to run into another product's number.

    ``PCPB0028`` must match ``PCPB0028US`` (site suffix) but not
    ``PCPB00280``; ``EF-``/``EF2-`` variants are accepted as well.
    """

    for candidate in (prefix, f"EF-{prefix}", f"EF2-{prefix}"):
        if not sku.startswith(candidate):
            continue
        rest = sku[len(candidate) :]
        if not rest or not rest[0].isdigit():
            return True
    return False


def match_target(sku: str, targets: Mapping[str, float]) -> tuple[str, str, int] | None:
    """Return ``(target_key, base_sku, pack)`` for a datasheet SKU."""

    base, pack = parse_pack(sku)
    for key in sorted(targets, key=len, reverse=True):
        if _matches(key, base):
            return key, base, pack
    return None


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


def plan_price_changes(
    rows: Sequence[DatasheetRow],
    targets: Mapping[str, float],
    *,
    pack_policy: PackPolicy = "same",
) -> PricePlan:
    """Plan price writes so every row reaches its minimum selling price.

    ``pack_policy``:

    * ``same``     - pack rows are treated like any other row (production default)
    * ``skip``     - pack rows are left untouched
    * ``multiply`` - a pack row's target is multiplied by its pack size
    """

    postage = resolve_postage(rows)
    changes: list[Change] = []
    matched = 0
    skipped: list[str] = []
    hit: set[str] = set()

    for row in rows:
        match = match_target(row.sku, targets)
        if match is None:
            continue
        key, _base, pack = match
        hit.add(key)

        if pack > 1 and pack_policy == "skip":
            skipped.append(f"{row.sku} (x{pack})")
            continue
        if row.row in postage.ambiguous_rows:
            continue

        matched += 1
        shipping = postage.by_row[row.row]
        target = float(targets[key]) * (pack if pack_policy == "multiply" and pack > 1 else 1)
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
    )


def plan_stock_changes(
    rows: Sequence[DatasheetRow],
    stock_by_sku: Mapping[str, float],
    *,
    divide_by_pack: bool = True,
) -> tuple[list[Change], list[str]]:
    """Plan absolute stock writes against the *actual* SKU.

    ``stock_by_sku`` is keyed by the actual product code (no site suffix, no
    pack suffix). A listing row is only touched when its actual SKU has a
    stock figure; a pack listing receives ``floor(stock / pack)`` so the listed
    quantity can actually be fulfilled.

    Returns ``(changes, unmatched_skus)``.
    """

    changes: list[Change] = []
    unmatched: set[str] = set()

    for row in rows:
        base, pack = parse_pack(row.sku)
        if base not in stock_by_sku:
            unmatched.add(base)
            continue
        stock = float(stock_by_sku[base])
        wanted = float(int(stock // pack)) if divide_by_pack and pack > 1 else stock
        if wanted == row.qty:
            continue
        changes.append(
            Change(
                row=row.row,
                sku=row.sku,
                field="qty",
                old=row.qty,
                new=wanted,
                reason=(
                    f"实际 SKU {base} 库存 {stock:g}"
                    + (f" ÷ 打包数 {pack}" if pack > 1 and divide_by_pack else "")
                ),
            )
        )

    return changes, sorted(unmatched)


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
