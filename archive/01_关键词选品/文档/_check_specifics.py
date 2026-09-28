# -*- coding: utf-8 -*-
"""检查已采集 JSON 的 item specifics 完整性（不采集、不联网）。"""
import json
import os
import sys
from collections import Counter

JSON_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_105432.json"

d = json.load(open(JSON_PATH, encoding="utf-8"))
items = d["items"]

print("=" * 78)
print("1) 哪些条目的 item_specifics 是空的")
print("=" * 78)
with_spec = [it for it in items if it.get("item_specifics")]
without = [it for it in items if not it.get("item_specifics")]
print("有 specifics: %d 条 %s" % (len(with_spec), [it["position"] for it in with_spec]))
print("无 specifics: %d 条 %s" % (len(without), [it["position"] for it in without][:30]))

print()
print("=" * 78)
print("2) 前 10 条各自拿到了哪些属性（对照截图应有的 Brand/Type/Model/Color/Category...）")
print("=" * 78)
KEY = ["brand", "type", "model", "colour", "color", "condition", "category",
       "connectivity", "features", "capacity", "power source"]
for it in items[:10]:
    names = [s["name"] for s in it["item_specifics"]]
    low = [n.lower() for n in names]
    missing = [k for k in KEY if k not in low]
    print("\n#%-3d %s" % (it["position"], (it["title"] or "")[:56]))
    print("     属性数=%d  缺失关键项=%s" % (len(names), missing or "无"))
    print("     类目: leaf=%s  name=%s  categories=%s"
          % (it.get("leaf_category_ids"), it.get("leaf_category_name") or "(空)", it.get("categories")))

print()
print("=" * 78)
print("3) 属性名总表（前 10 条合并后）")
print("=" * 78)
c = Counter()
for it in items[:10]:
    for s in it["item_specifics"]:
        c[s["name"]] += 1
print("共 %d 种属性名：" % len(c))
for name, n in c.most_common():
    print("   %-28s %d/10" % (name, n))

print()
print("=" * 78)
print("4) Category 面包屑 / 类目名 是否拿到")
print("=" * 78)
print("leaf_category_name 非空的: %d / 10" % sum(1 for it in items[:10] if it.get("leaf_category_name")))
print("categories 非空的       : %d / 10" % sum(1 for it in items[:10] if it.get("categories")))
for it in items[:10]:
    print("   #%-3d leaf=%s name=%r categories=%s"
          % (it["position"], it.get("leaf_category_ids"), it.get("leaf_category_name"), it.get("categories")))

print()
print("=" * 78)
print("5) 120 条里商品标题类型分布（看有没有非耳机品类，需要别的类目样本）")
print("=" * 78)
kw = Counter()
for it in items:
    t = (it["title"] or "").lower()
    for k in ("blender", "earbud", "earphone", "headphone", "headset", "buds", "pods",
              "speaker", "charger", "watch", "camera", "mouse", "keyboard"):
        if k in t:
            kw[k] += 1
print("  ", dict(kw.most_common()))
print("   类目ID分布:", Counter(str(it["leaf_category_ids"][0]) for it in items if it.get("leaf_category_ids")).most_common())
