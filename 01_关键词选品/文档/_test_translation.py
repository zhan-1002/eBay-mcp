# -*- coding: utf-8 -*-
"""实测翻译 API 对我们场景是否真的有用（英 → 德/法/西/意，标题语境）。"""
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Content-Type": "application/json",
     "Accept": "application/json", "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
URL = "https://api.ebay.com/commerce/translation/v1_beta/translate"

TITLE = "TWS Wireless Bluetooth Earphones Air In-Ear Pods Buds for iPhone Samsung Android"
KW = ["wireless earbuds", "noise cancelling headphones", "phone case", "charging cable"]

print("原文: %s\n" % TITLE)
for lang, name in (("de", "德语"), ("fr", "法语"), ("es", "西语"), ("it", "意语")):
    r = requests.post(URL, headers=A, json={
        "from": "en", "to": lang, "text": [TITLE], "translationContext": "ITEM_TITLE"},
        timeout=35)
    if r.status_code == 200:
        out = (r.json().get("translations") or [{}])[0].get("translatedText", "")
        print("%s: %s" % (name, out))
    else:
        print("%s: HTTP %s %s" % (name, r.status_code, r.text[:120]))

print()
print("关键词翻译（英 → 德）：")
r = requests.post(URL, headers=A, json={
    "from": "en", "to": "de", "text": KW, "translationContext": "ITEM_TITLE"}, timeout=35)
if r.status_code == 200:
    for t in r.json().get("translations") or []:
        print("   %-32s → %s" % (t.get("originalText"), t.get("translatedText")))
else:
    print("   HTTP %s %s" % (r.status_code, r.text[:150]))
