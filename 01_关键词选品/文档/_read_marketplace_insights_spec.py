# -*- coding: utf-8 -*-
"""读 hendt 内嵌的 Marketplace Insights 完整 OAS3 规格 —— 这是"销量 API"的权威定义。
看：参数、返回字段（到底给什么销量数据）、scope。
同时看 GitHub 上两个 Terapeak/已售出相关的仓库说明了什么。
"""
import base64
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"
DIR = "src/types/restful/specs"

# ---------- 1. Marketplace Insights 规格 ----------
url = "%s/repos/hendt/ebay-api/contents/%s/buy_marketplace_insights_v1_beta_oas3.ts" % (API, DIR)
d = requests.get(url, headers=H, timeout=90).json()
txt = base64.b64decode(d["content"]).decode("utf-8", "replace")
open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mi_spec.ts", "w",
     encoding="utf-8").write(txt)
print("=" * 96)
print("一、Marketplace Insights 规格（%d 字符）" % len(txt))
print("=" * 96)

print("\n--- 请求参数（query）---")
for m in re.finditer(r"(?:@description\s+)([^*/]{20,220}?)\s*\*/\s*(\w+)\??:\s*(\w+)", txt):
    desc, name, typ = m.group(1), m.group(2), m.group(3)
    if name.lower() in ("q", "limit", "offset", "filter", "sort", "fieldgroups",
                        "category_ids", "seller_id", "last_sold_date"):
        print("  %-16s (%s) %s" % (name, typ, re.sub(r"\s+", " ", desc)[:150]))

print("\n--- 返回的销量相关字段 ---")
KEYS = ["totalSoldQuantity", "lastSoldDate", "quantitySold", "soldQuantity",
        "itemSales", "total", "averageSoldPrice", "lastSoldPrice", "soldPrice",
        "uniqueBidderCount", "bidCount", "totalSoldQty", "salesData", "percentChange"]
for k in KEYS:
    hits = list(re.finditer(k, txt))
    if hits:
        i = hits[0].start()
        frag = re.sub(r"\s+", " ", txt[max(0, i - 220):i + 260])
        print("  ★ %-20s 出现 %d 次" % (k, len(hits)))
        print("      …%s…" % frag[:330])
print("\n--- 是否为必填/枚举筛选值 ---")
for m in re.finditer(r"(last90days|last365days|last7days|last30days|SOLD|sold)", txt):
    i = m.group(1)
    ctx = re.sub(r"\s+", " ", txt[max(0, m.start() - 150):m.start() + 200])
    print("  [%s] …%s…" % (i, ctx[:250]))
    break
print("\n--- scope / 基础 URL ---")
for m in re.finditer(r"(api_scope[\w./]*)", txt):
    print("  scope 片段: %s" % m.group(1))
    break
for m in re.finditer(r"https://api\.ebay\.com/[A-Za-z0-9_/\-]+", txt):
    print("  URL: %s" % m.group(0))
    break

# ---------- 2. GitHub 上 Terapeak/已售出 仓库 ----------
print()
print("=" * 96)
print("二、GitHub 上 Terapeak / 已售出 相关仓库的说明")
print("=" * 96)
for repo in ["GeniusSecret1117/eBay-Sold-Items-Statistics-Scraper",
             "cmozzocchi/ebay_historicals",
             "bricre/ebay-sdk-buy-marketplace-insights"]:
    r = requests.get("%s/repos/%s" % (API, repo), headers=H, timeout=45)
    if r.status_code != 200:
        print("\n  %s → HTTP %s" % (repo, r.status_code))
        continue
    j = r.json()
    print("\n  【%s】★%s ｜ 更新 %s" % (repo, j["stargazers_count"], j["updated_at"][:10]))
    print("     %s" % (j.get("description") or "-"))
    rd = requests.get("%s/repos/%s/readme" % (API, repo), headers=H, timeout=60)
    if rd.status_code == 200:
        t = base64.b64decode(rd.json()["content"]).decode("utf-8", "replace")
        for kw in ["marketplace", "insight", "terapeak", "sold", "api"]:
            i = t.lower().find(kw)
            if i >= 0:
                print("     [%s] %s" % (kw, re.sub(r"\s+", " ", t[max(0, i - 100):i + 220])[:280]))
    time.sleep(1)
