# -*- coding: utf-8 -*-
"""细看 GitHub 上最相关的那几个 eBay 销量项目：它们到底怎么拿数据？能不能用？"""
import base64
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"

REPOS = [
    "colindaniels/eBay-sold-items-documentation",
    "bintangtimurlangit/ebay-terapeak-mcp",
    "4areem/ebay-terapeak-scraper",
    "kenryu621/eBay-Terapeak-Scraper",
    "DannyRivasDev/Ebay-Sold-Listings-Scraper",
    "crawloop/eBay-Sold-Listings-Scraper-Completed-Sales-Scraping",
    "618034128/cross-border-product-agent",
    "data-scrape/ebay-price-scraper",
    "ShehrozAttique/Ebay-Scraper",
    "Jason-Vaughan/openclaw-ebay-research",
]

KEYS = ["api_scope", "marketplace_insights", "item_sales", "sell/research",
        "product_insight", "terapeak", "selenium", "playwright", "undetected",
        "cloakbrowser", "cookie", "login", "sh/research", "sold", "watchcount",
        "totalSoldQuantity", "apify", "proxy", "requests.get", "beautifulsoup"]

for repo in REPOS:
    r = requests.get("%s/repos/%s" % (API, repo), headers=H, timeout=45)
    print("=" * 122)
    if r.status_code != 200:
        print("%s → HTTP %s" % (repo, r.status_code))
        continue
    j = r.json()
    lic = ((j.get("license") or {}).get("spdx_id")) or "无"
    print("【%s】★%s fork %s ｜ 最后改代码 %s ｜ 语言 %s ｜ 许可 %s"
          % (repo, j["stargazers_count"], j["forks_count"], j["pushed_at"][:10],
             j.get("language"), lic))
    print("   %s" % (j.get("description") or "-")[:160])

    # README
    rd = requests.get("%s/repos/%s/readme" % (API, repo), headers=H, timeout=60)
    if rd.status_code == 200:
        t = base64.b64decode(rd.json()["content"]).decode("utf-8", "replace")
        hits = {k: len(re.findall(re.escape(k), t, re.I)) for k in KEYS}
        hits = {k: v for k, v in hits.items() if v}
        print("   README %d 字 ｜ 关键词: %s" % (len(t), hits))
        # 摘几句关键说明
        for kw in ["unofficial", "not an ebay", "private endpoint", "login",
                   "cookie", "api", "apify", "scrape", "sold"]:
            m = re.search(r"[^.\n]{0,140}%s[^.\n]{0,160}" % kw, t, re.I)
            if m:
                print("      [%s] %s" % (kw, re.sub(r"\s+", " ", m.group(0))[:230]))
                break
    else:
        print("   （无 README）")
    time.sleep(1.2)
