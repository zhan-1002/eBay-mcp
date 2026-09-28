# -*- coding: utf-8 -*-
"""探查 eBay 凭据哪条路能自动续期（临时诊断脚本，不打印明文密钥）。

要回答的问题：
  1. 现存的 User Token（token.local.txt）还有效吗？
  2. config 里的 client_id/client_secret 能换到 app token 吗（client_credentials）？
  3. app token 能不能调 Browse API（search + getItem）？—— 能的话就不需要人工贴 token 了
"""
import io
import json
import os
import time

import requests

PROJ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CFG = os.path.join(PROJ, "config.local.json")
TOK = os.path.join(PROJ, "02_soldeazy详情补数", "token.local.txt")

with io.open(CFG, encoding="utf-8") as f:
    api = (json.load(f).get("ebay_api") or {})
CID = (os.environ.get("EBAY_CLIENT_ID") or api.get("client_id") or "").strip()
SEC = (os.environ.get("EBAY_CLIENT_SECRET") or api.get("client_secret") or "").strip()


def mask(v):
    v = str(v or "")
    return "<empty>" if not v else (v[:6] + "..." + v[-4:] if len(v) > 14 else "<set:%d>" % len(v))


print("client_id     =", mask(CID))
print("client_secret =", mask(SEC))
print("=" * 70)

# ---------- 1. 现存 User Token 还有效吗 ----------
tok_file = ""
if os.path.isfile(TOK):
    with io.open(TOK, encoding="utf-8") as f:
        tok_file = f.read().strip()
if tok_file:
    r = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                     headers={"Authorization": "Bearer " + tok_file,
                              "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"},
                     params={"q": "wireless earbuds", "limit": 1}, timeout=30)
    print("[1] token.local.txt 里的 User Token → HTTP %s" % r.status_code)
    if r.status_code != 200:
        print("    %s" % r.text[:200])
else:
    print("[1] token.local.txt 不存在或是空的")

# ---------- 2. client_credentials ----------
print("-" * 70)
SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/buy.item.bulk",
    "https://api.ebay.com/oauth/api_scope/buy.marketing",
]
app_token = ""
for env, root in (("production", "https://api.ebay.com"),
                  ("sandbox", "https://api.sandbox.ebay.com")):
    for scope in SCOPES:
        try:
            r = requests.post(root + "/identity/v1/oauth2/token", auth=(CID, SEC),
                              headers={"Content-Type": "application/x-www-form-urlencoded"},
                              data={"grant_type": "client_credentials", "scope": scope},
                              timeout=30)
        except Exception as exc:
            print("[2] %s scope=%s 请求异常 %s" % (env, scope.rsplit("/", 1)[-1], exc))
            continue
        ok = r.status_code == 200
        print("[2] %-10s scope=%-22s → HTTP %s %s"
              % (env, scope.rsplit("/", 1)[-1], r.status_code,
                 "" if ok else r.text[:160].replace("\n", " ")))
        if ok and env == "production" and not app_token:
            app_token = r.json().get("access_token") or ""
print("-" * 70)

# ---------- 3. app token 能调 Browse 吗 ----------
if not app_token:
    print("[3] 没有 app token，跳过 Browse 测试")
else:
    hdr = {"Authorization": "Bearer " + app_token,
           "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
           "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
    r = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                     headers=hdr, params={"q": "wireless earbuds", "limit": 5}, timeout=30)
    print("[3] app token → item_summary/search HTTP %s" % r.status_code)
    items = []
    if r.status_code == 200:
        d = r.json()
        items = d.get("itemSummaries") or []
        print("    total=%s 返回=%d 条 第一条=%s"
              % (d.get("total"), len(items), (items[0].get("title") or "")[:50] if items else "-"))
    else:
        print("    %s" % r.text[:250])
    if items:
        iid = items[0].get("itemId")
        r2 = requests.get("https://api.ebay.com/buy/browse/v1/item/" + iid, headers=hdr, timeout=30)
        print("[3] app token → getItem %s HTTP %s" % (iid, r2.status_code))
        if r2.status_code == 200:
            d2 = r2.json()
            print("    localizedAspects=%d brand=%s categoryId=%s"
                  % (len(d2.get("localizedAspects") or []),
                     d2.get("brand"), d2.get("categoryId")))
        else:
            print("    %s" % r2.text[:250])
    s = requests.get("https://api.ebay.com/sell/marketing/v1/item_sales/search",
                     headers=hdr, params={"q": "wireless earbuds", "limit": 1}, timeout=30)
    print("[3] app token → item_sales/search（售出数据）HTTP %s %s"
          % (s.status_code, "" if s.status_code == 200 else s.text[:160].replace("\n", " ")))

print("=" * 70)
print("完成，用时 %.1fs" % (time.time() - float(os.environ.get("T0", time.time()))))
