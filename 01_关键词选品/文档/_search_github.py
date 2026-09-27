# -*- coding: utf-8 -*-
"""在 GitHub / 代码搜索 / 包仓库里找 Product Research API 的痕迹。

目标关键词（eBay 未公开接口）：
  sell.research.product_insight   /sell/research/v1
  product_insight                marketplace_insights / item_sales/search
"""
import json
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "application/json, text/plain, */*"}

TERMS = ["sell.research.product_insight", "product_insight", "/sell/research/v1",
         "marketplace_insights", "item_sales/search", "sell.research"]


def grep_app(term):
    """grep.app 的公开代码搜索（无需登录）。"""
    try:
        r = requests.get("https://grep.app/api/search",
                         params={"q": term}, headers=H, timeout=45)
        if r.status_code != 200:
            return "HTTP %s" % r.status_code, []
        d = r.json()
        hits = d.get("hits", {}).get("hits") or []
        out = []
        for h in hits[:8]:
            repo = (h.get("repo") or {}).get("raw") or h.get("repo")
            path = (h.get("path") or {}).get("raw") or h.get("path")
            snip = ""
            content = h.get("content") or {}
            if isinstance(content, dict):
                snip = content.get("snippet") or ""
            snip = re.sub(r"<[^>]+>", "", str(snip)).replace("\n", " ")
            out.append((repo, path, snip[:150]))
        total = (d.get("hits") or {}).get("total")
        return "total=%s" % total, out
    except Exception as exc:
        return "异常 %s" % str(exc)[:70], []


print("=" * 100)
print("一、grep.app 代码搜索")
print("=" * 100)
for t in TERMS:
    status, hits = grep_app(t)
    print("\n【%s】%s" % (t, status))
    for repo, path, snip in hits:
        print("   %s" % repo)
        print("     %s" % path)
        if snip:
            print("     %s" % snip)
    time.sleep(1.5)

print()
print("=" * 100)
print("二、GitHub 仓库搜索")
print("=" * 100)
for q in ["ebay product research api", "ebay marketplace insights",
          "ebay sell research api", "ebay terapeak"]:
    try:
        r = requests.get("https://api.github.com/search/repositories",
                         params={"q": q, "sort": "stars", "per_page": 5},
                         headers=H, timeout=45)
        if r.status_code != 200:
            print("  %-34s HTTP %s %s" % (q, r.status_code, r.text[:80]))
            continue
        items = r.json().get("items") or []
        print("\n  【%s】共 %s 个仓库" % (q, r.json().get("total_count")))
        for it in items[:5]:
            print("     %-58s ★%s" % (it["full_name"][:58], it["stargazers_count"]))
            if it.get("description"):
                print("        %s" % it["description"][:130])
    except Exception as exc:
        print("  %-34s 异常 %s" % (q, str(exc)[:60]))
    time.sleep(2)
