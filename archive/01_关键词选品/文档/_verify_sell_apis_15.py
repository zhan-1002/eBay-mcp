# -*- coding: utf-8 -*-
"""逐个实测截图里那 15 个 Sell API：到底是"有额度"还是"能用"。

判据：403 = 路径存在、但我们没权限（需用户令牌）；404 = 路径不对；400/200 = 通了
"""
import sys
import time

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
API = "https://api.ebay.com"

# (截图里的名字, 额度, 实测路径)
TESTS = [
    ("Recommendation API", "5,000", API + "/sell/recommendation/v1/find", {"limit": 1}),
    ("Compliance API", "5,000", API + "/sell/compliance/v1/listing_violation_summary", {}),
    ("Logistics API", "250万", API + "/sell/logistics/v1_beta/shipment", {"limit": 1}),
    ("Finances API (Alpha)", "15,000", "https://apiz.ebay.com/sell/finances/v1/transaction",
     {"limit": 1}),
    ("Negotiation API", "有", API + "/sell/negotiation/v1/find_eligible_items", {"limit": 1}),
    ("Sell Feed API", "100,000", API + "/sell/feed/v1/task", {"limit": 1}),
    ("Marketing Ads API", "100,000", API + "/sell/marketing/v1/ad_campaign", {"limit": 1}),
    ("Stores API", "—", API + "/sell/stores/v1/get_store", {}),
    ("Inventory Mapping API", "—", API + "/sell/inventory_mapping/v1/listing", {"limit": 1}),
    ("Account API", "25,000", API + "/sell/account/v1/privilege", {}),
    ("Inventory API", "200万", API + "/sell/inventory/v1/inventory_item", {"limit": 1}),
    ("Fulfillment API", "100,000", API + "/sell/fulfillment/v1/order", {"limit": 1}),
    ("Marketing Promotion API", "10,000", API + "/sell/marketing/v1/promotion", {"limit": 1}),
    ("Analytics API", "100~400", API + "/sell/analytics/v1/traffic_report",
     {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"}),
    ("Metadata API", "5,000", API + "/sell/metadata/v1/marketplace/EBAY_GB", {}),
]

print("%-26s %-9s %-6s %s" % ("API（截图里的名字）", "额度/天", "HTTP", "实测结论"))
print("-" * 104)
usable, need_auth, wrong_path = [], [], []
for name, quota, url, params in TESTS:
    try:
        r = requests.get(url, headers=A, params=params, timeout=30)
        code = r.status_code
        if code == 200:
            verdict = "✅ 能用"
            usable.append(name)
        elif code in (401, 403):
            verdict = "🔒 路径存在，需【用户令牌/授权】"
            need_auth.append(name)
        elif code == 400:
            verdict = "★ 路径存在，参数问题（也需授权）"
            need_auth.append(name)
        elif code == 404:
            verdict = "❌ 路径不对（不代表没有）"
            wrong_path.append(name)
        else:
            verdict = "HTTP %s" % code
            wrong_path.append(name)
        print("%-26s %-9s %-6s %s" % (name, quota, code, verdict))
    except Exception as exc:
        print("%-26s %-9s %-6s 异常 %s" % (name, quota, "-", str(exc)[:40]))

print("-" * 104)
print("能用：%d ｜ 存在但需授权：%d ｜ 路径没试对：%d"
      % (len(usable), len(need_auth), len(wrong_path)))
if need_auth:
    print("\n授权后即可用的：%s" % "、".join(need_auth))
if wrong_path:
    print("路径待确认的：%s" % "、".join(wrong_path))
