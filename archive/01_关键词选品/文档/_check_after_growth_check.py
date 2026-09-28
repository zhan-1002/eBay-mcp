# -*- coding: utf-8 -*-
"""Growth Check 结果核对：销量被拒了，那"提额 / Catalog / bulk"批没批？

eBay 的回复只说了 Marketplace Insights 不给，没提其他三项 —— 所以直接实测：
逐个 scope 申请令牌 + 用令牌打对应接口。
"""
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

auth = ebay_auth.EbayAuth(verbose=False)
CID, SEC = auth.client_id, auth.client_secret
API = "https://api.ebay.com"
HDR = {"X-EBAY-C-MARKETPLACE-ID": "EBAY_GB", "Accept": "application/json"}

SCOPES = [
    ("（现用）Browse 搜索/详情", "https://api.ebay.com/oauth/api_scope"),
    ("销量 Marketplace Insights", "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"),
    ("批量取详情 buy.item.bulk", "https://api.ebay.com/oauth/api_scope/buy.item.bulk"),
    ("Catalog 商品目录", "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly"),
    ("Feed 批量快照", "https://api.ebay.com/oauth/api_scope/buy.feed"),
    ("Deal 促销", "https://api.ebay.com/oauth/api_scope/buy.deal"),
]

print("=" * 90)
print("一、scope 申请结果（对比申请前后有没有变化）")
print("=" * 90)
granted = {}
for label, scope in SCOPES:
    r = requests.post(API + "/identity/v1/oauth2/token", auth=(CID, SEC),
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "scope": scope}, timeout=30)
    if r.status_code == 200:
        granted[scope] = r.json().get("access_token")
        print("  ✅ %-32s 拿到令牌" % label)
    else:
        try:
            e = r.json()
            msg = "%s" % (e.get("error") or r.status_code)
        except Exception:
            msg = str(r.status_code)
        print("  🔒 %-32s 拿不到（%s）" % (label, msg))

print()
print("=" * 90)
print("二、拿到的 scope 去打接口，看接口是否真的可用")
print("=" * 90)


def call(label, scope, method, path, payload=None):
    tok = granted.get(scope)
    if not tok:
        print("  ⏭  %-30s 跳过（没令牌）" % label)
        return None
    h = dict(HDR)
    h["Authorization"] = "Bearer " + tok
    if method == "GET":
        r = requests.get(API + path, headers=h, params=payload, timeout=45)
    else:
        h["Content-Type"] = "application/json"
        r = requests.post(API + path, headers=h, json=payload, timeout=45)
    note = ""
    if r.status_code == 200:
        note = "✅ 可用 ｜ 返回字段: %s" % ", ".join(list(r.json().keys())[:5])
    else:
        try:
            e = (r.json().get("errors") or [{}])[0]
            note = "❌ errorId=%s %s" % (e.get("errorId"), (e.get("message") or "")[:60])
        except Exception:
            note = "❌ HTTP %s %s" % (r.status_code, r.text[:80])
    print("  %-30s %s" % (label, note))
    return r


print("· 销量（再确认一次）")
call("item_sales/search", "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights",
     "GET", "/buy/marketplace_insights/v1_beta/item_sales/search",
     {"q": "wireless earbuds", "limit": 1})
print("· Catalog")
call("product_summary/search", "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly",
     "GET", "/commerce/catalog/v1_beta/product_summary/search", {"q": "earbuds", "limit": 1})

# 批量取详情需要真实 itemId
r0 = requests.get(API + "/buy/browse/v1/item_summary/search",
                  headers=dict(HDR, Authorization="Bearer " + granted["https://api.ebay.com/oauth/api_scope"]),
                  params={"q": "wireless earbuds", "limit": 1}, timeout=30)
iid = (r0.json().get("itemSummaries") or [{}])[0].get("itemId", "")
print("· 批量取详情（bulk）")
call("item/get_items", "https://api.ebay.com/oauth/api_scope/buy.item.bulk",
     "POST", "/buy/browse/v1/item/get_items",
     {"requests": [{"uri": "/buy/browse/v1/item/" + iid}]})

print()
print("说明：Browse 的**每日调用额度**（申请里要的 20,000）无法用接口查 ——")
print("      eBay 不在响应头返回额度信息、也没有公开的额度查询接口，只能去开发者后台看。")
