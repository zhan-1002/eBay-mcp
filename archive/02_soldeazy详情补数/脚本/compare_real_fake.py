# -*- coding: utf-8 -*-
"""精准对比：真 item 与假 item 的 res_dsheet 关键字段是否有值。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))


def load(item_id):
    p = os.path.join(OUT, "flag_probe_%s.json" % item_id)
    if not os.path.isfile(p):
        return None
    rows = json.loads(open(p, encoding="utf-8").read())
    return rows[0] if rows else None


CASES = [("真 177632191323", "177632191323"),
         ("真 406803296693", "406803296693"),
         ("真 276643769322", "276643769322"),
         ("假 123456789012", "123456789012")]

KEY = ["dsheet_titleexternal", "dsheet_titleinternal", "dsheet_subtitleexternal",
       "dsheet_ebcategory", "dsheet_ebcategory2", "dsheet_price", "dsheet_currency",
       "dsheet_qty", "dsheet_condition_id", "dsheet_format", "dsheet_sitecode",
       "dsheet_itemlocation", "dsheet_pictotal", "dsheet_poster", "dsheet_gallery",
       "dsheet_is_variation", "dsheet_full_item_model", "dsheet_product_code"]

print("=" * 100)
print("① 关键字段值对比")
print("=" * 100)
hdr = "%-26s" % "字段"
for label, _ in CASES:
    hdr += "%-28s" % label
print(hdr)
for k in KEY:
    line = "%-26s" % k
    for label, iid in CASES:
        r = load(iid)
        v = ((r or {}).get("res_dsheet") or {}).get(k)
        s = str(v)
        line += "%-28s" % (s[:26] if s != "None" else "(None)")
    print(line)

print()
print("=" * 100)
print("② item specifics（有值的槽位）")
print("=" * 100)
for label, iid in CASES:
    r = load(iid)
    ds = (r or {}).get("res_dsheet") or {}
    specs = []
    for i in range(1, 46):
        v = ds.get("dsheet_item_specific_%d" % i)
        if v:
            specs.append("s%d=%s" % (i, str(v)[:60]))
    print("\n  %s : %d 项" % (label, len(specs)))
    for s in specs[:25]:
        print("     %s" % s)

print()
print("=" * 100)
print("③ 有值字段计数（判断内容抓没抓到）")
print("=" * 100)
for label, iid in CASES:
    r = load(iid)
    ds = (r or {}).get("res_dsheet") or {}
    nonempty = [k for k, v in ds.items() if v not in (None, "", [], {})]
    print("\n  %-18s 总字段 %d，有值 %d" % (label, len(ds), len(nonempty)))
    interesting = [k for k in nonempty if any(x in k for x in
                   ("title", "desc", "pic", "poster", "gallery", "specific",
                    "model", "price", "category", "condition"))]
    print("     内容类有值: %s" % interesting[:20])

print()
print("=" * 100)
print("④ 描述类字段的实际内容")
print("=" * 100)
for label, iid in CASES:
    r = load(iid)
    ds = (r or {}).get("res_dsheet") or {}
    print("\n  %s" % label)
    for k in ("dsheet_actual_desc", "dsheet_poster", "dsheet_gallery",
              "dsheet_gallerytype", "dsheet_photofirst", "dsheet_receivedesctotal",
              "dsheet_maindesctotal"):
        v = ds.get(k)
        if v not in (None, "", [], {}):
            print("     %-24s = %s" % (k, str(v)[:150]))
    if all(ds.get(k) in (None, "", [], {}) for k in
           ("dsheet_actual_desc", "dsheet_poster", "dsheet_gallery")):
        print("     （描述/图片相关字段全为空）")
