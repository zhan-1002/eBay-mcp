# -*- coding: utf-8 -*-
"""bricre 专门从 OpenAPI 规格自动生成 SDK —— 枚举它的 eBay 仓库，
看有没有 research / product-insight 相关的规格（有规格 = 接口有公开定义）。
"""
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
GH = "https://api.github.com"


def gh(path, **params):
    r = requests.get(GH + path, headers=H, params=params, timeout=45)
    if r.status_code != 200:
        return None, "HTTP %s %s" % (r.status_code, r.text[:100])
    return r.json(), None


print("=" * 100)
print("一、bricre 名下所有 ebay 仓库（= 它有的 eBay OpenAPI 规格）")
print("=" * 100)
repos, err = gh("/search/repositories",
                q="user:bricre ebay", per_page=100, sort="updated")
if err:
    print("  搜索失败: %s" % err)
    repos = {"items": []}
items = repos.get("items") or []
print("  共 %d 个" % len(items))
interesting = []
for it in sorted(items, key=lambda x: x["name"]):
    name = it["name"]
    print("    %-56s 更新 %s" % (name[:56], (it.get("updated_at") or "")[:10]))
    if re.search(r"research|insight|analytic|report", name, re.I):
        interesting.append(it)
print()
print("  ★ 名字含 research/insight/analytic/report 的：%d 个" % len(interesting))
for it in interesting:
    print("     %s" % it["full_name"])

print()
print("=" * 100)
print("二、Marketplace Insights SDK 的 README（拿官方端点/scope 定义）")
print("=" * 100)
for it in items:
    if "marketplace-insights" in it["name"]:
        rd, e = gh("/repos/%s/readme" % it["full_name"])
        if e:
            print("  %s: %s" % (it["full_name"], e))
            continue
        import base64
        txt = base64.b64decode(rd.get("content") or "").decode("utf-8", "replace")
        print("  【%s】长度 %d" % (it["full_name"], len(txt)))
        print(txt[:1500])
        break

print()
print("=" * 100)
print("三、GitHub 全站搜 bricre 是否有 sell-research 规格（含代码搜索替代）")
print("=" * 100)
for q in ["ebay-sdk-sell-research", "ebay-sdk-sell-analytics",
          "ebay product-insight openapi", "sell.research.product_insight"]:
    res, e = gh("/search/repositories", q=q, per_page=5)
    if e:
        print("  %-38s %s" % (q, e))
    else:
        print("  %-38s 共 %s 个：" % (q, res.get("total_count")))
        for it in (res.get("items") or [])[:5]:
            print("       %s" % it["full_name"])
    time.sleep(2)
