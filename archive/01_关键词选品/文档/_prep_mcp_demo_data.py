# -*- coding: utf-8 -*-
"""为 MCP 演示准备真实数据：价格带/广告位/品牌 + 真实竞品评价 + 类目要求。"""
import glob
import io
import json
import sys
from collections import Counter

import requests

# ---------- 1. 从我们最近的采集结果里取真实数字 ----------
p = sorted(glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay"
                     r"\01_关键词选品\输出\api_uk_wireless_earbuds_*.json"))[-1]
d = json.load(io.open(p, encoding="utf-8"))
m = d["market"]
print("数据来源: %s（%d 条）" % (p.split("\\")[-1], d.get("item_count")))
print("=" * 96)
print("【价格带与广告位】")
for r in m["price_bands"]:
    print("   %-8s 商品 %-3s 占比 %-6s 竞争强度 %-8s"
          % (r["价格段"], r["商品数"], r["占比%"], r["竞争强度"]))
print("   最稀疏段: %s ｜ 分位 p25=%s p50=%s p75=%s"
      % (m["price_stat"].get("最稀疏段"), m["price_stat"].get("p25"),
         m["price_stat"].get("p50"), m["price_stat"].get("p75")))
print()
for r in m["ad_rows"]:
    print("   广告位 %-8s 广告 %-3s/%s 条 占比 %-6s 投放强度 %s"
          % (r["价格带"], r["广告位条数"], r["商品数"], r["广告位占比%"], r["投放强度"]))
print("   位次概览: %s" % m["ad_pos_summary"])
print()
print("【品牌结构】")
b = m["brand"]["structured"]["summary"]
print("   真品牌 %s%% ｜ 白牌 %s%% ｜ 品牌 %s 种 ｜ %s"
      % (b.get("真品牌占位率%"), b.get("白牌占比%"), b.get("真品牌种类数"),
         b.get("结论")))
print("   前 8 品牌: %s" % "、".join(
    "%s %s条" % (x["品牌"], x["商品数"]) for x in m["brand"]["structured"]["brand_rows"][:8]))
print()
print("【类目】%s %s"
      % (d["category"].get("recommend_leaf_id"), d["category"].get("recommend_leaf_name")))
print("【推荐标题】前 5 条：")
for t in (m.get("target_titles") or [])[:5]:
    print("   %s（%d 字符）" % (t, len(t)))

# ---------- 2. 类目必填属性（用缓存，0 次调用）----------
print()
print("【类目必填属性（Taxonomy 缓存）】")
try:
    tx = json.load(io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay"
                           r"\01_关键词选品\数据\taxonomy\EBAY_GB_112529.json",
                           encoding="utf-8"))
    must = [a for a in tx["aspects"]
            if (a.get("aspectConstraint") or {}).get("aspectRequired")]
    sel = [a for a in tx["aspects"]
           if (a.get("aspectConstraint") or {}).get("aspectMode") == "SELECTION_ONLY"]
    print("   必填 %d 个: %s" % (len(must), "、".join(a["localizedAspectName"] for a in must)))
    print("   只能选候选值 %d 个: %s" % (len(sel), "、".join(a["localizedAspectName"] for a in sel)))
except Exception as e:
    print("   缓存读取失败: %s" % e)

# ---------- 3. 真实竞品评价（蓝牙耳机卖家）----------
print()
print("=" * 96)
print("【真实竞品评价数据】")
sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

auth = ebay_auth.EbayAuth(verbose=False)
r = requests.post("https://api.ebay.com/identity/v1/oauth2/token",
                  auth=(auth.client_id, auth.client_secret),
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  data={"grant_type": "client_credentials",
                        "scope": "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly"},
                  timeout=30)
A = {"Authorization": "Bearer " + r.json()["access_token"],
     "Accept": "application/json", "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}

# 从采集数据里挑一个主要卖耳机的卖家
sellers = Counter()
for it in d.get("items") or []:
    u = it.get("seller")
    if isinstance(u, str) and u:
        sellers[u] += 1
target = sellers.most_common(1)[0][0]
print("   取样卖家: %s（在我们 200 条里占 %d 条）" % (target, sellers[target]))

rr = requests.get("https://api.ebay.com/commerce/feedback/v1/feedback", headers=A,
                  params={"user_id": target, "feedback_type": "FEEDBACK_RECEIVED",
                          "limit": 200}, timeout=45)
if rr.status_code == 200:
    j = rr.json()
    ents = j.get("feedbackEntries") or []
    print("   该卖家累计评价总数: %s ｜ 本页 %d 条" % (j["pagination"]["total"], len(ents)))
    print("   评价性质: %s" % dict(Counter(e.get("commentType") for e in ents)))
    byitem = Counter()
    for e in ents:
        o = e.get("orderLineItemSummary") or {}
        byitem[(o.get("listingTitle") or "")[:50]] += 1
    print("   出单榜 Top6:")
    for t, n in byitem.most_common(6):
        print("      %-52s %d 单" % (t, n))
    man = [e for e in ents if not e.get("automatedFeedback")]
    print("   真实买家评论（筛选掉系统自动评价，%d/%d 条）:" % (len(man), len(ents)))
    for e in man[:5]:
        c = (e.get("feedbackComment") or {}).get("commentText") or ""
        if c:
            print("      [%s] %s" % (e.get("commentType"), c[:60]))
else:
    print("   评价接口 HTTP %s" % rr.status_code)
