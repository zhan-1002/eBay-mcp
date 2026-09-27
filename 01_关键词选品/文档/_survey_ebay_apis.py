# -*- coding: utf-8 -*-
"""eBay API 能力普查：还有哪些接口能用？销量/评论这类市场数据在哪？

做法：用**现有的 client_credentials 令牌**（不需要用户令牌）逐个打候选接口，
把状态码和错误报文记下来 —— 错误报文本身就说明了"缺什么权限/要不要审批"。

不猜、不查二手资料：**能不能用，打一次就知道**。
"""
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

TOKEN = ebay_auth.EbayAuth(verbose=False).token()
BASE = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA",
        "Content-Type": "application/json"}
API = "https://api.ebay.com"

# 先用一次 search 拿个真实 itemId 备用
r0 = requests.get(API + "/buy/browse/v1/item_summary/search", headers=BASE,
                  params={"q": "wireless earbuds", "limit": 1}, timeout=30)
IID = (r0.json().get("itemSummaries") or [{}])[0].get("itemId", "")
LEGACY = (r0.json().get("itemSummaries") or [{}])[0].get("legacyItemId", "")
print("样本 itemId=%s legacy=%s" % (IID, LEGACY))
print("=" * 92)

PROBES = [
    # (分组, 说明, method, url, params/json)
    ("Browse", "搜索（已确认可用）", "GET", "/buy/browse/v1/item_summary/search",
     {"q": "wireless earbuds", "limit": 1}),
    ("Browse", "详情（已确认可用）", "GET", "/buy/browse/v1/item/" + IID, None),
    ("Browse", "详情 + EXTENDED（卖家反馈/物流等扩展字段）", "GET",
     "/buy/browse/v1/item/" + IID, {"fieldgroups": "EXTENDED"}),
    ("Browse", "搜索 + fieldgroups=EXTENDED", "GET", "/buy/browse/v1/item_summary/search",
     {"q": "wireless earbuds", "limit": 1, "fieldgroups": "EXTENDED"}),
    ("Browse", "批量取详情 get_items（bulk scope）", "POST",
     "/buy/browse/v1/item/get_items", {"requests": [{"uri": "/buy/browse/v1/item/" + IID}]}),
    ("Browse", "旧 itemId 查 summary", "GET",
     "/buy/browse/v1/item_summary/" + str(LEGACY), None),
    ("市场数据", "★ Marketplace Insights：已售出 item_sales/search", "GET",
     "/buy/marketplace_insights/v1_beta/item_sales/search",
     {"q": "wireless earbuds", "limit": 1}),
    ("市场数据", "★ 同上（带 90 天筛选，官方示例口径）", "GET",
     "/buy/marketplace_insights/v1_beta/item_sales/search",
     {"q": "wireless earbuds", "limit": 1, "filter": "last90days"}),
    ("市场数据", "Deal API：促销/折扣商品", "GET", "/buy/deal/v1/deal_item",
     {"limit": 1}),
    ("市场数据", "Feed API：批量快照 item_snapshot", "GET",
     "/buy/feed/v1_beta/item_snapshot", {"category_id": "112529", "limit": 1}),
    ("商品目录", "Catalog：按关键词找商品（epid）", "GET",
     "/commerce/catalog/v1_beta/product_summary/search", {"q": "wireless earbuds", "limit": 1}),
    ("商品目录", "Catalog：类目建议", "GET",
     "/commerce/catalog/v1_beta/product_summary/search", {"q": "earbuds", "limit": 1}),
    ("类目属性", "Taxonomy：类目属性（已确认可用）", "GET",
     "/commerce/taxonomy/v1/category_tree/3/get_item_aspects_for_category",
     {"category_id": "112529"}),
    ("类目属性", "Taxonomy：按关键词猜类目", "GET",
     "/commerce/taxonomy/v1/category_tree/3/get_category_suggestions",
     {"q": "wireless earbuds"}),
    ("类目属性", "Taxonomy：类目兼容属性（适配机型）", "GET",
     "/commerce/taxonomy/v1/category_tree/3/get_compatibility_properties",
     {"category_id": "112529"}),
    ("卖家/账号", "Sell Analytics（需用户令牌）", "GET",
     "/sell/analytics/v1/traffic_report", {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"}),
    ("卖家/账号", "Sell Marketing 广告活动（需用户令牌）", "GET",
     "/sell/marketing/v1/ad_campaign", {"limit": 1}),
    ("卖家/账号", "Sell Inventory（需用户令牌）", "GET",
     "/sell/inventory/v1/inventory_item", {"limit": 1}),
    ("卖家/账号", "Sell Fulfillment 订单（需用户令牌）", "GET",
     "/sell/fulfillment/v1/order", {"limit": 1}),
]

rows = []
for group, name, method, path, payload in PROBES:
    try:
        if method == "GET":
            r = requests.get(API + path, headers=BASE, params=payload, timeout=45)
        else:
            r = requests.post(API + path, headers=BASE, json=payload, timeout=45)
        code = r.status_code
        note = ""
        if code == 200:
            d = r.json()
            keys = [k for k in d.keys()][:6]
            note = "返回字段: %s" % ", ".join(keys)
        else:
            try:
                err = (r.json().get("errors") or [{}])[0]
                note = "errorId=%s %s" % (err.get("errorId"), (err.get("message") or "")[:80])
                if err.get("longMessage"):
                    note += " ｜ " + err["longMessage"][:90]
            except Exception:
                note = r.text[:120].replace("\n", " ")
    except Exception as exc:
        code, note = "异常", str(exc)[:110]
    rows.append((group, name, code, note))

cur = None
for group, name, code, note in rows:
    if group != cur:
        print("\n【%s】" % group)
        cur = group
    mark = "✅" if code == 200 else ("🔒" if code in (401, 403) else "❌")
    print("  %s %-46s %-6s %s" % (mark, name[:46], code, note))

print()
print("=" * 92)
print("汇总：可用 %d ｜ 无权限/需审批 %d ｜ 其它失败 %d"
      % (sum(1 for x in rows if x[2] == 200),
         sum(1 for x in rows if x[2] in (401, 403)),
         sum(1 for x in rows if x[2] not in (200, 401, 403))))
