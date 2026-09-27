# -*- coding: utf-8 -*-
"""密钥对变体矩阵：判断是"值写错"还是"密钥集本身没生效"（临时诊断脚本）。"""
import base64

import requests

CID = "BETA-PRD-f82b86fbd-f4f4c153"
SEC = "PRD-examplecert000-0000-0000-0000-0000"
SCOPE = "https://api.ebay.com/oauth/api_scope"

variants = [
    ("原样", "https://api.ebay.com", CID, SEC, SCOPE),
    ("Cert 去掉 PRD- 前缀", "https://api.ebay.com", CID, SEC[4:], SCOPE),
    ("App ID 大写、Cert 小写", "https://api.ebay.com", CID.upper(), SEC.lower(), SCOPE),
    ("不带 scope", "https://api.ebay.com", CID, SEC, None),
    ("沙箱根 + 生产密钥", "https://api.sandbox.ebay.com", CID, SEC, SCOPE),
]

for name, root, cid, sec, scope in variants:
    data = {"grant_type": "client_credentials"}
    if scope:
        data["scope"] = scope
    try:
        r = requests.post(root + "/identity/v1/oauth2/token", auth=(cid, sec),
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data=data, timeout=30)
    except Exception as exc:
        print("%-24s → 异常 %s" % (name, exc))
        continue
    ok = "✅ 成功" if r.status_code == 200 else r.text[:110].replace("\n", " ")
    print("%-24s → HTTP %s  %s" % (name, r.status_code, ok))

print("-" * 72)
print("Basic 头长度核对（base64(cid:sec)）：",
      len(base64.b64encode(("%s:%s" % (CID, SEC)).encode())))
print("说明：invariant 的 invalid_client 有两种可能 ——")
print("  a) App ID / Cert ID 值不对（含截图里左侧被截断的可能）")
print("  b) 值是对的，但这个密钥集在 eBay 侧没生效（未启用/未通过合规校验）")
print("两者返回的报文完全一样，只能靠你后台页面确认 b。")
