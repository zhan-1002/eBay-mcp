# -*- coding: utf-8 -*-
"""列出 hendt/ebay-api 里内嵌的 eBay OAS3 规格清单 —— 等于一份完整 API 枚举。
如果连它都没有 research/product-insight 的规格，基本可以确认"无公开定义"。
"""
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"

for path in ["/repos/hendt/ebay-api/contents/src/types/restful/specs",
             "/repos/hendt/ebay-api/contents/src/types/restful"]:
    r = requests.get(API + path, headers=H, timeout=45)
    print("=" * 96)
    print("%s → HTTP %s" % (path, r.status_code))
    print("=" * 96)
    if r.status_code != 200:
        print("  %s" % r.text[:200])
        continue
    items = r.json()
    names = sorted(x["name"] for x in items)
    print("  共 %d 项：" % len(names))
    for n in names:
        flag = ""
        if any(k in n.lower() for k in ("research", "insight", "analytic",
                                        "report", "feedback", "reputation")):
            flag = "   ★"
        print("    %s%s" % (n, flag))
    time.sleep(1)

# 仓库元信息：看最后更新时间与规模
r = requests.get(API + "/repos/hendt/ebay-api", headers=H, timeout=45)
if r.status_code == 200:
    d = r.json()
    print()
    print("仓库: %s ｜ ★%s ｜ 更新 %s ｜ 说明: %s"
          % (d["full_name"], d["stargazers_count"], d["updated_at"][:10],
             (d.get("description") or "")[:80]))
