# -*- coding: utf-8 -*-
"""用已采集的真实数据离线验证 title 生成（不联网、不用紫鸟）。"""
import json
import os
import sys

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)
from analyze import (  # noqa: E402
    TITLE_MAX, collect_specifics, detect_brands, generate_titles, specifics_freq,
    tokenize,
)

JSON_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_104819.json"

d = json.load(open(JSON_PATH, encoding="utf-8"))
items = d["items"]
kw = d["keyword"]
titles = [it["title"] for it in items]

picked, spec_rows = collect_specifics(items, top_n_items=10, include_ads=True)
spec_stats = specifics_freq(spec_rows)

brands = detect_brands(titles)
print("自动识别出的品牌/型号词（%d 个）:" % len(brands))
print("  ", sorted(brands))
print()

out = generate_titles(kw, titles, spec_stats, min_count=20)
print("生成 %d 条推荐 title:" % len(out))
bad = []
for i, t in enumerate(out, 1):
    flag = ""
    if len(t) > TITLE_MAX:
        flag = "  <-- 超长"
    if "," in t:
        flag = "  <-- 有逗号"
    if len(t) < 18:
        flag = "  <-- 过短"
    low = t.lower()
    hit = [b for b in brands if b in tokenize(t)]
    if hit:
        flag += "  <-- 含品牌词 %s" % hit
    if flag:
        bad.append(t)
    print("  %2d. (%2d) %s%s" % (i, len(t), t, flag))

print("\n违规条数: %d" % len(bad))
kw_toks = set(tokenize(kw))
print("关键词成分被剔除检查:", "ok" if all(k not in tokenize(t)[1:] for t in out for k in kw_toks) else "有重复关键词")
