# -*- coding: utf-8 -*-
"""穷举可能的凭据形态，一次测完（只换 token）。

用户给的三段即完整：
  A1 = BETA-SBX-c82936ba4-c0f1d079            (App ID)
  A2 = 16880a0b-a69a-4ac8-91fd-93986bb62f8a   (Dev ID，后台明确不参与认证)
  A3 = SBX-82936ba43378-651d-42cb-ba0f-d67a   (Cert ID)
"""
import requests

APP = "BETA-SBX-c82936ba4-c0f1d079"
DEV = "16880a0b-a69a-4ac8-91fd-93986bb62f8a"
CERT = "SBX-82936ba43378-651d-42cb-ba0f-d67a"
CERT_NO_PREFIX = CERT[4:]                      # 去掉 SBX-
APP_NO_BETA = APP.replace("BETA-", "", 1)      # SBX-...

URLS = [
    ("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
    ("生产", "https://api.ebay.com/identity/v1/oauth2/token"),
]
SCOPES = {
    "默认": "https://api.ebay.com/oauth/api_scope",
    "空": "",
}

combos = []
for app in [APP, APP_NO_BETA]:
    for cert in [CERT, CERT_NO_PREFIX]:
        combos.append((app, cert))

print("待测组合 %d 个 × %d 域名\n" % (len(combos), len(URLS)))
hit = None
for lbl, url in URLS:
    for app, cert in combos:
        for slbl, scope in SCOPES.items():
            data = {"grant_type": "client_credentials"}
            if scope:
                data["scope"] = scope
            try:
                r = requests.post(url, auth=(app, cert),
                                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                                  data=data, timeout=25)
            except Exception as exc:
                print("  [%s] 异常 %s" % (lbl, str(exc)[:80]))
                continue
            tag = "%s app=%-28s cert=%-32s scope=%s" % (lbl, app[:28], cert[:32], slbl)
            if r.status_code == 200:
                j = r.json()
                print("  ✅ %s -> 200, token %d 位" % (tag, len(j.get("access_token") or "")))
                hit = (lbl, url, app, cert, j.get("access_token"))
            else:
                print("  ✗ %s -> %s %s" % (tag, r.status_code,
                                          r.text[:70].replace("\n", " ")))

print()
if hit:
    print("可用: %s" % (hit[0],))
else:
    print("穷举 %d 种形态全部 401。" % (len(combos) * len(URLS) * len(SCOPES)))
    print()
    print("结论：这三段值无法通过 client_credentials 认证。可能原因：")
    print("  1) Cert ID 复制时缺字符（后台是打码态，眼睛图标看到的才是全值）")
    print("  2) 该 BETA app 尚未激活 / 未授予 api_scope（右下角 OAuth Scopes 可查）")
    print("  3) BETA 版 app 的凭据需用新的端点或凭据体系（非经典身份 API）")
    print()
    print("互通性论证：Auth'n'Auth / 后台生成的 User Token 属于另一条路径，")
    print("与 client_credentials 用的是同一套 App ID + Cert ID —— 所以 Cert ID 若是全值，")
    print("两种路径都应能通；两种都不通则基本可判定 Cert ID 值不完整。")
