# -*- coding: utf-8 -*-
"""试 eBay 官方「查额度」接口 Developer Analytics getRateLimits。

响应头里没有额度信息（已实测），所以看看官方这个接口能不能用 app token 调。
路径试几个候选；404/401/403 的报文本身就说明问题，且不消耗额度。
"""
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

tok = ebay_auth.EbayAuth(verbose=False).token()
H = {"Authorization": "Bearer " + tok, "Accept": "application/json"}

CANDIDATES = [
    "/sell/developer_analytics/v1/rate_limit",
    "/sell/developer_analytics/v1/rate_limits",
    "/developer_analytics/v1/rate_limit",
    "/buy/developer_analytics/v1/rate_limit",
    "/sell/developer_analytics/v1/rate_limit/browse/1",
]

for path in CANDIDATES:
    try:
        r = requests.get("https://api.ebay.com" + path, headers=H, timeout=30)
    except Exception as exc:
        print("%-52s 异常 %s" % (path, exc))
        continue
    body = r.text[:220].replace("\n", " ")
    print("%-52s HTTP %s  %s" % (path, r.status_code, body))
