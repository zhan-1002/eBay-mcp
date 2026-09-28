# -*- coding: utf-8 -*-
"""用截图上的生产密钥对（BETA-PRD / PRD-Cert）真试一次 client_credentials。

推断依据：
  沙箱 App ID 段结构 = [4,3,9,8] → BETA | SBX | 9位 | 8位（config 里存的就是这个）
  截图生产 App ID 可见部分 = "BETA-PRD-f82b86fbd-f4f4c153" → 段结构也是 [4,3,9,8]
  ⇒ 生产 App ID 应当就是 BETA-PRD-f82b86fbd-f4f4c153（"BETA" 是应用名，不是 sandbox 标记）

能换到 token 就说明推断正确，同时这个坑也就解了。
"""
import json
import sys

import requests

CID = "BETA-PRD-f82b86fbd-f4f4c153"
SEC = "PRD-examplecert000-0000-0000-0000-0000"
ROOT = "https://api.ebay.com"

print("候选生产密钥对：")
print("  App ID  = %s（%d 位）" % (CID, len(CID)))
print("  Cert ID = %s...%s（%d 位）" % (SEC[:6], SEC[-4:], len(SEC)))
print("-" * 72)

for scope in ("https://api.ebay.com/oauth/api_scope",
              "https://api.ebay.com/oauth/api_scope/buy.item.bulk"):
    r = requests.post(ROOT + "/identity/v1/oauth2/token", auth=(CID, SEC),
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "scope": scope},
                      timeout=30)
    print("client_credentials scope=%-22s → HTTP %s %s"
          % (scope.rsplit("/", 1)[-1], r.status_code,
             "" if r.status_code == 200 else r.text[:180].replace("\n", " ")))
    if r.status_code != 200:
        continue
    d = r.json()
    tok = d["access_token"]
    print("  ✅ 换到 app token：长度 %d ｜ expires_in %s ｜ scope %s"
          % (len(tok), d.get("expires_in"), d.get("scope")))
    hdr = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
           "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
    s = requests.get(ROOT + "/buy/browse/v1/item_summary/search", headers=hdr,
                     params={"q": "wireless earbuds", "limit": 3}, timeout=30)
    print("  Browse item_summary/search → HTTP %s" % s.status_code)
    if s.status_code != 200:
        print("    %s" % s.text[:220].replace("\n", " "))
        sys.exit(1)
    items = s.json().get("itemSummaries") or []
    print("    total=%s 返回 %d 条" % (s.json().get("total"), len(items)))
    for it in items[:3]:
        print("      - %s" % (it.get("title") or "")[:60])
    iid = items[0]["itemId"]
    g = requests.get(ROOT + "/buy/browse/v1/item/" + iid, headers=hdr, timeout=30)
    print("  getItem → HTTP %s" % g.status_code)
    if g.status_code == 200:
        dd = g.json()
        print("    localizedAspects=%d ｜ brand=%s ｜ categoryId=%s ｜ priorityListing=%s"
              % (len(dd.get("localizedAspects") or []), dd.get("brand"),
                 dd.get("categoryId"), dd.get("priorityListing")))
    print("-" * 72)
    print("结论：截图上的生产密钥对可用 ✅  client_credentials 畅通，不需要人工贴 token")
    sys.exit(0)

print("-" * 72)
print("结论：这对不行，说明截图里 App ID 左侧确有被截断的部分，需要完整值")
sys.exit(1)
