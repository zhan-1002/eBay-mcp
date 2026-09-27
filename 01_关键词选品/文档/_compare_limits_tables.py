# -*- coding: utf-8 -*-
"""把「公开的 Sell 默认额度表」与「我们 app 的实际额度响应」对照。

目的：公开表是通用默认值；**我们自己的额度响应才是"这个 app 到底被授予了什么"**。
两者不一致的地方，就是最有价值的信息。
"""
import json
from collections import defaultdict

d = json.load(open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\rate_limits.json",
                   encoding="utf-8"))

# 公开 Sell 表里出现过的 API 名（用户粘贴的那张表）
PUBLIC_SELL = {
    "Account": "25,000/天", "Finances": "15,000/天",
    "Analytics(customer_service_metric)": "400/天",
    "Analytics(traffic_report/seller_standards)": "100/天",
    "Notification": "10,000/天", "Feed": "100,000/天", "Inventory": "200万/天",
    "Inventory Mapping": "20/天", "Media(document)": "100万/天", "Catalog": "10,000/天",
    "Charity": "5,000/天", "Metadata": "5,000/天", "Taxonomy": "5,000/天",
    "Merchandising": "5,000/天", "Marketing(Promotion)": "100,000/天",
    "Marketing(Ads)": "10,000/天", "Recommendation": "5,000/天",
    "Negotiation": "100万/天", "Fulfillment(Order)": "100,000/天",
    "Fulfillment(PaymentDispute)": "250,000/天", "Logistics": "250万/天",
    "Post-Order(各资源)": "各 5,000/天", "Business Policies(已弃用)": "5,000/天",
    "Compliance": "5,000/天", "Identity": "5,000/天", "Product API": "5,000/天",
    "Product Metadata": "5,000/天", "Trading API": "5,000/天",
    "Translation(beta)": "5,000/天",
}

# 我们 app 实际拿到的资源
ours = defaultdict(list)
for blk in d.get("rateLimits") or []:
    ctx = (blk.get("apiContext") or "").strip()
    api = "%s / %s %s" % (ctx, blk.get("apiName"), blk.get("apiVersion"))
    for res in blk.get("resources") or []:
        for rate in res.get("rates") or []:
            ours[api].append((res.get("name"), rate.get("limit"), rate.get("timeWindow")))

print("=" * 100)
print("我们 app 实际被授予的 API（按家族）—— 共 %d 个 API、%d 条资源"
      % (len(ours), sum(len(v) for v in ours.values())))
print("=" * 100)
for api in sorted(ours):
    print("\n【%s】" % api)
    for name, limit, win in sorted(set(ours[api])):
        w = "%dh" % (win // 3600) if win else "-"
        print("    %-46s 上限 %-10s 窗口 %s" % (name, limit, w))

print()
print("=" * 100)
print("★ 关键对照：公开 Sell 表里有没有这些？")
print("=" * 100)
checks = [
    ("ProductResearch（sell.research.product_insight）", "Product Research"),
    ("Feedback（commerce.feedback）", "Feedback"),
    ("Translation（commerce.translation.translate）", "Translation"),
    ("Catalog（commerce.catalog）", "Catalog"),
    ("Taxonomy（commerce.taxonomy）", "Taxonomy"),
    ("Metadata（sell.metadata）", "Metadata"),
    ("Recommendation（sell.recommendation）", "Recommendation"),
    ("Finances（payoutapi.sell.finances）", "Finances"),
    ("Feed（sell.feed）", "Feed"),
]
pub_text = " ".join(PUBLIC_SELL.keys()) + " " + " ".join(PUBLIC_SELL.values())
for name, key in checks:
    inpub = key.split("(")[0].strip().split()[0]
    hit = any(inpub.lower() in k.lower() for k in PUBLIC_SELL)
    print("   %-52s 公开表里有: %s" % (name, "✅" if hit else "❌ **没有**"))

print()
print("=" * 100)
print("★ 反查：公开表里有、但我们 app 没被授予的（这些调不了）")
print("=" * 100)
our_names = set()
for api in ours:
    for n, _l, _w in ours[api]:
        our_names.add((n or "").lower())
for k in sorted(PUBLIC_SELL):
    core = k.split("(")[0].strip().lower().replace(" api", "")
    hit = any(core in n for n in our_names)
    if not hit:
        print("   %-42s 默认 %-14s → 我们的额度表里**没有**" % (k, PUBLIC_SELL[k]))
