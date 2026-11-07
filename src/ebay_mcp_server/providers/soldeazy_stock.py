"""库存更新表：运营手工维护的 Excel 约定 + 解析（不依赖第三方库即可校验）。

约定（运营只需填「库存」一列）：

    Sheet「库存」，第 1 行表头：SKU | 库存 | 备注
    第 2 行起：一行一个实际 SKU
      · SKU   必填，去空格后作为实际货号（与产品主目录一致）
      · 库存  必填，非负整数；打「-」或留空表示本行不参与本次更新
      · 备注  可选，随便写，程序忽略

解析只做校验、不改数据：重复 SKU、非数字、负数都会进 ``issues``，
调用方可以据此整份拒收，避免带着脏数据去改线上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

SHEET_NAME = "库存"
COLUMNS: tuple[str, ...] = ("SKU", "库存", "备注")
TEMPLATE_NAME = "库存更新.xlsx"


@dataclass(frozen=True)
class StockEntry:
    sku: str
    qty: float
    row: int

    def as_dict(self) -> dict[str, Any]:
        return {"sku": self.sku, "qty": self.qty, "row": self.row}


@dataclass(frozen=True)
class StockSheet:
    entries: dict[str, float]
    skipped: list[dict[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku_count": len(self.entries),
            "skipped": self.skipped,
            "issues": self.issues,
            "ok": self.ok,
        }


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def parse_stock_rows(matrix: Iterable[Sequence[object]]) -> StockSheet:
    """把工作表的二维单元格校验成 ``{实际 SKU: 库存}``。

    第 1 行必须是表头（至少含 ``SKU`` 与 ``库存`` 两列，顺序不限）。
    """

    rows = [list(row) for row in matrix]
    if not rows:
        return StockSheet(entries={}, issues=["空表：连表头都没有"])

    header = [_clean(cell) for cell in rows[0]]
    try:
        sku_col = header.index("SKU")
        qty_col = header.index("库存")
    except ValueError:
        return StockSheet(
            entries={},
            issues=[f"表头必须同时包含 SKU 与 库存 两列，实际为 {header}"],
        )

    entries: dict[str, float] = {}
    skipped: list[dict[str, Any]] = []
    issues: list[str] = []

    for offset, row in enumerate(rows[1:], start=2):
        sku = _clean(row[sku_col] if sku_col < len(row) else "")
        raw_qty = _clean(row[qty_col] if qty_col < len(row) else "")
        if not sku and not raw_qty:
            continue  # 空行
        if not sku:
            issues.append(f"第 {offset} 行：库存有值但 SKU 为空")
            continue
        if raw_qty in {"", "-", "—"}:
            skipped.append({"row": offset, "sku": sku, "reason": "库存留空，跳过"})
            continue
        try:
            qty = float(raw_qty.replace(",", ""))
        except ValueError:
            issues.append(f"第 {offset} 行 {sku}：库存 {raw_qty!r} 不是数字")
            continue
        if qty < 0:
            issues.append(f"第 {offset} 行 {sku}：库存 {qty:g} 为负数")
            continue
        if qty != int(qty):
            issues.append(f"第 {offset} 行 {sku}：库存 {qty:g} 不是整数")
            continue
        if sku in entries:
            issues.append(f"第 {offset} 行 {sku}：与前面重复，无法判定哪个是对的")
            continue
        entries[sku] = qty

    return StockSheet(entries=entries, skipped=skipped, issues=issues)


def read_stock_sheet(path: str | Path, sheet_name: str | None = None) -> StockSheet:
    """读取运营维护的库存表（需要 ``openpyxl``）。"""

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError(
            "读取库存表需要 openpyxl，请安装：uv sync --extra soldeazy"
        ) from exc

    workbook = load_workbook(str(path), data_only=True, read_only=True)
    name = sheet_name or (SHEET_NAME if SHEET_NAME in workbook.sheetnames else workbook.sheetnames[0])
    worksheet = workbook[name]
    matrix = [tuple(row) for row in worksheet.iter_rows(values_only=True)]
    workbook.close()
    return parse_stock_rows(matrix)


def write_stock_template(path: str | Path, skus: Sequence[str]) -> Path:
    """生成库存表模板：SKU 预先填好，运营只填「库存」列。"""

    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError(
            "生成库存模板需要 openpyxl，请安装：uv sync --extra soldeazy"
        ) from exc

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    worksheet.append(list(COLUMNS))
    for sku in skus:
        worksheet.append([str(sku).strip(), None, None])
    worksheet.freeze_panes = "A2"
    worksheet.column_dimensions["A"].width = 28
    worksheet.column_dimensions["B"].width = 12
    worksheet.column_dimensions["C"].width = 30

    target = Path(path)
    if target.is_dir():
        target = target / TEMPLATE_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(target))
    return target
