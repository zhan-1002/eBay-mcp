# -*- coding: utf-8 -*-
"""这些路径已确认存在（403），现在试申请对应的 scope —— 拿得到就能调用。

重点：buy.marketing（most_watched_items = 最多人关注商品）和 commerce.feedback（评论/反馈）
都在我们的额度表里（各 5000/天），如果 scope 能拿到，就是白捡的两个数据源。
"""
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

auth = ebay_auth.EbayAuth(verbose=False)
CID, SEC = auth.client_id, auth.client_secret
API = "https://api.ebay.com"

CANDIDATES = [
    ("buy.marketing", "https://api.ebay.com/oauth/api_scope/buy.marketing",
     "GET", "/buy/marketing/v1/most_watched_items", {"limit": 5}),
    ("buy.marketing.readonly", "https://api.ebay.com/oauth/api_scope/buy.marketing.readonly",
     "GET", "/buy/marketing/v1/most_watched_items", {"limit": 5}),
    ("commerce.feedback", "https://api.ebay.com/oauth/api_scope/commerce.feedback",
     "GET", "/commerce/feedback/v1/feedback", {}),
    ("commerce.feedback.readonly",
     "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly",
     "GET", "/commerce/feedback/v1/feedback", {}),
    ("sell.analytics.readonly", "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
     "GET", "/sell/analytics/v1/traffic_report",
     {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"}),
    ("commerce.catalog.readonly",
     "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly",
     "GET", "/commerce/catalog/v1_beta/product_summary/search", {"q": "earbuds", "limit": 1}),
    ("buy.feed", "https://api.ebay.com/oauth/api_scope/buy.feed",
     "GET", "/buy/feed/v1_beta/item_snapshot", {"category_id": "112529", "limit": 1}),
]

print("%-26s %-34s %s" % ("scope", "申请结果", "用它调接口"))
print("-" * 118)
for label, scope, method, path, params in CANDIDATES:
    r = requests.post(API + "/identity/v1/oauth2/token", auth=(CID, SEC),
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "scope": scope}, timeout=30)
    if r.status_code != 200:
        print("%-26s %-34s —" % (label, "🔒 invalid_scope"))
        continue
    tok = r.json().get("access_token")
    H = {"Authorization": "Bearer " + tok, "Accept": "application/json",
         "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
    r2 = requests.get(API + path, headers=H, params=params, timeout=30)
    if r2.status_code == 200:
        note = "✅ 200 ！！字段: %s" % ", ".join(list(r2.json().keys())[:6])
    elif r2.status_code in (401, 403):
        note = "🔒 %s 有 scope 但接口仍拒（可能需用户令牌）" % r2.status_code
    else:
        note = "HTTP %s %s" % (r2.status_code, r2.text[:80].replace("\n", " "))
    print("%-26s %-34s %s" % (label, "✅ 拿到令牌", note))
