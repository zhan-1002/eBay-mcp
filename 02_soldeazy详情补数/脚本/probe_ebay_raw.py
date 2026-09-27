# -*- coding: utf-8 -*-
"""用给定凭据的原始值直接测，并打印 Authorization 头长度与响应原文。"""
import base64

import requests

# 完全按用户给定值，不做任何加工
APP = "BETA-SBX-c82936ba4-c0f1d079"
CERT = "SBX-82936ba43378-651d-42cb-ba0f-d67a"

print("APP  = %r (len=%d)" % (APP, len(APP)))
print("CERT = %r (len=%d)" % (CERT, len(CERT)))
print()

BASIC = base64.b64encode(("%s:%s" % (APP, CERT)).encode()).decode()
print("Basic 头值长度: %d" % len(BASIC))
print()

TRIES = [
    ("沙箱 identity", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
    ("生产 identity", "https://api.ebay.com/identity/v1/oauth2/token"),
]

for label, url in TRIES:
    hdrs = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Basic " + BASIC,
        "Accept": "application/json",
    }
    body = {"grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"}
    print("=== %s ===" % label)
    print("  POST %s" % url)
    print("  Authorization: Basic <len=%d>" % len(BASIC))
    try:
        r = requests.post(url, headers=hdrs, data=body, timeout=25)
        print("  → HTTP %s" % r.status_code)
        print("  → headers: %s" % dict(list(r.headers.items())[:6]))
        print("  → body: %s" % r.text[:400])
    except Exception as exc:
        print("  → 异常: %s" % str(exc)[:200])
    print()
