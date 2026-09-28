# -*- coding: utf-8 -*-
"""沙箱内可用范围内做完整覆盖度实测 + 多关键词/多站点。

目标（生产到位前能做的部分）：
  1) 沙箱全部可搜到的 item，逐条 getItem，量 localizedAspects 覆盖率
  2) 记下 getItem 失败/无 aspects 的样本，供生产阶段对照
  3) 覆盖多个关键词 × 多个站点，验证 header 与字段稳定性
"""
import json
import os
import time
from collections import Counter
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = open(os.path.normpath(os.path.join(HERE, "..", "token.local.txt")),
             encoding="utf-8").read().strip()
BASE = "https://api.sandbox.ebay.com"
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
os.makedirs(OUT, exist_ok=True)
CALLS = Counter()

KEYWORDS = ["earbuds", "headphones", "blender", "sneakers", "phone case", "led light"]
SITES = [("EBAY_GB", "GB", "SW1A1AA"), ("EBAY_US", "US", "10001"), ("EBAY_DE", "DE", "10115")]


def hdrs(mp, ctry, zp):
    return {"Authorization": "Bearer " + TOKEN,
            "X-EBAY-C-MARKETPLACE-ID": mp,
            "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%%3D%s%%2Czip%%3D%s" % (ctry, zp),
            "Accept": "application/json"}


def search(q, mp, ctry, zp, limit=200, offset=0):
    CALLS["search"] += 1
    return requests.get(BASE + "/buy/browse/v1/item_summary/search", headers=hdrs(mp, ctry, zp),
                        params={"q": q, "limit": limit, "offset": offset}, timeout=45)


def get_item(iid, mp):
    CALLS["getItem"] += 1
    return requests.get(BASE + "/buy/browse/v1/item/" + quote(iid, safe=""),
                        headers=hdrs(mp, "GB", "SW1A1AA"), timeout=30)


print("token 长度 %d\n" % len(TOKEN))
all_items = {}
print("=" * 78)
print("① 多关键词 × 多站点 搜索（沙箱）")
print("=" * 78)
for q in KEYWORDS:
    for mp, ctry, zp in SITES:
        try:
            r = search(q, mp, ctry, zp)
        except Exception as exc:
            print("  %-12s %-8s 异常 %s" % (q, mp, str(exc)[:50]))
            continue
        if r.status_code != 200:
            print("  %-12s %-8s HTTP %s %s" % (q, mp, r.status_code, r.text[:80]))
            continue
        its = r.json().get("itemSummaries") or []
        print("  %-12s %-8s → %d 条" % (q, mp, len(its)))
        for it in its:
            iid = it.get("itemId")
            if iid and iid not in all_items:
                it["_marketplace"] = mp
                it["_query"] = q
                all_items[iid] = it

print("\n去重后共 %d 个 item 待取详情" % len(all_items))

print()
print("=" * 78)
print("② 逐条 getItem：localizedAspects 覆盖率")
print("=" * 78)
results = []
for iid, summary in all_items.items():
    mp = summary.get("_marketplace", "EBAY_GB")
    try:
        g = get_item(iid, mp)
    except Exception as exc:
        results.append({"itemId": iid, "ok": False, "err": str(exc)[:60]})
        continue
    if g.status_code != 200:
        results.append({"itemId": iid, "ok": False, "http": g.status_code,
                        "err": g.text[:120]})
        continue
    d = g.json()
    asp = d.get("localizedAspects") or []
    results.append({
        "itemId": iid, "ok": True, "title": (d.get("title") or "")[:60],
        "marketplace": mp, "query": summary.get("_query"),
        "aspects_n": len(asp),
        "aspect_names": [a.get("name") for a in asp],
        "categoryPath": d.get("categoryPath"),
        "categoryId": d.get("categoryId"),
        "categoryPathIds": d.get("categoryPathIds"),
        "desc_len": len(d.get("description") or ""),
        "image": bool(d.get("image")),
        "images_n": len(d.get("additionalImages") or []),
        "condition": d.get("condition"),
        "brand": d.get("brand"),
    })
    time.sleep(0.15)

ok = [x for x in results if x.get("ok")]
bad = [x for x in results if not x.get("ok")]
with_asp = [x for x in ok if x["aspects_n"] > 0]
print("  getItem 成功: %d | 失败: %d" % (len(ok), len(bad)))
print("  其中有 localizedAspects: %d | 无: %d" % (len(with_asp), len(ok) - len(with_asp)))
if ok:
    print("  覆盖率 = %.0f%%" % (100.0 * len(with_asp) / len(ok)))
for x in bad:
    print("     失败 %s -> %s" % (x["itemId"][:26], str(x.get("err"))[:90]))
print()
print("  逐条明细:")
for x in ok:
    print("     %-26s mp=%-8s aspects=%-3d cat=%-8s desc=%-4d img=%d | %s"
          % (x["itemId"][:26], x["marketplace"], x["aspects_n"], x["categoryId"],
             x["desc_len"], x["images_n"], x["title"][:38]))

print()
print("=" * 78)
print("③ 字段稳定性：出现在 getItem 返回里的键（并集）")
print("=" * 78)
keys = Counter()
for x in ok:
    for k in ("categoryPath", "categoryId", "categoryPathIds", "description",
              "image", "brand", "condition"):
        if x.get(k):
            keys[k] += 1
for k, v in keys.most_common():
    print("   %-18s 有值 %d/%d" % (k, v, len(ok)))

print()
print("=" * 78)
print("④ 调用消耗（本次）")
print("=" * 78)
print("  search=%d  getItem=%d  合计=%d" % (CALLS["search"], CALLS["getItem"],
                                          CALLS["search"] + CALLS["getItem"]))

with open(os.path.join(OUT, "sandbox_coverage.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump({"results": results, "calls": dict(CALLS)}, f, ensure_ascii=False, indent=2)
print("\n已存 sandbox_coverage.json")
