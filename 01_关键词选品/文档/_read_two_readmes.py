# -*- coding: utf-8 -*-
"""用 raw 通道读这两份 README（不占 GitHub API 限额）。"""
import io
import re

import requests

H = {"User-Agent": "Mozilla/5.0"}
TARGETS = [
    ("colindaniels/eBay-sold-items-documentation",
     "https://raw.githubusercontent.com/colindaniels/eBay-sold-items-documentation/main/README.md"),
    ("Jason-Vaughan/openclaw-ebay-research",
     "https://raw.githubusercontent.com/Jason-Vaughan/openclaw-ebay-research/master/README.md"),
]

for repo, url in TARGETS:
    r = requests.get(url, headers=H, timeout=60)
    print("#" * 124)
    print("# %s  （HTTP %s，%d 字节）" % (repo, r.status_code, len(r.content)))
    print("#" * 124)
    if r.status_code != 200:
        continue
    t = r.text
    io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\%s.md"
            % repo.split("/")[-1], "w", encoding="utf-8").write(t)
    print(t[:4600])
    print()
    print("-" * 124)
    print("关键词命中：")
    for kw in ["marketplace_insights", "item_sales", "sell/research", "product_insight",
               "client_credentials", "api_scope", "terapeak", "sold", "apify",
               "unofficial", "private", "graphql", "endpoint", "token"]:
        n = len(re.findall(re.escape(kw), t, re.I))
        if n:
            m = re.search(r"[^\n]{0,120}%s[^\n]{0,160}" % re.escape(kw), t, re.I)
            print("  %-22s %2d 次 ｜ %s" % (kw, n, re.sub(r"\s+", " ", m.group(0))[:190]))
    print()
