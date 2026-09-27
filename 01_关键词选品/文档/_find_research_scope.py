# -*- coding: utf-8 -*-
"""找 research / product_insight 对应的 OAuth scope（查第三方整理的 scope 清单）。"""
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.8"}

URLS = [
    ("Cleo 整理的 eBay OAuth Scopes",
     "https://support.cleo.com/hc/en-us/articles/39571742942871-OAuth-Scopes-eBay"),
    ("ebay-mcp 的 OAuth 速查（GitHub 原文）",
     "https://raw.githubusercontent.com/YosefHayim/ebay-mcp/main/docs/auth/OAUTH_QUICK_REFERENCE.md"),
    ("ebay-mcp 仓库的 API 覆盖说明",
     "https://raw.githubusercontent.com/YosefHayim/ebay-mcp/main/README.md"),
]

for label, url in URLS:
    print("=" * 96)
    print("%s\n%s" % (label, url))
    print("=" * 96)
    try:
        r = requests.get(url, headers=H, timeout=45)
        print("HTTP %s ｜ %d 字节" % (r.status_code, len(r.content)))
        if r.status_code != 200:
            print()
            continue
        t = r.text
        if "<" in t[:200] and "html" in t[:400].lower():
            t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
            t = re.sub(r"(?s)<[^>]+>", " ", t)
            t = re.sub(r"&nbsp;", " ", t)
        t = re.sub(r"[ \t]+", " ", t)
        # 找研究/洞察相关行
        lines = [x.strip() for x in t.splitlines() if x.strip()]
        hits = [x for x in lines
                if re.search(r"research|insight|analytics|scope", x, re.I)]
        print("命中 %d 行；先看含 research/insight 的：" % len(hits))
        n = 0
        for x in lines:
            if re.search(r"research|insight", x, re.I):
                print("   %s" % x[:220])
                n += 1
                if n >= 12:
                    break
        if n == 0:
            print("   （没有 research/insight 相关的行）")
            print("   含 scope 的样例：")
            for x in hits[:8]:
                print("     %s" % x[:200])
    except Exception as exc:
        print("异常 %s" % str(exc)[:120])
    print()
