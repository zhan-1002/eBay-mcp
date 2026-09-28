# -*- coding: utf-8 -*-
"""用 hendt 规格里的**准确完整路径**实测（重点：Feedback 评论/反馈 API）。"""
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
API = "https://api.ebay.com"

TESTS = [
    # Feedback（评论/反馈）—— 规格里的 4 个路径 × 两个版本前缀
    ("Feedback /feedback (v1_beta)", "/commerce/feedback/v1_beta/feedback", {}),
    ("Feedback /feedback (v1)", "/commerce/feedback/v1/feedback", {}),
    ("Feedback /feedback_rating_summary", "/commerce/feedback/v1_beta/feedback_rating_summary",
     {}),
    ("Feedback /feedback_rating_summary (v1)",
     "/commerce/feedback/v1/feedback_rating_summary", {}),
    ("Feedback /awaiting_feedback", "/commerce/feedback/v1_beta/awaiting_feedback", {}),
    # Buy Marketing（规格里只有 merchandised_product；额度表里还有 most_watched/similar）
    ("BuyMarketing /merchandised_product", "/buy/marketing/v1_beta/merchandised_product",
     {"limit": 5}),
    ("BuyMarketing most_watched (v1)", "/buy/marketing/v1/most_watched_items", {"limit": 5}),
    ("BuyMarketing most_watched (v1_beta)",
     "/buy/marketing/v1_beta/most_watched_items", {"limit": 5}),
    ("BuyMarketing similar_items (v1)", "/buy/marketing/v1/similar_items",
     {"item_id": "v1|178469686091|0"}),
    # 对照
    ("Marketplace Insights item_sales", "/buy/marketplace_insights/v1_beta/item_sales/search",
     {"q": "earbuds", "limit": 1}),
    ("Sell Analytics traffic_report", "/sell/analytics/v1/traffic_report",
     {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"}),
]

print("%-42s %-58s %s" % ("目标", "路径", "结果"))
print("-" * 130)
for label, path, params in TESTS:
    try:
        r = requests.get(API + path, headers=A, params=params, timeout=30)
        if r.status_code == 200:
            tag = "✅ 200 通了！字段: %s" % ", ".join(list(r.json().keys())[:6])
        elif r.status_code in (401, 403):
            tag = "🔒 %s 存在但无权限" % r.status_code
        elif r.status_code == 400:
            tag = "★ 400 存在（参数问题）"
        elif r.status_code == 404:
            tag = "❌ 404 不存在"
        else:
            tag = "HTTP %s" % r.status_code
        print("%-42s %-58s %s" % (label, path[:58], tag))
    except Exception as exc:
        print("%-42s %-58s 异常 %s" % (label, path[:58], str(exc)[:40]))
