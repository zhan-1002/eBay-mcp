# -*- coding: utf-8 -*-
"""GitHub 上"eBay 销量/已售出"相关项目普查。

每个项目记录：★ / fork / 最后改代码时间(pushed_at) / 语言 / 许可证
—— 这才是判断"能不能用"的关键，而不是 updated_at（有 star 就刷新，会骗人）。
"""
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"

QUERIES = [
    "ebay sold items",
    "ebay sold scraper",
    "ebay sales data",
    "ebay terapeak",
    "ebay marketplace insights",
    "ebay product research",
    "ebay sales analysis",
    "ebay sold history",
]

seen = {}
for q in QUERIES:
    try:
        r = requests.get("%s/search/repositories" % API,
                         params={"q": q, "sort": "stars", "per_page": 12},
                         headers=H, timeout=45)
        if r.status_code != 200:
            print("  【%s】HTTP %s %s" % (q, r.status_code, r.text[:70]))
            time.sleep(8)
            continue
        data = r.json()
        print("  【%-26s】共 %-5s 个" % (q, data.get("total_count")))
        for it in data.get("items") or []:
            seen[it["full_name"]] = it
    except Exception as exc:
        print("  【%s】异常 %s" % (q, str(exc)[:60]))
    time.sleep(7)

print()
print("=" * 132)
print("去重后共 %d 个仓库，按 ★ 排序" % len(seen))
print("=" * 132)
print("%-52s %5s %5s %-12s %-12s %-10s" % ("仓库", "★", "fork", "最后改代码", "创建", "语言"))
print("-" * 132)
rows = sorted(seen.values(), key=lambda x: -x["stargazers_count"])
for it in rows:
    lic = ((it.get("license") or {}).get("spdx_id")) or "-"
    print("%-52s %5s %5s %-12s %-12s %-10s"
          % (it["full_name"][:52], it["stargazers_count"], it["forks_count"],
             it["pushed_at"][:10], it["created_at"][:10],
             (it.get("language") or "-")[:10]))

print()
print("=" * 132)
print("描述里带销量/已售出关键词的（值得细看的）")
print("=" * 132)
KEY = ("sold", "sales", "terapeak", "insight", "sold count", "sell-through")
for it in rows:
    d = (it.get("description") or "").lower()
    if any(k in d for k in KEY):
        print("\n  【%s】★%s ｜ fork %s ｜ 最后改代码 %s ｜ 许可 %s"
              % (it["full_name"], it["stargazers_count"], it["forks_count"],
                 it["pushed_at"][:10],
                 ((it.get("license") or {}).get("spdx_id")) or "无"))
        print("     %s" % (it.get("description") or "")[:150])
