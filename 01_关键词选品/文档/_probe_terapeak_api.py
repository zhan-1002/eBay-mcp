# -*- coding: utf-8 -*-
"""两件事：
  1. 从 2021 那份《Terapeak API》PDF 里挖明文线索（元数据/URL/ASCII 串）
     —— 正文是 CID 编码，我的粗暴提取解不出中文，但元数据往往有明文
  2. 探一下 eBay 有没有 Terapeak/Research 相关的接口路径与 scope
     （404 不消耗额度；目的是确认"Terapeak API 现在是否还是独立接口"）
"""
import re
import sys

import requests

PDF = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_api.pdf"

# ---------- 1. PDF 明文线索 ----------
print("=" * 90)
print("一、2021《Terapeak API》PDF 里的明文线索")
print("=" * 90)
try:
    raw = open(PDF, "rb").read()
    print("文件大小 %d 字节" % len(raw))
    # 可读 ASCII 串
    strings = re.findall(rb"[ -~]{6,}", raw)
    interesting = []
    for s in strings:
        t = s.decode("latin-1")
        low = t.lower()
        if any(k in low for k in ("terapeak", "http", "api", "ebay", "scope",
                                  "endpoint", "research", "erp", "oauth", "title")):
            if len(t) < 300:
                interesting.append(t)
    seen, uniq = set(), []
    for t in interesting:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    print("含关键词的明文串 %d 条，前 40 条：" % len(uniq))
    for t in uniq[:40]:
        print("   %s" % t[:150])
    # XMP / Info 元数据
    for m in re.finditer(rb"<(xmp:)?(Title|Creator|Author|Description)>([^<]{3,200})<",
                         raw):
        print("   元数据 %s = %s" % (m.group(2).decode(), m.group(3).decode("utf-8", "ignore")))
    for m in re.finditer(rb"/(Title|Author|Subject|Keywords)\s*\(([^)]{3,200})\)", raw):
        print("   Info %s = %s" % (m.group(1).decode(), m.group(2).decode("utf-8", "ignore")))
except Exception as exc:
    print("异常 %s" % exc)

# ---------- 2. 探路径 / scope ----------
sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

auth = ebay_auth.EbayAuth(verbose=False)
tok = auth.token()
H = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
API = "https://api.ebay.com"

print()
print("=" * 90)
print("二、scope 探测：有没有 Terapeak / Research 的权限范围")
print("=" * 90)
for scope in ["https://api.ebay.com/oauth/api_scope/sell.research",
              "https://api.ebay.com/oauth/api_scope/sell.terapeak",
              "https://api.ebay.com/oauth/api_scope/commerce.terapeak.readonly",
              "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"]:
    r = requests.post(API + "/identity/v1/oauth2/token",
                      auth=(auth.client_id, auth.client_secret),
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "scope": scope}, timeout=30)
    tag = "✅ 有" if r.status_code == 200 else "🔒 没有"
    print("  %-56s %s" % (scope.split("/oauth/")[-1], tag))

print()
print("=" * 90)
print("三、路径探测：有没有 Terapeak/Research 接口")
print("=" * 90)
for path in ["/commerce/terapeak/v1/research",
             "/sell/research/v1/terapeak",
             "/commerce/research/v1/product_research",
             "/buy/marketplace_insights/v1_beta/item_sales/search"]:
    try:
        r = requests.get(API + path, headers=H,
                         params={"q": "wireless earbuds", "limit": 1}, timeout=30)
        note = r.text[:90].replace("\n", " ") if r.status_code != 200 else "200 OK"
        print("  %-52s HTTP %s %s" % (path, r.status_code, note))
    except Exception as exc:
        print("  %-52s 异常 %s" % (path, str(exc)[:60]))
