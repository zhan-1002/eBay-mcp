# -*- coding: utf-8 -*-
"""完整拉取本应用在 eBay 侧的额度表，重点找 Product Research / 销量相关 API。

/developer/analytics/v1_beta/rate_limit/ 返回的是**本应用被授予的 API 及其额度**，
所以这张表本身就是一份"我们能用哪些 API"的权威清单 —— 比猜路径可靠得多。
"""
import io
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
URL = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/"
r = requests.get(URL, headers={"Authorization": "Bearer " + tok,
                               "Accept": "application/json"}, timeout=45)
print("HTTP %s" % r.status_code)
data = r.json()
io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\rate_limits.json", "w",
        encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))

rows = []
for blk in data.get("rateLimits") or []:
    for res in blk.get("resources") or []:
        for rate in res.get("rates") or []:
            rows.append({
                "api": "%s / %s %s" % ((blk.get("apiContext") or "").strip(),
                                       blk.get("apiName"), blk.get("apiVersion")),
                "resource": res.get("name"),
                "limit": rate.get("limit"),
                "used": rate.get("count"),
                "remaining": rate.get("remaining"),
                "window_s": rate.get("timeWindow"),
                "reset": (rate.get("reset") or "")[:19],
            })

print("共 %d 条额度记录\n" % len(rows))
print("%-42s %-38s %8s %6s %10s %8s" % ("API", "资源", "上限", "已用", "剩余", "窗口"))
print("-" * 118)
for x in sorted(rows, key=lambda y: (y["api"], y["resource"] or "")):
    win = "%dh" % (x["window_s"] // 3600) if x["window_s"] else "-"
    print("%-42s %-38s %8s %6s %10s %8s"
          % (x["api"][:42], (x["resource"] or "")[:38], x["limit"], x["used"],
             x["remaining"], win))

print()
print("=" * 118)
print("★ 与「搜索 / 研究 / 销量」相关的资源")
print("=" * 118)
KEY = ("search", "research", "insight", "browse", "sale", "sold", "product")
for x in rows:
    blob = ("%s %s" % (x["api"], x["resource"])).lower()
    if any(k in blob for k in KEY):
        print("  · %-40s %-40s 上限 %s ｜ 已用 %s ｜ 重置 %s"
              % (x["api"][:40], (x["resource"] or "")[:40], x["limit"], x["used"],
                 x["reset"]))

print()
print("重置时间（最早的一条）: %s" % min((x["reset"] for x in rows if x["reset"]),
                                       default="-"))
print("原始 JSON 已存: rate_limits.json")
