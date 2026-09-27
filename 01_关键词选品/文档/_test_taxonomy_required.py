# -*- coding: utf-8 -*-
"""验证 Taxonomy 的"必填属性(REQUIRED)"确实能取到 —— 多探几个真实类目。

Headphones(112529) 碰巧 REQUIRED=0，不能据此说接口不支持必填；
拿我们采集数据里出现过的几个末级类目 ID 都查一遍，看有没有 REQUIRED。
"""
import collections
import glob
import io
import json
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

H = {"Authorization": "Bearer " + ebay_auth.EbayAuth(verbose=False).token(),
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB", "Accept": "application/json"}
TREE = "3"

# 从采集产物里挖出真实出现过的末级类目 ID
cats = collections.Counter()
for p in glob.glob(r"01_关键词选品\输出\api_*.json"):
    d = json.load(io.open(p, encoding="utf-8"))
    for it in d.get("items") or []:
        for cid in (it.get("leaf_category_ids") or []):
            cats[str(cid)] += 1
print("采集数据里的末级类目（前 8）: %s" % cats.most_common(8))
print("=" * 78)

probe = [c for c, _ in cats.most_common(8)]
for cid in probe:
    r = requests.get("https://api.ebay.com/commerce/taxonomy/v1/category_tree/%s"
                     "/get_item_aspects_for_category" % TREE,
                     headers=H, params={"category_id": cid}, timeout=30)
    if r.status_code != 200:
        print("%-10s HTTP %s %s" % (cid, r.status_code, r.text[:100].replace("\n", " ")))
        continue
    d = r.json()
    cat = ((d.get("category") or {}).get("categoryName")) or (d.get("categoryName")) or "?"
    g = collections.Counter()
    req_names = []
    for a in d.get("aspects") or []:
        u = ((a.get("aspectConstraint") or {}).get("aspectUsage")) or "未标注"
        g[u] += 1
        if u == "REQUIRED":
            req_names.append(a.get("localizedAspectName"))
    print("%-10s %-28s 共 %2d 个属性 ｜ REQUIRED=%d RECOMMENDED=%d OPTIONAL=%d%s"
          % (cid, cat[:28], sum(g.values()), g.get("REQUIRED", 0),
             g.get("RECOMMENDED", 0), g.get("OPTIONAL", 0),
             ("  必填: " + "、".join(req_names)) if req_names else ""))
