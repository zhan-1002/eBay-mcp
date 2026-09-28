# -*- coding: utf-8 -*-
"""用生产 App ID（BETA-PRD-...）试 client_credentials。"""
import base64

import requests

CANDIDATES = [
    ("生产 App ID（截图）", "BETA-PRD-f82b86fbf-f4f4c153"),
    ("沙箱 App ID（截图）", "BETA-SBX-c82936ba4-c0f1d079"),
]
CERT = "SBX-82936ba43378-651d-42cb-ba0f-d67a"
SCOPE = "https://api.ebay.com/oauth/api_scope"

TARGETS = [("生产", "https://api.ebay.com/identity/v1/oauth2/token"),
           ("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token")]

print("Cert ID: %s (len=%d)\n" % (CERT, len(CERT)))
for alabel, app in CANDIDATES:
    print("=== %s : %s (len=%d) ===" % (alabel, app, len(app)))
    for lbl, url in TARGETS:
        try:
            r = requests.post(url, auth=(app, CERT),
                              headers={"Content-Type": "application/x-www-form-urlencoded"},
                              data={"grant_type": "client_credentials", "scope": SCOPE}, timeout=25)
        except Exception as exc:
            print("   [%s] 异常 %s" % (lbl, str(exc)[:80]))
            continue
        if r.status_code == 200:
            j = r.json()
            print("   ✅ [%s] HTTP 200 | token 长度 %d | expires_in %s"
                  % (lbl, len(j.get("access_token") or ""), j.get("expires_in")))
            import json
            import os
            CFG = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\config.local.json"
            d = json.load(open(CFG, encoding="utf-8"))
            d["ebay_api"] = {"client_id": app, "client_secret": CERT, "env": lbl}
            with open(CFG, "w", encoding="utf-8", newline="\n") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            print("      已写回 config.local.json")
        else:
            print("   ✗ [%s] HTTP %s %s" % (lbl, r.status_code, r.text[:110].replace("\n", " ")))
    print()
