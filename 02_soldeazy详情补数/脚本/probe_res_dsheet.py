# -*- coding: utf-8 -*-
"""对比 res_dsheet 全字段：真 item 与假 item 的差别在哪（找可判定的信号）。"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))

FILES = {
    "真-177632191323": "flag_probe_177632191323.json",
    "真-406803296693": "flag_probe_406803296693.json",
    "真-276643769322": "flag_probe_276643769322.json",
    "假-123456789012": "flag_probe_123456789012.json",
}

data = {}
for label, fn in FILES.items():
    p = os.path.join(OUT, fn)
    if not os.path.isfile(p):
        print("缺文件: %s" % fn)
        continue
    try:
        rows = json.loads(open(p, encoding="utf-8").read())
    except Exception as exc:
        print("%s 解析失败: %s" % (fn, exc))
        continue
    data[label] = rows[0] if rows else {}

print("=== res 顶层键 ===")
for label, r in data.items():
    print("  %-18s %s" % (label, list(r.keys())))

print("\n=== res_dsheet 键（取并集）===")
allkeys = []
for r in data.values():
    for k in (r.get("res_dsheet") or {}).keys():
        if k not in allkeys:
            allkeys.append(k)
print("  共 %d 个键" % len(allkeys))
for k in allkeys:
    print("    %s" % k)

print("\n=== 逐字段对比（只列有差异或关键的）===")
SKIP = {"dsheet_exclude_shiptolocation"}
for k in allkeys:
    vals = {}
    for label, r in data.items():
        v = (r.get("res_dsheet") or {}).get(k)
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        vals[label] = v
    uniq = {str(v) for v in vals.values()}
    mark = "  <<< 有差异" if len(uniq) > 1 else ""
    if k in SKIP:
        continue
    print("\n  %s%s" % (k, mark))
    for label, v in vals.items():
        s = str(v)
        print("     %-18s %s" % (label, s[:110] + ("…" if len(s) > 110 else "")))

print("\n\n=== 关键判定信号候选 ===")
for label, r in data.items():
    ds = r.get("res_dsheet") or {}
    print("\n  %s" % label)
    for k in ("dsheet_title", "dsheet_sku", "dsheet_price", "dsheet_ebcategory",
              "dsheet_ebcategory_name", "dsheet_sitecode", "dsheet_itemlocation",
              "dsheet_quantity", "dsheet_desc", "dsheet_condition"):
        if k in ds:
            v = str(ds.get(k))
            print("     %-24s = %s" % (k, v[:80]))
