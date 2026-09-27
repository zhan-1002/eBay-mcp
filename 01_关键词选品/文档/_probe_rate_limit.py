# -*- coding: utf-8 -*-
"""探测 eBay Browse API 的额度信息：响应头里到底有没有 rate limit？

打 2~3 次调用（可忽略的额度消耗），把**全部响应头**打出来看有没有
X-RateLimit-* / Retry-After 之类的字段。有的话就能读出当日额度与剩余量。
"""
import os
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

auth = ebay_auth.EbayAuth(verbose=False)
tok = auth.token()
print("凭据: %s ｜ token 来源: %s" % (auth.env, auth._source))
print("=" * 78)

HDR = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
       "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}

r = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                 headers=HDR, params={"q": "wireless earbuds", "limit": 1}, timeout=30)
print("[1] GET item_summary/search → HTTP %s" % r.status_code)
print("--- 响应头 ---")
for k, v in r.headers.items():
    print("    %-32s %s" % (k, v))
items = (r.json().get("itemSummaries") or []) if r.status_code == 200 else []
print("--- 结果 --- total=%s 返回 %d 条"
      % (r.json().get("total") if r.status_code == 200 else "-", len(items)))

if items:
    iid = items[0]["itemId"]
    r2 = requests.get("https://api.ebay.com/buy/browse/v1/item/" + iid, headers=HDR,
                      timeout=30)
    print()
    print("[2] GET item/%s → HTTP %s" % (iid, r2.status_code))
    print("--- 响应头 ---")
    for k, v in r2.headers.items():
        print("    %-32s %s" % (k, v))

print("=" * 78)
hits = [k for k in list(r.headers) + (list(r2.headers) if items else [])
        if "limit" in k.lower() or "rate" in k.lower() or "quota" in k.lower()
        or "retry" in k.lower()]
print("含 limit/rate/quota/retry 的响应头: %s" % (hits or "（一个都没有）"))
