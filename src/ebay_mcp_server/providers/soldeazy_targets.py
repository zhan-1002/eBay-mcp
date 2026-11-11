"""批量目标值的文件入口。

为什么要这个：一次改价/改库存往往涉及成百上千个 SKU。走 ``targets={...}`` 内联字典时，
**每一条都要模型自己生成**，而且会整段留在上下文里，之后每一轮都重发一遍。
2000 个 SKU 的内联字典约 1.6 万 token，10 轮对话就变成十几万。

改成给一个文件路径，调用方只发 20 来个 token，几千条都在磁盘上，
表格由运营维护（库存表已经是这个约定），服务端读完直接进计划。

支持两种载体：

* **Excel**（``.xlsx``）：表头至少含 ``SKU`` 和一列数值（``库存``/``价格``/``price`` 等），
  一行一个目标；与 ``库存更新.xlsx`` 的约定兼容。
* **文本/CSV**（其他后缀）：一行一条，``SKU=数值``、``SKU,数值`` 或制表符分隔；
  ``#`` 开头是注释；首个字段不是数字的行按表头跳过。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

#: 表头里认得的数值列名（大小写不敏感）。库存表和价格表共用一套解析。
VALUE_HEADERS: tuple[str, ...] = (
    "库存",
    "数量",
    "qty",
    "quantity",
    "stock",
    "价格",
    "新价格",
    "price",
    "值",
    "目标值",
)

#: 一行里可能出现的分隔符。SKU 自身可能带空格（如 ``ZMFL0012 x2``），
#: 所以取「最后一个」分隔符切分，不按空格切。
SEPARATORS: tuple[str, ...] = ("=", ",", "\t", "，", "；", ";")


@dataclass(frozen=True)
class TargetBatch:
    targets: dict[str, float] = field(default_factory=dict)
    source: str = ""
    skipped: list[dict[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "targets_count": len(self.targets),
            "source": self.source,
            "skipped": self.skipped,
            "issues": self.issues,
            "ok": self.ok,
        }


def _clean(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text


def _split(line: str) -> tuple[str, str] | None:
    """按最靠后的分隔符把一行切成 (SKU, 数值)。"""

    best = -1
    for sep in SEPARATORS:
        index = line.rfind(sep)
        if index > best:
            best = index
    if best <= 0:
        return None
    sep_len = 1
    return line[:best].strip(), line[best + sep_len :].strip()


def _check(kind: str, sku: str, raw: str, row: int | str) -> tuple[float | None, str]:
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None, f"第 {row} 行 {sku}：{raw!r} 不是数字"
    if kind == "qty":
        if value < 0:
            return None, f"第 {row} 行 {sku}：数量 {value:g} 为负数"
        if value != int(value):
            return None, f"第 {row} 行 {sku}：数量 {value:g} 不是整数"
    elif value <= 0:
        return None, f"第 {row} 行 {sku}：价格 {value:g} 必须大于 0"
    return value, ""


def parse_targets_text(text: str, *, kind: str = "price", source: str = "") -> TargetBatch:
    """解析 ``SKU=数值`` 形式的文本。坏行进 ``issues``，不静默丢弃。"""

    targets: dict[str, float] = {}
    skipped: list[dict[str, Any]] = []
    issues: list[str] = []
    header_seen = False

    for row, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        pair = _split(line)
        if pair is None:
            issues.append(f"第 {row} 行：找不到分隔符（支持 = , 制表符），内容 {line[:40]!r}")
            continue

        sku, raw_value = _clean(pair[0]), _clean(pair[1])

        # 首个字段不是数字的按表头跳过，这样导出的 CSV 可以直接喂进来
        if not header_seen and not raw_value:
            header_seen = True
            continue
        if not header_seen:
            header_seen = True
            try:
                float(raw_value.replace(",", ""))
            except ValueError:
                if sku.upper() == "SKU":
                    continue
        if not sku:
            issues.append(f"第 {row} 行：有数值但没有 SKU")
            continue
        if raw_value in {"", "-", "—"}:
            skipped.append({"row": row, "sku": sku, "reason": "数值留空，跳过"})
            continue

        value, problem = _check(kind, sku, raw_value, row)
        if problem:
            issues.append(problem)
            continue
        if sku in targets:
            issues.append(f"第 {row} 行 {sku}：与前面重复，无法判定哪个是对的")
            continue
        targets[sku] = float(value)

    return TargetBatch(targets=targets, source=source, skipped=skipped, issues=issues)


def _value_column(header: Sequence[str]) -> int | None:
    for index, name in enumerate(header):
        if _clean(name).lower() in VALUE_HEADERS:
            return index
    return 1 if len(header) > 1 else None


def parse_target_rows(
    matrix: Iterable[Sequence[object]], *, kind: str = "price", source: str = ""
) -> TargetBatch:
    """从 Excel 的二维单元格里读目标值；表头需含 ``SKU``。"""

    rows = [list(row) for row in matrix]
    if not rows:
        return TargetBatch(source=source, issues=["空表：连表头都没有"])

    header = [_clean(cell) for cell in rows[0]]
    lowered = [name.lower() for name in header]
    if "sku" not in lowered:
        return TargetBatch(
            source=source,
            issues=[f"表头必须包含 SKU 列，实际为 {header}"],
        )
    sku_col = lowered.index("sku")
    value_col = _value_column(header)
    if value_col is None:
        return TargetBatch(source=source, issues=[f"找不到数值列，表头为 {header}"])

    targets: dict[str, float] = {}
    skipped: list[dict[str, Any]] = []
    issues: list[str] = []

    for offset, row in enumerate(rows[1:], start=2):
        sku = _clean(row[sku_col] if sku_col < len(row) else "")
        raw_value = _clean(row[value_col] if value_col < len(row) else "")
        if not sku and not raw_value:
            continue
        if not sku:
            issues.append(f"第 {offset} 行：有数值但没有 SKU")
            continue
        if raw_value in {"", "-", "—"}:
            skipped.append({"row": offset, "sku": sku, "reason": "数值留空，跳过"})
            continue
        value, problem = _check(kind, sku, raw_value, offset)
        if problem:
            issues.append(problem)
            continue
        if sku in targets:
            issues.append(f"第 {offset} 行 {sku}：与前面重复，无法判定哪个是对的")
            continue
        targets[sku] = float(value)

    return TargetBatch(targets=targets, source=source, skipped=skipped, issues=issues)


def read_targets_file(
    path: str | Path, *, kind: str = "price", sheet_name: str | None = None
) -> TargetBatch:
    """按后缀分派：``.xlsx`` 走 Excel 解析，其余按文本解析。"""

    target = Path(path).expanduser()
    if not target.is_file():
        return TargetBatch(source=str(target), issues=[f"找不到目标文件：{target}"])

    if target.suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError:  # pragma: no cover - 取决于环境
            return TargetBatch(
                source=str(target),
                issues=["读取 Excel 需要 openpyxl，请安装：uv sync --extra soldeazy"],
            )
        workbook = load_workbook(str(target), data_only=True, read_only=True)
        name = sheet_name or (
            "库存" if "库存" in workbook.sheetnames else workbook.sheetnames[0]
        )
        matrix = [tuple(row) for row in workbook[name].iter_rows(values_only=True)]
        workbook.close()
        return parse_target_rows(matrix, kind=kind, source=str(target))

    try:
        text = target.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return TargetBatch(source=str(target), issues=[f"读不了目标文件：{exc}"])
    return parse_targets_text(text, kind=kind, source=str(target))
