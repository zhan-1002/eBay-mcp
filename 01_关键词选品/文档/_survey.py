# -*- coding: utf-8 -*-
"""盘点：① 品牌信息来源 ② 价格段现状 ③ 现有 title/词频字段结构。"""
import glob
import json
import os
import re
from collections import Counter

OUT = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出"
# 用有 specifics 的那一版（113146），品牌信息最全
JSON = os.path.join(OUT, "haihu_8075_uk_wireless_earbuds_20260914_113146.json")
d = json.load(open(JSON, encoding="utf-8"))
its = d["items"]
print("数据源: %s（%d 条）" % (os.path.basename(JSON), len(its)))

print("\n" + "=" * 74)
print("① 品牌信息有哪些来源")
print("=" * 74)
print("A) item_specifics 里的 Brand 字段（只有前 10 条有详情）：")
brand_spec = Counter()
for it in its:
    for s in it.get("item_specifics") or []:
        if s["name"].lower() in ("brand", "compatible brand"):
            brand_spec[(s["name"], s["value"])] += 1
for k, v in brand_spec.most_common(20):
    print("   %-18s %-24s %d" % (k[0], k[1], v))

print("\nB) 标题里出现的品牌（用现有 detect_brands 的识别结果）：")
import sys
sys.path.insert(0, r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本")
from analyze import detect_brands, tokenize
titles = [it["title"] for it in its]
brands = detect_brands(titles)
print("   识别到 %d 个: %s" % (len(brands), sorted(brands)))
cnt = Counter()
for t in titles:
    for tok in set(tokenize(t)):
        if tok in brands:
            cnt[tok] += 1
print("   标题中出现次数 top 20:")
for b, c in cnt.most_common(20):
    print("      %-18s %3d 条 (%.0f%%)" % (b, c, 100.0 * c / len(titles)))

print("\nC) 各属性名的覆盖情况（前 10 条详情）:")
ac = Counter()
for it in its[:10]:
    for s in it["item_specifics"]:
        ac[s["name"]] += 1
print("  ", dict(ac.most_common(15)))

print("\n" + "=" * 74)
print("② 价格段现状（JSON 里的 price 字段）")
print("=" * 74)
pr = d["price"]
for k in ("count", "currency", "min", "p20", "p50", "p80", "max", "suggest_price"):
    print("   %-14s %s" % (k, pr.get(k)))
print("   bins:")
tot = sum(b["count"] for b in pr["bins"]) or 1
for b in pr["bins"]:
    print("      %-18s %3d 条  %.1f%%" % (b["label"], b["count"], 100.0 * b["count"] / tot))

print("\n" + "=" * 74)
print("③ 现有 titles_tokens / titles_exact 结构")
print("=" * 74)
print("titles_tokens 字段: %s" % (list(d["titles_tokens"][0].keys()) if d["titles_tokens"] else "空"))
print("   前 8: %s" % d["titles_tokens"][:8])
print("titles_exact 字段: %s" % (list(d["titles_exact"][0].keys()) if d["titles_exact"] else "空"))
dup = [t for t in d["titles_exact"] if t["count"] > 1]
print("   重复>1 的 title 数: %d" % len(dup))
for t in dup[:5]:
    print("      count=%d  %s" % (t["count"], t["title"][:70]))
