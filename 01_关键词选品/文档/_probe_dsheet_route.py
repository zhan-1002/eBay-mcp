# -*- coding: utf-8 -*-
"""摸 Soldeazy dsheet_list 路由：参数形态、是否有 JSON 接口、未登录返回什么。"""
import re

import requests

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/151.0.0.0 Safari/537.36"})

BASE = "https://stiger.soldeazy.com"
paths = [
    "/app/soldeazy/datasheet/dsheet_list",
    "/app/soldeazy/datasheet/dsheet_list?default_search_profile",
    "/app/soldeazy/datasheet",
    "/app/soldeazy/",
]
for p in paths:
    try:
        r = s.get(BASE + p, timeout=25, verify=False, allow_redirects=True)
    except Exception as exc:
        print("%-58s 请求失败 %s" % (p, str(exc)[:60]))
        continue
    loc = r.url.replace(BASE, "")
    print("%-58s -> HTTP %s  最终=%s  长度=%d" % (p, r.status_code, loc[:70], len(r.text)))

print("\n=== 从 login 页 HTML 里找已注册的路由 / ajax 端点 ===")
r = s.get(BASE + "/app/soldeazy/login", timeout=25, verify=False)
html = r.text
routes = set()
for m in re.finditer(r"""['"](/app/[A-Za-z0-9_/\-]{3,80})['"]""", html):
    routes.add(m.group(1))
for m in re.finditer(r"""['"](/ssl/[A-Za-z0-9_/\-]{3,80})['"]""", html):
    routes.add(m.group(1))
print("共发现 %d 条路由（前 40）：" % len(routes))
for u in sorted(routes)[:40]:
    print("   %s" % u)

print("\n=== dsheet / datasheet 关键词在 login 页出现情况 ===")
for kw in ("dsheet", "datasheet", "product_code", "search_profile"):
    print("   %-18s %d 次" % (kw, len(re.findall(kw, html, re.I))))
