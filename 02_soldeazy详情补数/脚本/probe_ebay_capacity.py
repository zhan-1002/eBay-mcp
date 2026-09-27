# -*- coding: utf-8 -*-
"""量化 eBay Browse API 的四项关键指标（只读）。

1) 单页条数上限 / offset 翻页
2) getItem 的 localizedAspects 覆盖率
3) 调用消耗统计
4) 多站点 header 是否生效（EBAY_GB / EBAY_US / EBAY_DE）
"""
import json
import os
import sys
import time
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.normpath(os.path.join(HERE, "..", "token.local.txt"))


def load_token():
    t = open(TOKEN_FILE, encoding="utf-8").read().strip()
    return t


BASE = "https://api.sandbox.ebay.com"
TOKEN = load_token()
CALLS = {"search": 0, "getItem": 0, "other": 0}


def hdrs(marketplace="EBAY_GB", country="GB", zipc="SW1A1AA"):
    return {
        "Authorization": "Bearer " + TOKEN,
        "X-EBAY-C-MARKETPLACE-ID": marketplace,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%%3D%s%%2Czip%%3D%s" % (country, zipc),
        "Accept": "application/json",
    }


def search(q, limit, offset=0, marketplace="EBAY_GB", country="GB", zipc="SW1A1AA"):
    CALLS["search"] += 1
    r = requests.get(BASE + "/buy/browse/v1/item_summary/search", headers=hdrs(marketplace, country, zipc),
                     params={"q": q, "limit": limit, "offset": offset}, timeout=45)
    return r


def get_item(iid, marketplace="EBAY_GB"):
    CALLS["getItem"] += 1
    return requests.get(BASE + "/buy/browse/v1/item/" + quote(iid, safe=""),
                        headers=hdrs(marketplace), timeout=30)


print("token 长度: %d | 域名: %s\n" % (len(TOKEN), BASE))

# ---------- 1) limit 上限与翻页 ----------
print("=" * 76)
print("① 单页条数上限 & offset 翻页")
print("=" * 76)
for lim in (5, 50, 200, 300):
    try:
        r = search("earbuds", lim)
    except Exception as exc:
        print("  limit=%-4d 异常 %s" % (lim, str(exc)[:80]))
        continue
    if r.status_code == 200:
        j = r.json()
        n = len(j.get("itemSummaries") or [])
        print("  limit=%-4d -> HTTP 200 | 服务端 limit=%s | 返回 %d 条 | total=%s"
              % (lim, j.get("limit"), n, j.get("total")))
    else:
        print("  limit=%-4d -> HTTP %s | %s" % (lim, r.status_code, r.text[:160].replace("\n", " ")))

print()
for off in (0, 1, 2):
    try:
        r = search("earbuds", 5, offset=off)
    except Exception as exc:
        print("  offset=%-3d 异常 %s" % (off, str(exc)[:60]))
        continue
    if r.status_code == 200:
        j = r.json()
        ids = [x.get("legacyItemId") for x in (j.get("itemSummaries") or [])]
        print("  offset=%-3d -> HTTP 200 | offset 回显=%s | itemId: %s" % (off, j.get("offset"), ids))
    else:
        print("  offset=%-3d -> HTTP %s | %s" % (off, r.status_code, r.text[:140].replace("\n", " ")))

# ---------- 2) getItem 覆盖率 ----------
print()
print("=" * 76)
print("② getItem 的 localizedAspects 覆盖率")
print("=" * 76)
r = search("earbuds", 200)
ids = []
if r.status_code == 200:
    ids = [x.get("itemId") for x in (r.json().get("itemSummaries") or [])]
print("  搜索到 %d 条，逐条 getItem：" % len(ids))
ok = miss = fail = 0
samples = []
for iid in ids:
    try:
        g = get_item(iid)
    except Exception as exc:
        fail += 1
        continue
    if g.status_code != 200:
        fail += 1
        print("     %s -> HTTP %s" % (iid, g.status_code))
        continue
    d = g.json()
    asp = d.get("localizedAspects") or []
    if asp:
        ok += 1
        if len(samples) < 3:
            samples.append((iid, d.get("title", "")[:40], len(asp),
                            [a.get("name") for a in asp[:8]]))
    else:
        miss += 1
print("  有 localizedAspects: %d | 无: %d | 请求失败: %d" % (ok, miss, fail))
for iid, title, n, names in samples:
    print("     例 %s | %s | %d 项: %s" % (iid[:24], title, n, names))

# ---------- 3) 调用消耗 ----------
print()
print("=" * 76)
print("③ 调用消耗统计（本次探测）")
print("=" * 76)
print("  search 调用: %d 次" % CALLS["search"])
print("  getItem 调用: %d 次" % CALLS["getItem"])
print()
print("  按目标场景推算（一次完整跑）:")
print("    搜索 120 条 = 1 次 search (limit=200 一页拿完)")
print("    item specifics = 120 次 getItem")
print("    → 合计约 121 次调用 / 关键词/站点")

# ---------- 4) 多站点 ----------
print()
print("=" * 76)
print("④ 多站点 header 是否生效")
print("=" * 76)
for mp, ctry, zp in (("EBAY_GB", "GB", "SW1A1AA"), ("EBAY_US", "US", "10001"), ("EBAY_DE", "DE", "10115")):
    try:
        r = search("earbuds", 3, marketplace=mp, country=ctry, zipc=zp)
    except Exception as exc:
        print("  %-8s 异常 %s" % (mp, str(exc)[:70]))
        continue
    if r.status_code == 200:
        j = r.json()
        its = j.get("itemSummaries") or []
        locs = [(x.get("itemLocation") or {}).get("country") for x in its]
        print("  %-8s -> HTTP 200 | %d 条 | listingMarketplaceId=%s | itemLocation 国家=%s"
              % (mp, len(its), (its[0].get("listingMarketplaceId") if its else None), locs))
    else:
        print("  %-8s -> HTTP %s | %s" % (mp, r.status_code, r.text[:140].replace("\n", " ")))

print()
print("=" * 76)
print("最终调用计数: %s" % CALLS)
print("=" * 76)
