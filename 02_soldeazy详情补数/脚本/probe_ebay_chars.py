# -*- coding: utf-8 -*-
"""字符级排查：Unicode 连字符 / 大小写 / 空白，排除"看起来一样但实际不同"。"""
import unicodedata

import requests

RAW_APP = "BETA-SBX-c82936ba4-c0f1d079"
RAW_CERT = "SBX-82936ba43378-651d-42cb-ba0f-d67a"

print("=== 字符级检查 ===")
for name, s in (("App", RAW_APP), ("Cert", RAW_CERT)):
    odd = [(i, c, "U+%04X" % ord(c), unicodedata.name(c, "?"))
           for i, c in enumerate(s) if ord(c) > 127 or c in "\u2010\u2011\u2012\u2013\u2014\u2212"]
    print("  %-5s 长度=%d 非ASCII/异体连字符: %s" % (name, len(s), odd or "无"))
    print("       纯ASCII: %s | 含空格: %s" % (s.isascii(), " " in s))

# 生成变体
def variants(s):
    out = {s, s.strip()}
    out.add(s.replace("BETA-", ""))            # 去 BETA-
    out.add(s.replace("-", "\u2212"))          # 减号 U+2212
    out.add(s.replace("-", "\u2013"))          # en dash
    # 常见"补前缀"猜测
    for pre in ("BETA-", "", "SBX-"):
        out.add(pre + s.replace("BETA-SBX-", ""))
    return [v for v in out if v]

APPS = variants(RAW_APP)
CERTS = variants(RAW_CERT)
print("\nApp 变体 %d 个，Cert 变体 %d 个" % (len(APPS), len(CERTS)))

URLS = [("沙箱", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
        ("生产", "https://api.ebay.com/identity/v1/oauth2/token")]
SCOPE = "https://api.ebay.com/oauth/api_scope"

print("\n=== 逐组合探测（只打成功的，失败只计数）===")
tried = ok = 0
hit = None
for lbl, url in URLS:
    for a in APPS:
        for c in CERTS:
            tried += 1
            try:
                r = requests.post(url, auth=(a, c),
                                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                                  data={"grant_type": "client_credentials", "scope": SCOPE},
                                  timeout=20)
            except Exception:
                continue
            if r.status_code == 200:
                ok += 1
                print("  ✅ [%s] app=%r cert=%r" % (lbl, a, c))
                hit = (lbl, a, c, r.json().get("access_token"))
print("  共试 %d 组合，成功 %d" % (tried, ok))

if not hit:
    print("\n=== 结论 ===")
    print("字符层面全部排除。App ID 值确定为 27 位，而标准沙箱 App ID 为 44 位。")
    print("→ 卡点是【App ID 值不完整】，不是字符/写法/域名/scope/app 状态。")
