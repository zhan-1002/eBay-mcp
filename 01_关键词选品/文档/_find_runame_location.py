# -*- coding: utf-8 -*-
"""找 RuName 的确切位置：官方文档（可能 403）+ 第三方实操指南（GitHub raw，可抓）。"""
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.8",
     "Accept-Language": "en-US,en;q=0.9"}

TARGETS = [
    ("官方：Getting your redirect_uri value",
     "https://developer.ebay.com/api-docs/static/oauth-redirect-uri.html"),
    ("第三方指南 ebay-mcp CONFIGURATION.md",
     "https://raw.githubusercontent.com/YosefHayim/ebay-mcp/main/docs/auth/CONFIGURATION.md"),
    ("第三方指南 ebay-mcp OAUTH_QUICK_REFERENCE.md",
     "https://raw.githubusercontent.com/YosefHayim/ebay-mcp/main/docs/auth/OAUTH_QUICK_REFERENCE.md"),
]

for label, url in TARGETS:
    print("=" * 112)
    print("%s\n%s" % (label, url))
    print("=" * 112)
    try:
        r = requests.get(url, headers=H, timeout=45)
        print("HTTP %s ｜ %d 字节" % (r.status_code, len(r.content)))
        if r.status_code != 200:
            print("  （抓不到，可能是反爬或路径变了）\n")
            continue
        t = r.text
        if "<html" in t[:300].lower():
            t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
            t = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", t)
            t = re.sub(r"(?s)<[^>]+>", " ", t)
            t = re.sub(r"&nbsp;", " ", t)
        t = re.sub(r"[ \t]+", " ", t)
        # 找 RuName 相关段落
        n = 0
        for m in re.finditer(r"RuName|redirect_uri|Redirect URL|auth accepted",
                             t, re.I):
            s = max(0, m.start() - 260)
            frag = re.sub(r"\s+", " ", t[s:m.start() + 340]).strip()
            print("  …%s…" % frag[:520])
            n += 1
            if n >= 8:
                break
        if n == 0:
            print("  （正文里没找到 RuName 相关段落）")
        print()
    except Exception as exc:
        print("  异常 %s\n" % str(exc)[:110])
