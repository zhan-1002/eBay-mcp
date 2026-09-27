# -*- coding: utf-8 -*-
"""从 hendt/ebay-api 内嵌的 OAS3 规格里读出**真实路径与 scope**，并实测。

重点三个（我们额度表里有、但之前没调通的）：
  commerce_feedback_v1_beta     → 评论/反馈（额度 commerce.feedback 5000/天）
  buy_marketing_v1_beta         → most_watched_items（额度 5000/天，需求信号）
  buy_marketplace_insights      → 确认 scope（已拒绝，仅作对照）
"""
import re
import sys

import requests

RAW = "https://raw.githubusercontent.com/hendt/ebay-api/main/src/types/restful/specs/"
H = {"User-Agent": "Mozilla/5.0"}

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

FILES = {
    "Feedback (评论/反馈)": "commerce_feedback_v1_beta_oas3.ts",
    "Buy Marketing (关注/相似)": "buy_marketing_v1_beta_oas3.ts",
    "Marketplace Insights (销量·已拒)": "buy_marketplace_insights_v1_beta_oas3.ts",
}

found_paths = {}
for label, fn in FILES.items():
    print("=" * 96)
    print("【%s】%s" % (label, fn))
    print("=" * 96)
    try:
        r = requests.get(RAW + fn, headers=H, timeout=60)
        print("HTTP %s ｜ %d 字节" % (r.status_code, len(r.content)))
        if r.status_code != 200:
            continue
        t = r.text
        # 路径：形如  "/xxx/yyy": {   或  '/xxx':
        paths = sorted(set(re.findall(r'["\'](/[A-Za-z0-9_\-/{}]+)["\']\s*:', t)))
        paths = [p for p in paths if p.count("/") >= 1 and not p.startswith("/#")]
        print("  路径 %d 个：" % len(paths))
        for p in paths[:14]:
            print("     %s" % p)
        # scope
        scopes = sorted(set(re.findall(r"(https://api\.ebay\.com/oauth/api_scope[\w./]*)", t)))
        if scopes:
            print("  scope：")
            for s in scopes[:8]:
                print("     %s" % s)
        # 基础 URL
        for m in re.finditer(r"(https://api\.ebay\.com/[A-Za-z0-9_/\-{}]+)", t):
            print("  基础 URL 片段: %s" % m.group(1))
            break
        found_paths[label] = paths
    except Exception as exc:
        print("  异常 %s" % str(exc)[:100])
    print()

# ---- 实测 ----
tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
API = "https://api.ebay.com"

print("=" * 96)
print("实测：拿规格里的真实路径逐个打（404=不存在 ｜ 403=存在但无权限 ｜ 400/200=通了）")
print("=" * 96)
TEST = [
    ("/commerce/feedback/v1_beta/feedback", None),
    ("/commerce/feedback/v1_beta/feedback_summary", None),
    ("/buy/marketing/v1_beta/most_watched_items", {"limit": 5}),
    ("/buy/marketing/v1_beta/similar_items", {"item_id": "v1|178469686091|0"}),
    ("/buy/marketplace_insights/v1_beta/item_sales/search",
     {"q": "wireless earbuds", "limit": 1}),
]
for p, q in TEST:
    try:
        r = requests.get(API + p, headers=A, params=q, timeout=30)
        if r.status_code == 200:
            tag = "✅ 200 通了！字段: %s" % ", ".join(list(r.json().keys())[:6])
        elif r.status_code in (401, 403):
            tag = "🔒 %s 存在但无权限" % r.status_code
        elif r.status_code == 400:
            tag = "★ 400 存在（参数问题）"
        elif r.status_code == 404:
            tag = "❌ 404"
        else:
            tag = "HTTP %s" % r.status_code
        print("  %-52s %s" % (p, tag))
    except Exception as exc:
        print("  %-52s 异常 %s" % (p, str(exc)[:50]))
