# -*- coding: utf-8 -*-
"""Feedback API（评论/反馈）实测 —— 用真实卖家名查。

这是本轮挖到的新能力：scope `commerce.feedback.readonly` 是**应用级**的，
client_credentials 就能拿到，不需要卖家授权。
"""
import glob
import io
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

# ① 从我们采集的数据里取几个真实卖家名
sellers = []
for p in sorted(glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay"
                          r"\01_关键词选品\输出\api_*.json")):
    try:
        d = json.load(io.open(p, encoding="utf-8"))
    except Exception:
        continue
    for it in d.get("items") or []:
        u = ((it.get("seller") or {}).get("username")
             if isinstance(it.get("seller"), dict) else it.get("seller_username"))
        if u and u not in sellers:
            sellers.append(u)
    if len(sellers) >= 6:
        break
print("样本卖家: %s" % sellers[:6])

# ② 换一个带 feedback scope 的令牌
auth = ebay_auth.EbayAuth(verbose=False)
r = requests.post("https://api.ebay.com/identity/v1/oauth2/token",
                  auth=(auth.client_id, auth.client_secret),
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  data={"grant_type": "client_credentials",
                        "scope": "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly"},
                  timeout=30)
print("换令牌 HTTP %s" % r.status_code)
tok = r.json().get("access_token")
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}
API = "https://api.ebay.com"

ENDPOINTS = [
    ("/commerce/feedback/v1/feedback", {"username": None}),
    ("/commerce/feedback/v1/feedback_rating_summary", {"username": None}),
    ("/commerce/feedback/v1/awaiting_feedback", {}),
]
for path, params in ENDPOINTS:
    print()
    print("=" * 92)
    print(path)
    print("=" * 92)
    if "username" in params:
        u = sellers[0] if sellers else "ebay"
        p2 = dict(params)
        p2["username"] = u
        rr = requests.get(API + path, headers=A, params=p2, timeout=30)
        print("  username=%s → HTTP %s" % (u, rr.status_code))
    else:
        rr = requests.get(API + path, headers=A, params=params, timeout=30)
        print("  → HTTP %s" % rr.status_code)
    body = rr.text
    print("  %s" % body[:1200].replace("\n", " "))
