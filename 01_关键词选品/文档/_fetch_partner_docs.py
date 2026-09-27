# -*- coding: utf-8 -*-
"""抓三份权威文档，回答三件事：
  1. Terapeak 到底是什么、能看到什么
  2. Buy APIs 的使用要求（含"要不要企业身份 / 伙伴关系"）
  3. eBay Partner Network（EPN）的准入条件
developer.ebay.com 之前被反爬 403，这里如实报告，不假装抓到。
"""
import io
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}

TARGETS = [
    ("Terapeak 官方介绍", "https://export.ebay.com/en/marketing/"
                         "ebay-services-and-tools-help-seller/terapeak/"),
    ("Buy APIs Requirements（关键：使用要求/伙伴门槛）",
     "https://developer.ebay.com/api-docs/buy/buy-requirements.html"),
    ("Marketplace Insights 概览（官方对访问权的说明）",
     "https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html"),
    ("EPN 网络协议（准入条件相关）",
     "https://partnernetwork.ebay.fr/page/network-agreement"),
]


def text_of(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|pre)>", "\n", html)
    t = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'")):
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


KEYS = {
    "Terapeak 官方介绍": ["sold", "sell-through", "365", "free", "research", "average",
                          "Terapeak"],
    "Buy APIs Requirements（关键：使用要求/伙伴门槛）":
        ["partner", "requirement", "business", "approved", "apply", "growth check",
         "restricted", "production"],
    "Marketplace Insights 概览（官方对访问权的说明）":
        ["restricted", "access", "approved", "partner", "requirement", "apply"],
    "EPN 网络协议（准入条件相关）":
        ["eligibility", "apply", "requirement", "website", "traffic", "approved",
         "reject", "terminate"],
}

for label, url in TARGETS:
    print("=" * 96)
    print("%s\n%s" % (label, url))
    print("=" * 96)
    try:
        r = requests.get(url, headers=H, timeout=45)
        if r.status_code != 200:
            print("  HTTP %s —— 抓不到（大概率反爬/需登录）\n" % r.status_code)
            continue
        t = text_of(r.text)
        io.open("wb_%s.txt" % re.sub(r"\W+", "_", label)[:24], "w",
                encoding="utf-8").write(t)
        print("  正文 %d 字" % len(t))
        for k in KEYS[label]:
            hits = 0
            for m in re.finditer(re.escape(k), t, re.I):
                s = max(0, m.start() - 150)
                frag = re.sub(r"\s+", " ", t[s:m.start() + 250]).strip()
                print("   [%s] …%s…" % (k, frag[:300]))
                hits += 1
                if hits >= 2:
                    break
        print()
    except Exception as exc:
        print("  异常 %s\n" % str(exc)[:120])
