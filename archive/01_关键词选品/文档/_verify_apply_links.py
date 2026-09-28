# -*- coding: utf-8 -*-
"""验证申请相关链接是否可达（顺带看是否被重定向到登录页）。"""
import requests

URLS = [
    ("★ 申请表入口（Application Growth Check）",
     "https://developer.ebay.com/grow/application-growth-check"),
    ("流程：用 growth check 拿受限 API 访问权",
     "https://developer.ebay.com/api-docs/static/gs_use-the-application-growth.html"),
    ("怎么发起申请", "https://developer.ebay.com/api-docs/static/gs_request-an-application-growth.html"),
    ("填表说明", "https://developer.ebay.com/api-docs/static/gs_apply-for-the-application.html"),
    ("API Call Limits（你截图那页，切 Buy tab 看销量接口额度）",
     "https://developer.ebay.com/api-docs/static/api-call-limits.html"),
    ("Marketplace Insights 概览（销量接口文档）",
     "https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html"),
    ("开发者后台（登录后从这里找入口）", "https://developer.ebay.com/my/home"),
    ("Application Keys（改 App ID / Cert ID 的地方）", "https://developer.ebay.com/my/keys"),
]

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
for label, url in URLS:
    try:
        r = requests.get(url, headers=H, timeout=30, allow_redirects=True)
        final = r.url if r.url != url else ""
        note = "HTTP %s %s" % (r.status_code, "✅ 可达" if r.status_code < 400 else "❌")
        if final:
            note += " → 重定向到 %s" % final
        if r.status_code < 400 and "login" in r.url.lower():
            note += "（需要先登录）"
    except Exception as exc:
        note = "异常 %s" % str(exc)[:80]
    print("%-52s %s" % (label[:52], note))
