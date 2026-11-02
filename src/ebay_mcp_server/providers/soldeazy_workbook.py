"""在导出表上写改价/改库存，并在上传前自检「只有允许的列变了」。

上传数据表是整行覆盖：文件里任何一列意外变化都会把线上字段冲掉。所以流程固定为
「读原表 → 只改 E/F → 存新文件 → 逐格比对 → 越界就拒绝上传」。

比对与改写的核心都是二维单元格矩阵，不依赖 Excel 库即可测试；读写 xlsx 的两层
薄封装才需要 ``openpyxl``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

#: 数据表导出里的固定列位（与影刀流程一致，列不会变）
FIELD_COLUMNS: dict[str, int] = {"qty": 5, "price": 6}

#: 允许改动的列：E(数量) / F(价格)
EDITABLE_COLUMNS: frozenset[str] = frozenset({"E", "F"})


@dataclass(frozen=True)
class CellChange:
    row: int
    column: int
    letter: str
    old: Any
    new: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "column": self.letter,
            "old": self.old,
            "new": self.new,
        }


class UnsafeUpload(RuntimeError):
    """上传前自检失败：文件里有白名单之外的改动。"""


def column_letter(index: int) -> str:
    """1 -> 'A'、5 -> 'E'、27 -> 'AA'（不依赖 openpyxl，便于纯逻辑测试）。"""

    if index < 1:
        raise ValueError(f"列号必须从 1 开始，收到 {index}")
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def field_column(field: str) -> int:
    try:
        return FIELD_COLUMNS[field]
    except KeyError as exc:
        raise ValueError(f"未知字段 {field!r}，只支持 {sorted(FIELD_COLUMNS)}") from exc


def apply_changes(
    matrix: Sequence[Sequence[Any]],
    changes: Iterable[tuple[str, int, Any]],
    *,
    first_row: int = 1,
) -> list[list[Any]]:
    """按 ``(字段, Excel 行号, 新值)`` 改写矩阵，返回新矩阵（不改原对象）。

    ``first_row`` 是矩阵第 0 行对应的 Excel 行号，默认 1。
    """

    result = [list(row) for row in matrix]
    for field, row_number, value in changes:
        index = row_number - first_row
        if index < 0 or index >= len(result):
            raise ValueError(f"行号 {row_number} 超出表格范围")
        column = field_column(field) - 1
        row = result[index]
        while len(row) <= column:
            row.append(None)
        row[column] = value
    return result


def diff_matrices(
    before: Sequence[Sequence[Any]],
    after: Sequence[Sequence[Any]],
    *,
    first_row: int = 1,
) -> list[CellChange]:
    """逐格比对两份矩阵，返回全部差异（含行号与列字母）。"""

    changes: list[CellChange] = []
    height = max(len(before), len(after))
    for index in range(height):
        left = before[index] if index < len(before) else []
        right = after[index] if index < len(after) else []
        width = max(len(left), len(right))
        for column in range(width):
            old = left[column] if column < len(left) else None
            new = right[column] if column < len(right) else None
            if old != new:
                changes.append(
                    CellChange(
                        row=first_row + index,
                        column=column + 1,
                        letter=column_letter(column + 1),
                        old=old,
                        new=new,
                    )
                )
    return changes


def changed_columns(changes: Iterable[CellChange]) -> set[str]:
    return {change.letter for change in changes}


def assert_only_editable(
    changes: Iterable[CellChange], *, allowed: Iterable[str] = EDITABLE_COLUMNS
) -> None:
    """上传前自检：出现白名单之外的列就抛错，整批拒绝上传。"""

    allowed_set = {str(column).upper() for column in allowed}
    offenders = sorted(changed_columns(changes) - allowed_set)
    if offenders:
        raise UnsafeUpload(
            f"文件里有白名单之外的列被改动：{offenders}（只允许 {sorted(allowed_set)}），"
            "已拒绝上传"
        )


def read_matrix(path: str | Path, sheet: str | None = None) -> tuple[str, list[list[Any]]]:
    """读取工作表为矩阵，返回 ``(工作表名, 矩阵)``。"""

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError("读写数据表需要 openpyxl：uv sync --extra soldeazy") from exc

    workbook = load_workbook(str(path))
    name = sheet or ("Worksheet" if "Worksheet" in workbook.sheetnames else workbook.sheetnames[0])
    worksheet = workbook[name]
    matrix = [list(row) for row in worksheet.iter_rows(values_only=True)]
    workbook.close()
    return name, matrix


def write_matrix(path: str | Path, matrix: Sequence[Sequence[Any]], sheet: str) -> Path:
    """把矩阵写进一份新的 xlsx（保留列宽等由调用方决定，这里只保证数据一致）。"""

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError("读写数据表需要 openpyxl：uv sync --extra soldeazy") from exc

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = load_workbook(str(target))
    worksheet = workbook[sheet if sheet in workbook.sheetnames else workbook.sheetnames[0]]
    for row_index, row in enumerate(matrix, start=1):
        for column_index, value in enumerate(row, start=1):
            worksheet.cell(row=row_index, column=column_index).value = value
    workbook.save(str(target))
    workbook.close()
    return target


def build_upload_file(
    src: str | Path,
    dst: str | Path,
    changes: Iterable[tuple[str, int, Any]],
    *,
    sheet: str | None = None,
) -> dict[str, Any]:
    """复制原表 → 只改指定单元格 → 存新文件 → 逐格复核。

    复核不通过会抛 :class:`UnsafeUpload`，并且**不返回可上传的文件**。
    """

    name, before = read_matrix(src, sheet)
    after = apply_changes(before, changes)
    differences = diff_matrices(before, after)
    assert_only_editable(differences)

    target = Path(dst)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(Path(src).read_bytes())
    write_matrix(target, after, name)

    _, written = read_matrix(target, name)
    problems = [
        change
        for change in diff_matrices(before, written)
        if change.letter not in EDITABLE_COLUMNS
    ]
    if problems:
        raise UnsafeUpload(
            "写回后复核失败，出现白名单之外的差异："
            + ", ".join(f"{p.letter}{p.row}" for p in problems[:10])
        )

    return {
        "path": str(target),
        "sheet": name,
        "changes": [change.as_dict() for change in differences],
        "changed_columns": sorted(changed_columns(differences)),
    }
