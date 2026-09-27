# -*- coding: utf-8 -*-
"""① 修好 grep.app 的解析；② 多词搜索；③ 拉 Marketplace Insights SDK 的端点定义。
"""
import base64
import json
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "application/json"}


def grep_app(term):
    r = requests.get("https://grep.app/api/search", params={"q": term},
                     headers=H, timeout=45)
    if r.status_code != 200:
        return "HTTP %s" % r.status_code, [], None
    try:
        d = r.json()
    except Exception:
        return "非 JSON", [], r.text[:200]
    hits_node = d.get("hits")
    if isinstance(hits_node, dict):
        arr = hits_node.get("hits") or []
        total = hits_node.get("total")
    elif isinstance(hits_node, list):
        arr = hits_node
        total = d.get("total")
    else:
        arr = []
        total = d.get("total")
    out = []
    for h in arr or []:
        if not isinstance(h, dict):
            continue
        repo = h.get("repo") or {}
        path = h.get("path") or {}
        repo = repo.get("raw") if isinstance(repo, dict) else repo
        path = path.get("raw") if isinstance(path, dict) else path
        content = h.get("content") or {}
        snip = content.get("snippet") if isinstance(content, dict) else str(content)
        snip = re.sub(r"<[^>]+>", "", str(snip)).replace("\n", " ")
        out.append((repo, path, snip[:170]))
    return "total=%s" % total, out, None


print("=" * 100)
print("一、先看 grep.app 原始结构（修解析用）")
print("=" * 100)
r = requests.get("https://grep.app/api/search", params={"q": "product_insight"},
                 headers=H, timeout=45)
print("HTTP %s" % r.status_code)
print(r.text[:600])

print()
print("=" * 100)
print("二、多词代码搜索")
print("=" * 100)
for t in ["product_insight", "productInsight", "sell/research", "sell.research",
          "marketplace_insights", "item_sales/search", "product_research"]:
    status, hits, raw = grep_app(t)
    print("\n【%s】%s%s" % (t, status, ("  raw=" + raw[:120]) if raw else ""))
    for repo, path, snip in hits:
        print("   %s ｜ %s" % (repo, str(path)[:70]))
        if snip:
            print("      %s" % snip)
    time.sleep(1.2)

print()
print("=" * 100)
print("三、Marketplace Insights SDK 里定义的端点（证明该规格存在且内容）")
print("=" * 100)
API = "https://api.github.com"
for path in ["/repos/bricre/ebay-sdk-buy-marketplace-insights/contents/",
             "/repos/bricre/ebay-sdk-php-buy-marketplace-insights/contents/src"]:
    rr = requests.get(API + path, headers=H, timeout=45)
    if rr.status_code != 200:
        print("  %s → HTTP %s" % (path, rr.status_code))
        continue
    print("  %s：" % path)
    for it in rr.json()[:25]:
        print("     %-46s %s" % (it["name"], it.get("type")))
    time.sleep(1)
