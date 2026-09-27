# -*- coding: utf-8 -*-
"""eBay 沙箱密钥连通性实测（只读）。

沙箱环境域名：api.sandbox.ebay.com；数据是 eBay 提供的测试数据，不含真实商品。
"""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
CFG = os.path.join(PROJ, "config.local.json")

# config 里缺凭据时，用沙箱密钥补齐（仅本地文件，不入库）
SANDBOX = {
    "client_id": "BETA-SBX-c82936ba4-c0f1d079",
    "client_secret": "16880a0b-a69a-4ac8-91fd-93986bb62f8a",
}

print("=" * 78)
print("① 准备配置")
print("=" * 78)
data = {}
if os.path.isfile(CFG):
    data = json.load(open(CFG, encoding="utf-8"))
api = data.get("ebay_api") or {}
if not (api.get("client_id") and api.get("client_secret")):
    api.update(SANDBOX)
    data["ebay_api"] = api
    with open(CFG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("  已把沙箱密钥写入 %s（gitignore 已覆盖）" % CFG)
else:
    print("  config 里已有 ebay_api 凭据，沿用")
print("  client_id 前 12 位: %s..." % (api.get("client_id") or "")[:12])
print("  顶层键: %s" % list(data.keys()))

cid = api.get("client_id")
sec = api.get("client_secret")

print()
print("=" * 78)
print("② 换 token（沙箱）")
print("=" * 78)
TOKEN_URLS = [
    ("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
    ("生产", "https://api.ebay.com/identity/v1/oauth2/token"),
]
token = None
token_url_ok = None
for label, url in TOKEN_URLS:
    t0 = time.time()
    try:
        r = requests.post(url, auth=(cid, sec),
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data={"grant_type": "client_credentials",
                                "scope": "https://api.ebay.com/oauth/api_scope"},
                          timeout=30)
    except Exception as exc:
        print("  [%s] 请求异常: %s" % (label, str(exc)[:110]))
        continue
    body = r.text[:300]
    print("  [%s] HTTP %s  (%.1fs)" % (label, r.status_code, time.time() - t0))
    if r.status_code == 200:
        j = r.json()
        token = j.get("access_token")
        token_url_ok = url
        print("      access_token 长度 %d，有效期 %s 秒" % (len(token or ""), j.get("expires_in")))
        break
    else:
        print("      返回: %s" % body)

if not token:
    print("\n换 token 失败，后续测试中止。")
    sys.exit(2)

print()
print("=" * 78)
print("③ 沙箱搜索（Browse item_summary/search）")
print("=" * 78)
hdrs = {
    "Authorization": "Bearer " + token,
    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DUS%2Czip%3D10001",
    "Accept": "application/json",
}
search_url = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"
params = {"q": "wireless earbuds", "limit": 5,
          "fieldgroups": "EXTENDED,ASPECT_REFINEMENTS,CATEGORY_REFINEMENTS"}
try:
    r = requests.get(search_url, headers=hdrs, params=params, timeout=45)
except Exception as exc:
    print("  请求异常: %s" % str(exc)[:150])
    sys.exit(3)
print("  HTTP %s" % r.status_code)
if r.status_code != 200:
    print("  返回: %s" % r.text[:500])
    sys.exit(4)
payload = r.json()
items = payload.get("itemSummaries") or []
print("  命中 %d 条" % len(items))
print("  顶层键: %s" % list(payload.keys()))
if items:
    print("\n  第 1 条 itemSummary 的全部字段:")
    for k, v in items[0].items():
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        print("     %-22s = %s" % (k, s[:90]))
    print("\n  ★ 是否含 item specifics 类字段: %s"
          % [k for k in items[0].keys()
             if any(x in k.lower() for x in ("aspect", "specific"))] or "无")
    print("  ★ 是否有 localizedAspects: %s" % ("localizedAspects" in items[0]))
    print("  ★ 是否有 leafCategoryIds: %s" % ("leafCategoryIds" in items[0]))
    print("  ★ 是否有 categoryPath: %s" % ("categoryPath" in items[0]))

    # 取一条详情
    iid = items[0].get("itemId")
    if iid:
        print()
        print("=" * 78)
        print("④ 单条 getItem（%s）" % iid)
        print("=" * 78)
        from urllib.parse import quote
        url = "https://api.sandbox.ebay.com/buy/browse/v1/item/" + quote(iid, safe="")
        r2 = requests.get(url, headers=hdrs, timeout=30)
        print("  HTTP %s" % r2.status_code)
        if r2.status_code == 200:
            det = r2.json()
            print("  返回键: %s" % list(det.keys()))
            asp = det.get("localizedAspects") or []
            print("  localizedAspects 条数: %d" % len(asp))
            for a in asp[:8]:
                print("     %-24s = %s" % (a.get("name"), str(a.get("value"))[:60]))
            print("  categoryPathIds: %s" % det.get("categoryPathIds"))
            print("  categoryId: %s" % det.get("categoryId"))
            print("  description 长度: %d" % len(det.get("description") or ""))
            print("  imageUrl 数量: %d" % len(det.get("additionalImages") or []) + (1 if det.get("image") else 0))
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "输出", "探查")
            os.makedirs(p, exist_ok=True)
            with open(os.path.join(p, "sandbox_getitem.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(det, f, ensure_ascii=False, indent=2)
            print("  已存 sandbox_getitem.json")
        else:
            print("  返回: %s" % r2.text[:300])

print()
print("=" * 78)
print("⑤ 沙箱是否有『售出/成交』权限（Marketplace Insights 探测）")
print("=" * 78)
mi_url = "https://api.sandbox.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
try:
    r3 = requests.get(mi_url, headers=hdrs, params={"q": "earbuds", "limit": 1}, timeout=30)
    print("  HTTP %s" % r3.status_code)
    print("  返回: %s" % r3.text[:400])
except Exception as exc:
    print("  请求异常: %s" % str(exc)[:150])
