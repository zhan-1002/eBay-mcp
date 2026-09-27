# -*- coding: utf-8 -*-
"""确认 Browse API 能不能拿到"热度"信号：拍卖出价次数 bidCount。

销量拿不到（Marketplace Insights 需审批），那竞拍次数就是现在最接近需求热度的指标。
顺便看看哪些字段能当"另类市场数据"用。
"""
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

tok = ebay_auth.EbayAuth(verbose=False).token()
H = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
     "Accept": "application/json",
     "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
API = "https://api.ebay.com"

print("=" * 92)
print("一、拍卖商品：看是否返回 currentBidPrice / bidCount")
print("=" * 92)
r = requests.get(API + "/buy/browse/v1/item_summary/search", headers=H,
                 params={"q": "wireless earbuds", "limit": 20,
                         "filter": "buyingOptions:{AUCTION}"}, timeout=45)
print("HTTP %s ｜ total=%s" % (r.status_code, r.json().get("total")))
items = r.json().get("itemSummaries") or []
print("返回 %d 条拍卖商品" % len(items))
if items:
    print("字段: %s" % ", ".join(sorted(items[0].keys())))
    print()
    for it in items[:6]:
        print("  bidCount=%-4s currentBid=%-10s buyingOptions=%s ｜ %s"
              % (it.get("bidCount"), (it.get("currentBidPrice") or {}).get("value"),
                 it.get("buyingOptions"), (it.get("title") or "")[:38]))

print()
print("=" * 92)
print("二、能当'另类市场数据'用的字段（现成可用）")
print("=" * 92)
r2 = requests.get(API + "/buy/browse/v1/item_summary/search", headers=H,
                  params={"q": "wireless earbuds", "limit": 50,
                          "fieldgroups": "EXTENDED"}, timeout=45)
its = r2.json().get("itemSummaries") or []
import collections
print("样本 %d 条：" % len(its))
print("  卖家数: %d ｜ 卖家反馈分中位: %s ｜ 好评率最低: %s"
      % (len({i.get("seller", {}).get("username") for i in its}),
         sorted((i.get("seller") or {}).get("feedbackScore") or 0 for i in its)[len(its) // 2],
         min(((i.get("seller") or {}).get("feedbackPercentage") or "100") for i in its)))
print("  上架时间范围: %s ~ %s"
      % (min((i.get("itemCreationDate") or "")[:10] for i in its),
         max((i.get("itemCreationDate") or "")[:10] for i in its)))
print("  支持议价(BEST_OFFER): %d 条 ｜ 顶评卖家: %d 条 ｜ 有优惠券: %d 条"
      % (sum(1 for i in its if "BEST_OFFER" in (i.get("buyingOptions") or [])),
         sum(1 for i in its if i.get("topRatedBuyingExperience")),
         sum(1 for i in its if i.get("availableCoupons"))))
lg = collections.Counter((i.get("itemLocation") or {}).get("country") for i in its)
print("  发货国分布: %s" % dict(lg.most_common(5)))
topsell = collections.Counter((i.get("seller") or {}).get("username") for i in its)
print("  卖家集中度 Top5: %s" % topsell.most_common(5))
