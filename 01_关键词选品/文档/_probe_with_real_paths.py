# -*- coding: utf-8 -*-
"""用 OpenAPI 规格里解析出的**正确 basePath**去探端点。

重点目标：
  1. developer-analytics `/rate_limit/`  → **查 API 额度**（前几轮一直查不到的）
  2. commerce-translation `/translate`    → 多语言标题（我们做 9 个站点）
  3. sell-analytics `/traffic_report`      → 自家流量/转化
  4. sell-finances（注意 host 是 apiz.ebay.com，不是 api.ebay.com）
"""
import io
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

data = json.load(io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\apisguru_list.json",
                         encoding="utf-8"))
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# 解析每个规格的 host + basePath
resolved = {}
for key, v in data.items():
    if "ebay" not in key.lower():
        continue
    pref = v.get("preferred")
    ver = (v.get("versions") or {}).get(pref) or {}
    url = ver.get("swaggerUrl") or ver.get("openapiUrl")
    if not url:
        continue
    try:
        s = requests.get(url, headers=H, timeout=60).json()
    except Exception:
        continue
    srv = (s.get("servers") or [{}])[0]
    tpl = srv.get("url", "")
    base = ((srv.get("variables") or {}).get("basePath") or {}).get("default", "")
    host = tpl.split("{")[0] if "{" in tpl else tpl
    resolved[key.split(":")[-1]] = {
        "title": (ver.get("info") or {}).get("title"),
        "host": host or "https://api.ebay.com",
        "base": base,
        "paths": sorted((s.get("paths") or {}).keys()),
    }

print("=" * 96)
print("已解析的 eBay API（host + basePath）")
print("=" * 96)
for k in sorted(resolved):
    r = resolved[k]
    print("  %-22s %-24s %-34s %s" % (k, r["title"][:22] if r["title"] else "-",
                                      r["host"], r["base"] or "(空)"))

# ---- 正确的探测 ----
tok = ebay_auth.EbayAuth(verbose=False).token()
AUTH = {"Authorization": "Bearer " + tok, "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}

PROBES = [
    ("★ 查 API 额度", "developer-analytics", "/rate_limit/", None),
    ("★ 查用户级额度", "developer-analytics", "/user_rate_limit/", None),
    ("翻译（英→德）", "commerce-translation", "/translate",
     {"from": "en", "to": "de", "text": ["wireless earbuds bluetooth 5.4"]}),
    ("自家流量报表", "sell-analytics", "/traffic_report",
     {"dimension": "DAY", "filter": "marketplace_ids:{EBAY_GB}"}),
    ("自家卖家标准", "sell-analytics", "/seller_standards_profile",
     {"program": "PROGRAM_UK", "cycle": "CURRENT"}),
    ("订单", "sell-fulfillment", "/order", {"limit": 1}),
    ("财务交易", "sell-finances", "/transaction", {"limit": 1}),
    ("账号权限", "sell-account", "/privilege", None),
    ("库存", "sell-inventory", "/inventory_item", {"limit": 1}),
]

print()
print("=" * 96)
print("用正确 basePath 探测")
print("=" * 96)
for label, key, path, payload in PROBES:
    r = resolved.get(key)
    if not r:
        print("  %-22s 规格未解析到，跳过" % label)
        continue
    full = r["host"].rstrip("/") + (r["base"] or "") + path
    try:
        if path == "/translate":
            resp = requests.post(full, headers=AUTH, json=payload, timeout=30)
        else:
            resp = requests.get(full, headers=AUTH, params=payload, timeout=30)
        code = resp.status_code
        if code == 200:
            keys = list(resp.json().keys())[:6]
            note = "✅ 可用 ｜ 字段: %s" % ", ".join(keys)
        elif code in (401, 403):
            try:
                e = (resp.json().get("errors") or [{}])[0]
                note = "🔒 无权限 errorId=%s %s" % (e.get("errorId"),
                                                  (e.get("message") or "")[:50])
            except Exception:
                note = "🔒 无权限"
        elif code == 404:
            note = "❌ 404（路径仍不对）"
        else:
            note = "⚠️ HTTP %s %s" % (code, resp.text[:80].replace("\n", " "))
        print("  %-22s %s" % (label, note))
        print("      %s" % full)
        if code == 200:
            print("      %s" % json.dumps(resp.json(), ensure_ascii=False)[:400])
    except Exception as exc:
        print("  %-22s 异常 %s" % (label, str(exc)[:70]))
