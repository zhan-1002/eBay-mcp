# -*- coding: utf-8 -*-
"""逐组合找出正确的 client_id / client_secret 配对（只换 token，只读）。

沙箱凭据的常见形态：
   App ID(Client ID) : SBX-xxxxxxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  或  BETA-SBX-...
   Cert ID(Secret)   : SBX-xxxxxxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
"""
import itertools
import time

import requests

# 用户给的三段原文
RAW = [
    "BETA-SBX-c82936ba4-c0f1d079",
    "16880a0b-a69a-4ac8-91fd-93986bb62f8a",
    "SBX-82936ba43378-651d-42cb-ba0f-d67a",
]

URLS = [
    ("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
    ("生产", "https://api.ebay.com/identity/v1/oauth2/token"),
]
SCOPES = [
    ("api_scope", "https://api.ebay.com/oauth/api_scope"),
    ("api_scope+buy", "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/buy.item.feed"),
]

print("候选值：")
for i, v in enumerate(RAW, 1):
    print("  %d) %s（长度 %d）" % (i, v, len(v)))

found = []
for (lbl, url) in URLS:
    for cid in RAW:
        for sec in RAW:
            if cid == sec:
                continue
            try:
                r = requests.post(url, auth=(cid, sec),
                                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                                  data={"grant_type": "client_credentials",
                                        "scope": SCOPES[0][1]},
                                  timeout=25)
            except Exception as exc:
                print("  [%s] %s / %s -> 异常 %s" % (lbl, cid[:18], sec[:18], str(exc)[:60]))
                continue
            tag = "%s | id=%s | secret=%s" % (lbl, cid[:26], sec[:26])
            if r.status_code == 200:
                j = r.json()
                print("  ✅ %s -> HTTP 200，token 长度 %d" % (tag, len(j.get("access_token") or "")))
                found.append((lbl, url, cid, sec, j.get("access_token")))
            else:
                msg = r.text[:90].replace("\n", " ")
                print("  ✗ %s -> HTTP %s %s" % (tag, r.status_code, msg))

print()
if found:
    lbl, url, cid, sec, tok = found[0]
    print("可用配对: 环境=%s" % lbl)
    print("  client_id     = %s" % cid)
    print("  client_secret = %s" % sec)
    # 写回 config（仅当与沙箱环境匹配）
    import json
    import os
    CFG = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\config.local.json"
    data = json.load(open(CFG, encoding="utf-8"))
    data["ebay_api"] = {"client_id": cid, "client_secret": sec, "env": lbl.lower()}
    with open(CFG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("  已写回 config.local.json 的 ebay_api（新增 env 字段）")
else:
    print("全部组合都失败 —— 可能密钥本身不匹配、或已失效、或需在新版开发者后台确认格式。")
