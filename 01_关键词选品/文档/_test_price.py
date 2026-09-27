# -*- coding: utf-8 -*-
"""离线自测 collect_ziniao.parse_price_display（不联网）。"""
import os
import sys

sys.path.insert(0, r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本")
from collect_ziniao import parse_price_display  # noqa: E402

CASES = [
    ("\u00a321.97 to \u00a322.97(\u00a321.97/Unit)", (21.97, 22.97, "\u00a3")),
    ("\u00a313.99(\u00a313.99/Unit)", (13.99, 13.99, "\u00a3")),
    ("US $10.99 to $19.99", (10.99, 19.99, "US $")),
    ("$20.00 or Best Offer", (20.00, 20.00, "$")),
    ("EUR 12,99", (12.99, 12.99, "EUR")),
    ("\u20ac1.234,56", (1234.56, 1234.56, "\u20ac")),
    ("", (None, None, "")),
    ("Free", (None, None, "")),
]

fail = 0
for text, expect in CASES:
    lo, hi, cur, disp = parse_price_display(text)
    got = (lo, hi, cur)
    ok = got == expect
    if not ok:
        fail += 1
    print("%s  %-34r -> %-28s expect %s" % ("OK  " if ok else "FAIL", text, got, expect))
print("\n失败 %d / %d" % (fail, len(CASES)))
sys.exit(1 if fail else 0)
