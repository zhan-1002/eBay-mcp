# -*- coding: utf-8 -*-
"""额度表里发现的 API，用**准确版本号**逐个探。

额度表给了每个资源的真实 apiName/apiVersion，据此拼路径比瞎猜准：
  commerce.translation.translate  → /commerce/translation/v1_beta/translate（不是 v1）
  buy.marketing.most_watched_items→ /buy/marketing/v1_beta/most_watched_items
  Sell/ProductResearch V1         → 试点 /sell/research/v1* 下的候选路径
"""
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
     "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
API = "https://api.ebay.com"

PROBES = [
    # —— 额度表里有、值得试的 ——
    ("★ ProductResearch（Terapeak）", "GET", "/sell/research/v1/product_insight", None),
    ("★ ProductResearch 变体2", "GET", "/sell/research/v1/product_insight/search", None),
    ("★ ProductResearch 变体3", "GET", "/sell/research/v1_beta/product_insight", None),
    ("★ 最多人关注商品（Buy Marketing）", "GET",
     "/buy/marketing/v1_beta/most_watched_items", {"limit": 5}),
    ("相似商品（Buy Marketing）", "GET", "/buy/marketing/v1_beta/similar_items",
     {"item_id": "v1|178469686091|0", "limit": 5}),
    ("翻译（正确版本 v1_beta）", "POST", "/commerce/translation/v1_beta/translate",
     {"from": "en", "to": "de", "text": ["wireless earbuds bluetooth 5.4"]}),
    ("批量取详情（bulk 有额度）", "POST", "/buy/browse/v1/item/get_items",
     {"requests": [{"uri": "/buy/browse/v1/item/v1|178469686091|0"}]}),
    ("Feed 快照（7.5万/天）", "GET", "/buy/feed/v1_beta/item_snapshot",
     {"category_id": "112529", "limit": 1}),
    ("Catalog（有额度 1万/天）", "GET", "/commerce/catalog/v1_beta/product_summary/search",
     {"q": "earbuds", "limit": 1}),
    ("Feedback API 猜测1", "GET", "/commerce/feedback/v1/feedback", {"limit": 1}),
    ("Feedback API 猜测2", "GET", "/commerce/feedback/v1/seller_feedback",
     {"filter": "user_id:test"}),
    ("Reputation（Sell）", "GET", "/sell/reputation/v1/feedback_summary", None),
]

print("%-34s %-46s %s" % ("目标", "路径", "结果"))
print("-" * 118)
for label, method, path, payload in PROBES:
    try:
        if method == "GET":
            r = requests.get(API + path, headers=A, params=payload, timeout=35)
        else:
            r = requests.post(API + path, headers=A, json=payload, timeout=35)
        if r.status_code == 200:
            body = r.text[:180].replace("\n", " ")
            note = "✅ 200 ｜ %s" % body
        elif r.status_code in (401, 403):
            try:
                e = (r.json().get("errors") or [{}])[0]
                note = "🔒 %s errorId=%s %s" % (r.status_code, e.get("errorId"),
                                               (e.get("message") or "")[:55])
            except Exception:
                note = "🔒 %s" % r.status_code
        elif r.status_code == 404:
            note = "❌ 404 路径不对"
        else:
            note = "⚠️ %s %s" % (r.status_code, r.text[:110].replace("\n", " "))
        print("%-34s %-46s %s" % (label, path[:46], note))
    except Exception as exc:
        print("%-34s %-46s 异常 %s" % (label, path[:46], str(exc)[:50]))
