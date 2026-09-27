# -*- coding: utf-8 -*-
"""把 ProductResearch（sell.research.product_insight）的端点挖出来。

判据：
  404 = 路径不存在
  403/401 = **路径存在**，只是没权限（我们要找的就是这种）
  400 = 路径存在且已通过鉴权（参数问题）
"""
import json
import re
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

# ① 先在 apis.guru 索引里找有没有 research/insight 的规格
data = json.load(open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\apisguru_list.json",
                      encoding="utf-8"))
print("=" * 92)
print("一、apis.guru 索引里搜 research / insight / analytics 规格")
print("=" * 92)
hit = False
for k in sorted(data):
    if "ebay" in k.lower() and re.search(r"research|insight|analytic", k, re.I):
        pref = data[k].get("preferred")
        info = ((data[k].get("versions") or {}).get(pref) or {}).get("info") or {}
        print("   %-40s %s" % (k, info.get("title")))
        hit = True
if not hit:
    print("   （没有 ProductResearch 的公开规格）")

# ② 端点爆破
tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
     "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
API = "https://api.ebay.com"

CANDIDATES = [
    "/sell/research/v1/product_insight",
    "/sell/research/v1/product_insight/search",
    "/sell/research/v1/product_insights",
    "/sell/research/v1/search",
    "/sell/research/v1/insight",
    "/sell/research/v1_beta/product_insight",
    "/sell/research/v1_beta/product_insight/search",
    "/sell/product_research/v1/product_insight",
    "/sell/productresearch/v1/product_insight",
    "/sell/research/v1/",
    "/sell/research/v1/item",
    "/sell/research/v1/sold",
    "/commerce/research/v1/product_insight",
    "/sell/analytics/v1/product_insight",
    "/sell/research/v1/query",
    "/sell/research/v1/report",
]

print()
print("=" * 92)
print("二、端点爆破（找 403/401/400 —— 那说明路径存在）")
print("=" * 92)
found = []
for p in CANDIDATES:
    for q in ({}, {"q": "wireless earbuds"}, {"keyword": "wireless earbuds"}):
        try:
            r = requests.get(API + p, headers=A, params=q, timeout=25)
        except Exception as exc:
            print("  %-52s 异常 %s" % (p, str(exc)[:40]))
            break
        code = r.status_code
        if code == 404:
            tag = "404"
        elif code in (401, 403):
            tag = "★★ %s 存在！" % code
            found.append((p, q, code, r.text[:150]))
        elif code == 400:
            tag = "★ 400 存在（参数问题）"
            found.append((p, q, code, r.text[:150]))
        elif code == 200:
            tag = "✅ 200 通了！"
            found.append((p, q, code, r.text[:200]))
        else:
            tag = "HTTP %s" % code
            found.append((p, q, code, r.text[:150]))
        print("  %-52s %-22s %s" % (p, str(q)[:20], tag))
        if code != 404:
            break       # 这个路径有结论了，不用再换参数

print()
print("=" * 92)
print("结论")
print("=" * 92)
if found:
    for p, q, code, body in found:
        print("  %s  %s  %s\n     %s" % (p, q, code, body.replace("\n", " ")))
else:
    print("  16 个候选路径全部 404 —— 说明 ProductResearch 的端点不在这些命名下。")
    print("  下一步只能靠问 eBay（额度表里它确实存在，端点却没公开）。")
