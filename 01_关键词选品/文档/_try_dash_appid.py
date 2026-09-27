# -*- coding: utf-8 -*-
"""App ID 带前导 "-" 的变体测试（临时诊断脚本）。

用户确认：后台显示的 App ID 就是 "-" 开头，即完整值 = -BETA-PRD-f82b86fbd-f4f4c153
"""
import requests

CANDIDATES = [
    ("带前导 -", "-BETA-PRD-f82b86fbd-f4f4c153", "PRD-examplecert000-0000-0000-0000-0000"),
    ("带前导 - / Cert 去 PRD-", "-BETA-PRD-f82b86fbd-f4f4c153",
     "examplecert000-0000-0000-0000-0000"),
    ("带前导 - / 小写 AppID", "-beta-prd-f82b86fbd-f4f4c153",
     "PRD-examplecert000-0000-0000-0000-0000"),
    ("不带前导 - (再确认一次)", "BETA-PRD-f82b86fbd-f4f4c153",
     "PRD-examplecert000-0000-0000-0000-0000"),
]

ROOT = "https://api.ebay.com"
SCOPE = "https://api.ebay.com/oauth/api_scope"

for name, cid, sec in CANDIDATES:
    try:
        r = requests.post(ROOT + "/identity/v1/oauth2/token", auth=(cid, sec),
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data={"grant_type": "client_credentials", "scope": SCOPE},
                          timeout=30)
    except Exception as exc:
        print("%-26s → 异常 %s" % (name, exc))
        continue
    if r.status_code == 200:
        d = r.json()
        print("%-26s → ✅ HTTP 200 换到 app token（长度 %d, expires_in %s）"
              % (name, len(d["access_token"]), d.get("expires_in")))
        print("   App ID 长度 = %d" % len(cid))
        print("   请把这一行告诉我：%s" % name)
        break
    print("%-26s → HTTP %s %s" % (name, r.status_code,
                                  r.text[:110].replace("\n", " ")))
else:
    print("-" * 70)
    print("全部失败。App ID 长度已试 %s"
          % ", ".join("%d" % len(c) for _, c, _ in CANDIDATES))
