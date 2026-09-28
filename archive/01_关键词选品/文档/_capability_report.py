# -*- coding: utf-8 -*-
"""eBay 能力体检：把所有"能用/不能用"的能力跑一遍，出结论表。

可重复运行 —— 以后想确认"现在我们到底能做什么"，跑这个就行。
消耗：eBay 约 8~10 次调用（可忽略）。
"""
import sys
import time

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

API = "https://api.ebay.com"
auth = ebay_auth.EbayAuth(verbose=False)


def token_for(scope):
    r = requests.post(API + "/identity/v1/oauth2/token",
                      auth=(auth.client_id, auth.client_secret),
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "scope": scope}, timeout=30)
    return (r.json().get("access_token") if r.status_code == 200 else None)


APP = token_for("https://api.ebay.com/oauth/api_scope")
FB = token_for("https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly")

H = {"Authorization": "Bearer " + APP, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
     "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
HF = dict(H, Authorization="Bearer " + FB)

rows = []


def probe(name, method, path, params=None, headers=None, body=None, note=""):
    t0 = time.time()
    try:
        if method == "GET":
            r = requests.get(API + path, headers=headers or H, params=params, timeout=35)
        else:
            r = requests.post(API + path, headers=dict(headers or H,
                                                       **{"Content-Type": "application/json"}),
                              json=body, timeout=35)
        ok = r.status_code in (200, 400)   # 400 = 存在且已鉴权（参数问题）
        if r.status_code == 200:
            detail = "✅ 可用"
            if isinstance(r.json(), dict):
                ks = list(r.json().keys())[:4]
                detail += " ｜ 字段: %s" % ", ".join(ks)
        elif r.status_code == 400:
            detail = "✅ 可用（需补参数）%s" % r.text[:70].replace("\n", " ")
        elif r.status_code in (401, 403):
            detail = "🔒 无权限"
        elif r.status_code == 404:
            detail = "❌ 端点不存在"
        else:
            detail = "⚠️ HTTP %s" % r.status_code
        rows.append((name, r.status_code, detail, note, time.time() - t0))
        return r
    except Exception as exc:
        rows.append((name, "-", "异常 %s" % str(exc)[:60], note, time.time() - t0))
        return None


# ---------- 已确认可用的能力 ----------
print("正在体检……")
probe("Browse 搜索（≤200条/次）", "GET", "/buy/browse/v1/item_summary/search",
      {"q": "wireless earbuds", "limit": 3}, note="主力：listingId/价格/广告位/卖家/上架时间")
r = probe("Browse 详情（item specifics）", "GET", "/buy/browse/v1/item/"
          + ((requests.get(API + "/buy/browse/v1/item_summary/search", headers=H,
                           params={"q": "wireless earbuds", "limit": 1},
                           timeout=30).json().get("itemSummaries") or [{}])[0].get("itemId", "")),
          note="localizedAspects + 类目路径 + 图片/描述")
probe("Taxonomy 类目属性", "GET",
      "/commerce/taxonomy/v1/category_tree/3/get_item_aspects_for_category",
      {"category_id": "112529"}, note="必填/推荐/可选属性 + 允许值")
probe("Taxonomy 类目建议", "GET",
      "/commerce/taxonomy/v1/category_tree/3/get_category_suggestions",
      {"q": "wireless earbuds"}, note="按关键词猜类目")
probe("★ Feedback 评价（销量近似）", "GET", "/commerce/feedback/v1/feedback",
      {"user_id": "jaza_trades", "feedback_type": "FEEDBACK_RECEIVED", "limit": 5},
      headers=HF, note="出单榜/好评率/成交价/买家原话（app token 即可）")
probe("Translation 翻译", "POST", "/commerce/translation/v1_beta/translate",
      headers=H, body={"from": "en", "to": "de", "text": ["wireless earbuds"],
                       "translationContext": "ITEM_TITLE"},
      note="英→德/法/西/意，单次 1 段文本")
probe("Developer Analytics 额度查询", "GET",
      "/developer/analytics/v1_beta/rate_limit/", note="官方额度表（146 条资源）")

# ---------- 拿不到的（验证一次，确认现状） ----------
probe("Marketplace Insights（销量真值）", "GET",
      "/buy/marketplace_insights/v1_beta/item_sales/search",
      {"q": "earbuds", "limit": 1}, note="Limited Release，已被 eBay 书面拒绝")
probe("Buy Marketing 最多人关注", "GET", "/buy/marketing/v1/most_watched_items",
      {"limit": 3}, note="需 buy.marketing scope（拿不到）")
probe("Catalog 商品目录", "GET", "/commerce/catalog/v1_beta/product_summary/search",
      {"q": "earbuds", "limit": 1}, note="额度有，调用 403")
probe("Sell 流量报表", "GET", "/sell/analytics/v1/traffic_report",
      {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"},
      note="需用户令牌；额度仅 100/天")
probe("Sell 订单", "GET", "/sell/fulfillment/v1/order", {"limit": 1},
      note="需用户令牌（缺 RuName）")
probe("Product Research（Terapeak）", "GET", "/sell/research/v1/product_insight",
      note="额度 5000/天，但端点未公开（已发邮件问 eBay）")

# ---------- 输出 ----------
print()
print("=" * 128)
print("eBay 能力体检报告")
print("=" * 128)
print("%-30s %-6s %-46s %s" % ("能力", "HTTP", "结论", "说明"))
print("-" * 128)
for name, code, detail, note, sec in rows:
    print("%-30s %-6s %-46s %s" % (name[:30], code, detail[:46], note[:56]))

ok = [r for r in rows if r[2].startswith("✅")]
lock = [r for r in rows if r[2].startswith("🔒")]
bad = [r for r in rows if r[2].startswith(("❌", "⚠️", "异常"))]
print("-" * 128)
print("可用 %d ｜ 无权限 %d ｜ 其它 %d" % (len(ok), len(lock), len(bad)))
print()
print("可用的能力：")
for n, _c, _d, note, _s in ok:
    print("   ✅ %-32s %s" % (n, note[:70]))
