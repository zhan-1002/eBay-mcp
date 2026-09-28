# -*- coding: utf-8 -*-
"""两种换 token 写法 × 两个域名，排除"写法"因素。"""
import requests

APP = "BETA-SBX-c82936ba4-c0f1d079"
CERT = "SBX-82936ba43378-651d-42cb-ba0f-d67a"
SCOPE = "https://api.ebay.com/oauth/api_scope"

TARGETS = [
    ("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
    ("生产", "https://api.ebay.com/identity/v1/oauth2/token"),
]

print("App ID  : %s  (长度 %d)" % (APP, len(APP)))
print("Cert ID : %s  (长度 %d)" % (CERT, len(CERT)))
print()

def show(tag, r):
    print("  %-46s -> HTTP %s" % (tag, r.status_code))
    if r.status_code == 200:
        j = r.json()
        print("      ✅ token 长度 %d, expires_in %s" % (len(j.get("access_token") or ""),
                                                     j.get("expires_in")))
        return True
    print("      %s" % r.text[:160].replace("\n", " "))
    return False

hit = False
for lbl, url in TARGETS:
    print("=== %s ===" % lbl)
    # 写法 1：HTTP Basic Auth
    try:
        r = requests.post(url, auth=(APP, CERT),
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data={"grant_type": "client_credentials", "scope": SCOPE},
                          timeout=25)
        hit |= show("Basic Auth", r)
    except Exception as exc:
        print("  Basic Auth 异常: %s" % str(exc)[:90])
    # 写法 2：body 传 client_id / client_secret
    try:
        r = requests.post(url,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data={"grant_type": "client_credentials", "scope": SCOPE,
                                "client_id": APP, "client_secret": CERT},
                          timeout=25)
        hit |= show("body 传参", r)
    except Exception as exc:
        print("  body 传参 异常: %s" % str(exc)[:90])
    print()

print("=" * 70)
if hit:
    print("至少一种写法可用。")
else:
    print("两种写法 × 两个域名 全部失败 → 排除写法因素。")
    print()
    print("剩下的可能性（按概率）：")
    print("  1) App ID 值不完整 —— 截图里该行行首有 '−'，说明左边内容被裁掉了")
    print("  2) 这个 BETA app 尚未生效（新注册 app 需审核/激活后才能换 token）")
    print("  3) 该 app 未授予任何 API scope（后台 OAuth Scopes 页可确认）")
