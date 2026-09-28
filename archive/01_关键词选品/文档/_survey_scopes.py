# -*- coding: utf-8 -*-
"""区分两类 403：缺 scope（能自己补）vs 需 eBay 审批（补不了）。

做法：
  1. 逐个 scope 去申请 client_credentials 令牌 —— 拿得到 = 这个 scope 我们有；
     拿不到（invalid_scope / unauthorized_client）= 需要审批或提额
  2. 对拿得到的 scope，再用那个令牌去打对应接口，看接口本身通不通
  3. 顺便把 Browse EXTENDED 字段组真正返回了什么打出来（看有没有卖家反馈/销量类字段）
"""
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

auth = ebay_auth.EbayAuth(verbose=False)
CID, SEC = auth.client_id, auth.client_secret
API = "https://api.ebay.com"
MARKET = {"X-EBAY-C-MARKETPLACE-ID": "EBAY_GB", "Accept": "application/json",
          "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}

SCOPES = [
    ("Browse 搜索/详情（现用）", "https://api.ebay.com/oauth/api_scope"),
    ("Browse 批量取详情", "https://api.ebay.com/oauth/api_scope/buy.item.bulk"),
    ("★ 已售出/销量（Marketplace Insights）", "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"),
    ("Deal 促销", "https://api.ebay.com/oauth/api_scope/buy.deal"),
    ("Feed 批量快照", "https://api.ebay.com/oauth/api_scope/buy.feed"),
    ("Catalog 商品目录", "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly"),
    ("Taxonomy 类目属性", "https://api.ebay.com/oauth/api_scope/commerce.taxonomy.readonly"),
    ("Sell 分析（流量/转化）", "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly"),
    ("Sell 营销（广告）", "https://api.ebay.com/oauth/api_scope/sell.marketing"),
    ("Sell 库存", "https://api.ebay.com/oauth/api_scope/sell.inventory"),
    ("Sell 订单", "https://api.ebay.com/oauth/api_scope/sell.fulfillment"),
]

print("=" * 96)
print("一、scope 申请结果（拿得到 = 有权限范围；拿不到 = 需审批/提额）")
print("=" * 96)
granted = {}
for label, scope in SCOPES:
    r = requests.post(API + "/identity/v1/oauth2/token", auth=(CID, SEC),
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "scope": scope}, timeout=30)
    if r.status_code == 200:
        j = r.json()
        granted[scope] = j.get("access_token")
        print("  ✅ %-40s 拿到令牌（返回 scope: %s）" % (label, j.get("scope")))
    else:
        try:
            e = r.json()
            msg = "%s %s" % (e.get("error"), (e.get("error_description") or "")[:60])
        except Exception:
            msg = r.text[:80]
        print("  🔒 %-40s HTTP %s ｜ %s" % (label, r.status_code, msg))

print()
print("=" * 96)
print("二、用拿到的 scope 令牌打对应接口")
print("=" * 96)


def call(label, scope, method, path, payload=None):
    tok = granted.get(scope)
    if not tok:
        print("  ⏭  %-40s 跳过（没拿到该 scope 的令牌）" % label)
        return
    h = dict(MARKET)
    h["Authorization"] = "Bearer " + tok
    if method == "GET":
        r = requests.get(API + path, headers=h, params=payload, timeout=45)
    else:
        h["Content-Type"] = "application/json"
        r = requests.post(API + path, headers=h, json=payload, timeout=45)
    note = ""
    if r.status_code == 200:
        note = "返回字段: %s" % ", ".join(list(r.json().keys())[:6])
    else:
        try:
            e = (r.json().get("errors") or [{}])[0]
            note = "errorId=%s %s" % (e.get("errorId"), (e.get("message") or "")[:70])
        except Exception:
            note = r.text[:100].replace("\n", " ")
    print("  %s %-40s %-5s %s" % ("✅" if r.status_code == 200 else "❌",
                                  label, r.status_code, note))


call("★ Marketplace Insights 销量", "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights",
     "GET", "/buy/marketplace_insights/v1_beta/item_sales/search",
     {"q": "wireless earbuds", "limit": 1})
call("Deal 促销", "https://api.ebay.com/oauth/api_scope/buy.deal",
     "GET", "/buy/deal/v1/deal_item", {"limit": 1})
call("Catalog 商品目录", "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly",
     "GET", "/commerce/catalog/v1_beta/product_summary/search", {"q": "earbuds", "limit": 1})
call("Sell 分析（流量）", "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
     "GET", "/sell/analytics/v1/traffic_report",
     {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"})

print()
print("=" * 96)
print("三、Browse 的 EXTENDED 字段组到底给什么（看有没有销量/评论类字段）")
print("=" * 96)
h = dict(MARKET)
h["Authorization"] = "Bearer " + granted["https://api.ebay.com/oauth/api_scope"]
r = requests.get(API + "/buy/browse/v1/item_summary/search", headers=h,
                 params={"q": "wireless earbuds", "limit": 1, "fieldgroups": "EXTENDED"},
                 timeout=45)
it = (r.json().get("itemSummaries") or [{}])[0]
print("  item_summary 字段: %s" % ", ".join(sorted(it.keys())))
print()
print("  seller 字段: %s" % ", ".join(sorted((it.get("seller") or {}).keys())))
print("  卖家反馈相关值: feedbackScore=%s feedbackPercentage=%s"
      % ((it.get("seller") or {}).get("feedbackScore"),
         (it.get("seller") or {}).get("feedbackPercentage")))
print()
# 详情里有没有"卖出数量/库存/上架时间"这类
r2 = requests.get(API + "/buy/browse/v1/item/" + it["itemId"], headers=h, timeout=45)
d2 = r2.json()
for k in ("estimatedAvailabilities", "quantityLimitPerBuyer", "itemCreationDate",
          "itemEndDate", "buyingOptions", "sellerItemRevision", "priorityListing"):
    if k in d2:
        v = json.dumps(d2[k], ensure_ascii=False)
        print("  详情.%-24s = %s" % (k, v[:160]))
