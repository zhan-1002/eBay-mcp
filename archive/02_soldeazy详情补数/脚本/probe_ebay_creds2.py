# -*- coding: utf-8 -*-
"""按后台截图纠正后重测：App ID(client_id) + Cert ID(client_secret)，Dev ID 不参与。"""
import itertools
import json
import os
import time

import requests

APP_ID = "BETA-SBX-c82936ba4-c0f1d079"
DEV_ID = "16880a0b-a69a-4ac8-91fd-93986bb62f8a"          # 不参与认证
CERT_GIVEN = "SBX-82936ba43378-651d-42cb-ba0f-d67a"      # 用户给的第三段（疑似被截断）

URLS = [
    ("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
    ("生产", "https://api.ebay.com/identity/v1/oauth2/token"),
]
SCOPE = "https://api.ebay.com/oauth/api_scope"

# App ID 可能带前缀（截图里前面被裁掉了），试着补几种常见前缀
APP_VARIANTS = [
    APP_ID,
    "SBX-c82936ba4-c0f1d079",
    "BETA-SBX-c82936ba4-c0f1d079",
]
CERT_VARIANTS = [CERT_GIVEN]

print("App ID 候选: %s" % APP_VARIANTS)
print("Cert ID 候选: %s（长度 %d，沙箱标准应为 38 位）" % (CERT_VARIANTS, len(CERT_GIVEN)))
print("Dev ID: %s（不用于换 token）\n" % DEV_ID)

ok = None
for lbl, url in URLS:
    for app in APP_VARIANTS:
        for cert in CERT_VARIANTS:
            try:
                r = requests.post(url, auth=(app, cert),
                                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                                  data={"grant_type": "client_credentials", "scope": SCOPE},
                                  timeout=25)
            except Exception as exc:
                print("  [%s] %s -> 异常 %s" % (lbl, app[:30], str(exc)[:70]))
                continue
            if r.status_code == 200:
                j = r.json()
                print("  ✅ [%s] app=%s cert=%s -> HTTP 200" % (lbl, app, cert[:20]))
                print("     token 长度 %d，有效期 %s 秒" % (len(j.get("access_token") or ""),
                                                       j.get("expires_in")))
                ok = (lbl, url, app, cert, j.get("access_token"))
            else:
                print("  ✗ [%s] app=%-30s -> HTTP %s %s"
                      % (lbl, app, r.status_code, r.text[:80].replace("\n", " ")))

print()
if ok:
    lbl, url, app, cert, tok = ok
    CFG = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\config.local.json"
    data = json.load(open(CFG, encoding="utf-8"))
    data["ebay_api"] = {"client_id": app, "client_secret": cert, "env": lbl.lower(),
                        "note": "Dev ID 不参与认证，见后台截图"}
    with open(CFG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已写回 config.local.json（env=%s）" % lbl)
    # 立刻验证一个只读接口
    hdrs = {"Authorization": "Bearer " + tok,
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Accept": "application/json"}
    base = "https://api.sandbox.ebay.com" if lbl == "沙箱" else "https://api.ebay.com"
    r2 = requests.get(base + "/buy/browse/v1/item_summary/search",
                      headers=hdrs, params={"q": "earbuds", "limit": 2}, timeout=30)
    print("搜索探测: HTTP %s | %s" % (r2.status_code, r2.text[:200]))
else:
    print("仍未通过。最可能是 Cert ID 被截断 —— 需要在后台点『眼睛』图标看完整值。")
    print("参考：你贴的第三段长度 %d" % len(CERT_GIVEN))
