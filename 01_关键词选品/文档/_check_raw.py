# -*- coding: utf-8 -*-
"""逐条打印 JSON 里 item_specifics / categories 的原始结构（不采集）。"""
import json

JSON_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_105432.json"

d = json.load(open(JSON_PATH, encoding="utf-8"))
items = d["items"]

print("顶层键: %s" % list(d.keys()))
print("specifics_sample_positions = %s" % d.get("specifics_sample_positions"))
print("item_count=%s ad_count=%s" % (d.get("item_count"), d.get("ad_count")))
print()

print("前 12 条逐条：")
for it in items[:12]:
    sp = it.get("item_specifics")
    print("  #%-3d specifics 类型=%-6s 条数=%-3s categories=%-2s leaf=%-14s name=%r"
          % (it["position"], type(sp).__name__,
             len(sp) if isinstance(sp, list) else "N/A",
             len(it.get("categories") or []), it.get("leaf_category_ids"),
             (it.get("leaf_category_name") or "")[:40]))

print()
print("有 specifics 的位置: %s" % [it["position"] for it in items if it.get("item_specifics")])
print()
print("第 1 条 specifics 原始值（前 3 项）:")
print("  %r" % (items[0].get("item_specifics") or [])[:3])
print()
print("第 2 条完整字典:")
print("  %s" % json.dumps({k: (v if k != "item_url" else str(v)[:60]) for k, v in items[1].items()},
                        ensure_ascii=False)[:900])
