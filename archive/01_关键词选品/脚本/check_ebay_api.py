# -*- coding: utf-8 -*-
"""探测 eBay 沙盒/生产密钥是否能换 token 并搜到商品。不写密钥到日志。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from collect_api import _host, _token, _headers
from config_load import ebay_api_creds
from sites import get_site
import requests


def main():
    env = "sandbox"
    if len(sys.argv) > 1 and sys.argv[1] in ("sandbox", "production"):
        env = sys.argv[1]
    creds = ebay_api_creds(env)
    print("环境: %s" % creds["environment"])
    print("Client ID 末 6 位: ...%s" % creds["client_id"][-6:])
    token, env = _token(env)
    print("换 token: OK")
    site = get_site("us")
    headers = _headers(token, site)
    url = _host(env) + "/buy/browse/v1/item_summary/search"
    r = requests.get(url, headers=headers, params={"q": "iphone", "limit": 3}, timeout=45)
    print("搜索 HTTP %s" % r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
        return 1
    items = (r.json() or {}).get("itemSummaries") or []
    print("返回 %d 条（沙盒是测试数据，条数可能很少或为 0）" % len(items))
    for it in items:
        print(" - %s | %s" % (it.get("title"), (it.get("price") or {}).get("value")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
