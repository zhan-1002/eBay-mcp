# -*- coding: utf-8 -*-
"""查真实调用时传给 write_sections 的行到底是什么。"""
import json
import os
import sys
import tempfile

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

import run_keyword_research as rk  # noqa: E402
from analyze import build_report, detect_brands, specifics_freq  # noqa: E402

SRC = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_113146.json"
d = json.load(open(SRC, encoding="utf-8"))
items = d["items"]
kw = d["keyword"]

rows = []
for it in items:
    for s in it.get("item_specifics") or []:
        rows.append({"name": s["name"], "value": s["value"], "position": it["position"]})
spec_stats = specifics_freq(rows)

report = build_report(kw, d["site"], items, 30, 10, extra_refinements=[])
market = rk.build_market_report(report, items, kw, spec_stats, target=30)

print("market 键:", list(market.keys()))
pr = market.get("price_bands") or []
print("\nprice_bands 条数:", len(pr))
if pr:
    print("  第 1 行键:", list(pr[0].keys()))
    print("  第 1 行:", pr[0])
bp = market.get("brand") or {}
print("\nbrand_pack 键:", list(bp.keys()))
for k in ("brand_rows", "band_rows", "spec_rows"):
    v = bp.get(k) or []
    print("  %s: %d 条" % (k, len(v)))
    if v:
        print("     第1行:", v[0])

print("\nbrand summary:", bp.get("summary"))
