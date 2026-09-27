# -*- coding: utf-8 -*-
"""复现 write_sections 的写入问题。"""
import sys

sys.path.insert(0, r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本")

import openpyxl  # noqa: E402
from run_keyword_research import write_sections, _cell_value  # noqa: E402

wb = openpyxl.Workbook()
ws = wb.active
price_rows = [
    {"价格段": "0-5", "下限": 0, "上限": 5, "商品数": 10, "占比%": 8.3, "累计占比%": 8.3, "竞争强度": "稀疏"},
    {"价格段": "5-8", "下限": 5, "上限": 8, "商品数": 16, "占比%": 13.3, "累计占比%": 21.7, "竞争强度": "中等"},
]
print("原始 dict 的键:", list(price_rows[0].keys()))
body = [[r.get("价格段"), r.get("下限"), r.get("上限"), r.get("商品数"),
         r.get("占比%"), r.get("累计占比%"), r.get("竞争强度")] for r in price_rows]
print("我构造的 body:", body)
print("_cell_value 检查:", [_cell_value(v) for v in body[0]])

write_sections(ws, [
    ("一、价格区间与占比", ["价格段", "下限", "上限", "商品数", "占比%", "累计占比%", "竞争强度"], body),
])
print()
print("写进 Excel 的实际内容:")
for i, row in enumerate(ws.iter_rows(values_only=True), 1):
    print("  %2d %r" % (i, row))
