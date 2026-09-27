# -*- coding: utf-8 -*-
"""核对：detail=0 的产物是否 120/120 带齐 item id / 链接（下游按 id 取数用）。"""
import glob
import json
import os

import openpyxl

OUT = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出"
XLSX = sorted(glob.glob(os.path.join(OUT, "haihu_8075_uk_wireless_earbuds_*.xlsx")))[-1]
JSON = XLSX[:-5] + ".json"
print("核对: %s" % os.path.basename(XLSX))

wb = openpyxl.load_workbook(XLSX)
d = json.load(open(JSON, encoding="utf-8"))
its = d["items"]
n = len(its)


def cnt(pred):
    return sum(1 for it in its if pred(it))


print("\n=== 下游对接字段（按 item id 去别处取数）===")
print("1) item_id 非空           : %d / %d" % (cnt(lambda it: it.get("item_id")), n))
print("2) legacy_item_id 非空    : %d / %d" % (cnt(lambda it: it.get("legacy_item_id")), n))
print("3) item_url 非空          : %d / %d" % (cnt(lambda it: it.get("item_url")), n))
print("4) item_url 含 /itm/数字  : %d / %d"
      % (cnt(lambda it: "/itm/" in (it.get("item_url") or "")), n))
print("5) variant_id 有值        : %d / %d" % (cnt(lambda it: it.get("variant_id")), n))
print("6) search_rank 有值       : %d / %d" % (cnt(lambda it: it.get("search_rank") is not None), n))

print("\n=== 其它字段 ===")
print("7) 广告位 promoted=True   : %d / %d" % (cnt(lambda it: it.get("is_sponsored")), n))
print("   标记来源= listings     : %d" % cnt(lambda it: it.get("promoted_source") == "listings"))
print("8) 末级类目ID 非空        : %d / %d" % (cnt(lambda it: it.get("leaf_category_ids")), n))
print("9) 价格非空 / 区间        : %d / %d"
      % (cnt(lambda it: it.get("price") is not None), cnt(lambda it: it.get("price_is_range"))))
print("10) title 带 a11y 噪音    : %d" % cnt(lambda it: "opens in a new window" in (it["title"] or "").lower()))
print("11) item_specifics 条数   : %d（detail=0 应为 0）" % cnt(lambda it: it.get("item_specifics")))
print("12) 推荐 title            : %d 条" % len(d["recommended_titles"]))
print("13) 唯一 item_id 数        : %d（去重后应等于 120）" % len({it.get("item_id") for it in its}))

print("\n=== Excel 采集明细列顺序（前 12 列）===")
hdr = [c.value for c in wb["采集明细"][1]]
print(hdr[:12])
print("总列数: %d" % len(hdr))

print("\n=== 前 5 行对接三件套 ===")
for it in its[:5]:
    print("  #%-3d id=%-14s var=%-14s promoted=%-5s cat=%-8s  £%-7s %s"
          % (it["position"], it["item_id"], str(it.get("variant_id"))[:14],
             it["is_sponsored"], (it.get("leaf_category_ids") or ["-"])[0],
             it["price"], (it["title"] or "")[:34]))
