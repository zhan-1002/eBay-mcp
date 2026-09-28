# -*- coding: utf-8 -*-
"""卖家端（Sell）API 普查。

两个手段：
  1. apis.guru 的公开 OpenAPI 索引里筛出所有 eBay 的 API 规格 → 拿到完整清单
  2. 用我们现有的 app token 逐个打端点：
       404 = 路径不存在
       401/403 = 路径存在，但缺权限（Sell 系列本来就需要用户令牌）
     这是唯一能区分"没有这个接口"和"有但没授权"的办法
"""
import json
import sys

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# ---------- 1. apis.guru 上的 eBay 规格清单 ----------
print("=" * 96)
print("一、apis.guru 索引里的 eBay API 规格")
print("=" * 96)
try:
    r = requests.get("https://api.apis.guru/v2/list.json", headers=H, timeout=90)
    print("HTTP %s ｜ %d 字节" % (r.status_code, len(r.content)))
    if r.status_code == 200:
        data = r.json()
        ebay = {k: v for k, v in data.items() if "ebay" in k.lower()}
        print("含 ebay 的规格 %d 个：" % len(ebay))
        for k in sorted(ebay):
            pref = (ebay[k].get("preferred") or "")
            info = ((ebay[k].get("versions") or {}).get(pref) or {}).get("info") or {}
            print("   %-46s %s" % (k, (info.get("title") or "")[:60]))
except Exception as exc:
    print("异常 %s" % str(exc)[:150])

# ---------- 2. 端点探测 ----------
sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
H2 = {"Authorization": "Bearer " + tok, "Accept": "application/json",
      "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
API = "https://api.ebay.com"

ENDPOINTS = [
    # —— Sell 系（卖家自有数据）——
    ("Sell 库存", "GET", "/sell/inventory/v1/inventory_item", {"limit": 1}),
    ("Sell 订单", "GET", "/sell/fulfillment/v1/order", {"limit": 1}),
    ("Sell 财务（交易明细）", "GET", "/sell/finances/v1/transaction", {"limit": 1}),
    ("Sell 分析：流量报表", "GET", "/sell/analytics/v1/traffic_report",
     {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"}),
    ("Sell 分析：卖家标准", "GET", "/sell/analytics/v1/seller_standards_profile",
     {"program": "PROGRAM_US", "cycle": "CURRENT"}),
    ("Sell 营销：广告活动", "GET", "/sell/marketing/v1/ad_campaign", {"limit": 1}),
    ("Sell 账号：权限", "GET", "/sell/account/v1/privilege", None),
    ("Sell 元数据：类目策略", "GET",
     "/sell/metadata/v1/marketplace/EBAY_GB/get_item_policies", None),
    ("Sell 推荐", "GET", "/sell/recommendation/v1/find", {"limit": 1}),
    ("Sell 议价：可议价商品", "GET", "/sell/negotiation/v1/find_eligible_items",
     {"limit": 1}),
    ("Sell 物流", "GET", "/sell/logistics/v1/shipment", {"limit": 1}),
    ("Sell 店铺", "GET", "/sell/stores/v1/get_store", None),
    ("Sell Feed（批量任务）", "GET", "/sell/feed/v1/task", {"limit": 1}),
    ("Sell 开发者分析：额度", "GET", "/sell/developer_analytics/v1/rate_limit", None),
    ("Sell 开发者分析：权限", "GET", "/sell/developer_analytics/v1/privilege", None),
    # —— Commerce 系 ——
    ("翻译 API", "POST", "/commerce/translation/v1/translate",
     {"from": "en", "to": "de", "text": ["wireless earbuds"]}),
    ("媒体：视频", "GET", "/commerce/media/v1/video", {"limit": 1}),
    ("消息 API", "GET", "/commerce/message/v1/conversation", {"limit": 1}),
    ("通知 API：订阅", "GET", "/commerce/notification/v1/subscription", None),
    ("身份 API", "GET", "/commerce/identity/v1/user", None),
    ("VeRO API", "GET", "/commerce/vero/v1/report", {"limit": 1}),
    ("慈善 API", "GET", "/commerce/charity/v1/charity_org", {"limit": 1}),
    # —— 其他 ——
    ("商品目录 Catalog", "GET", "/commerce/catalog/v1_beta/product_summary/search",
     {"q": "earbuds", "limit": 1}),
]

print()
print("=" * 96)
print("二、端点探测（404=不存在 ｜ 401/403=存在但无权限 ｜ 200=可用）")
print("=" * 96)
exist, missing = [], []
for label, method, path, payload in ENDPOINTS:
    try:
        if method == "GET":
            r = requests.get(API + path, headers=H2, params=payload, timeout=30)
        else:
            r = requests.post(API + path, headers=H2, json=payload, timeout=30)
        code = r.status_code
        if code == 404:
            missing.append(label)
            tag = "❌ 不存在"
        elif code in (401, 403):
            exist.append(label)
            tag = "🔒 存在，无权限"
        elif code == 200:
            exist.append(label)
            tag = "✅ 可用"
        else:
            exist.append(label)
            tag = "⚠️ HTTP %s" % code
        print("  %-28s %-22s %s" % (label, path[:22], tag))
    except Exception as exc:
        print("  %-28s 异常 %s" % (label, str(exc)[:60]))

print()
print("存在（需用户令牌授权）：%d 个" % len(exist))
for x in exist:
    print("   · %s" % x)
print("不存在/路径不对：%d 个" % len(missing))
for x in missing:
    print("   · %s" % x)
