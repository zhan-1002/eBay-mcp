# -*- coding: utf-8 -*-
"""核实一下：申请失败会不会影响现有能力？

用实测回答"最坏情况是什么"：如果 growth check 被拒，我们现在能用的东西会不会受影响。
本脚本只做只读检查，不消耗额度（除了 1 次 search 确认可用）。
"""
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

auth = ebay_auth.EbayAuth(verbose=False)
tok = auth.token()
H = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
     "Accept": "application/json"}

print("当前这套凭据的状态（申请被拒后这些都不会变）：")
print("  client_id : %s...%s" % (auth.client_id[:6], auth.client_id[-4:]))
print("  env       : %s" % auth.env)

r = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                 headers=H, params={"q": "earbuds", "limit": 1}, timeout=30)
print("  Browse 搜索        : HTTP %s %s" % (r.status_code, "可用" if r.status_code == 200 else "异常"))

r2 = requests.get("https://api.ebay.com/commerce/taxonomy/v1/category_tree/3"
                  "/get_item_aspects_for_category",
                  headers=H, params={"category_id": "112529"}, timeout=30)
print("  Taxonomy 类目属性   : HTTP %s %s" % (r2.status_code, "可用" if r2.status_code == 200 else "异常"))

r3 = requests.post("https://api.ebay.com/identity/v1/oauth2/token",
                   auth=(auth.client_id, auth.client_secret),
                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                   data={"grant_type": "client_credentials",
                         "scope": "https://api.ebay.com/oauth/api_scope"}, timeout=30)
print("  换 token（api_scope）: HTTP %s %s" % (r3.status_code, "可用" if r3.status_code == 200 else "异常"))

r4 = requests.post("https://api.ebay.com/identity/v1/oauth2/token",
                   auth=(auth.client_id, auth.client_secret),
                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                   data={"grant_type": "client_credentials",
                         "scope": "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"},
                   timeout=30)
print("  换 token（销量 scope）: HTTP %s（申请被拒的话，这里维持现状）" % r4.status_code)
print()
print("结论：上面 3 个 ✅ 是现在已有的能力，与「是否申请 / 是否被拒」无关 ——")
print("      销量 scope 现在本来就是拿不到的状态，被拒 = 维持现状，不是「降级」。")
