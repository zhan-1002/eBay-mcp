# -*- coding: utf-8 -*-
"""把类目属性清单（Taxonomy）抓下来存成可复用缓存。

存到 01_关键词选品\\数据\\taxonomy\\<市场>_<类目>.json —— 之后做
"这个类目的 Item Specifics 该填什么 / 竞品属性地图" 时直接读本地，
不用再往 eBay 打请求（省额度）。

用法： python _fetch_taxonomy_cache.py [marketplace] [category_id ...]
"""
import io
import json
import os
import sys

import requests

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth

OUT_DIR = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\数据\taxonomy"
MARKETPLACE = (sys.argv[1] if len(sys.argv) > 1 else "EBAY_GB")
CATS = sys.argv[2:] or ["112529", "80077"]

os.makedirs(OUT_DIR, exist_ok=True)
H = {"Authorization": "Bearer " + ebay_auth.EbayAuth(verbose=False).token(),
     "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE, "Accept": "application/json"}

r = requests.get("https://api.ebay.com/commerce/taxonomy/v1/get_default_category_tree_id",
                 headers=H, params={"marketplace_id": MARKETPLACE}, timeout=30)
r.raise_for_status()
tree = r.json()["categoryTreeId"]
print("marketplace=%s → categoryTreeId=%s" % (MARKETPLACE, tree))

for cid in CATS:
    rr = requests.get("https://api.ebay.com/commerce/taxonomy/v1/category_tree/%s"
                      "/get_item_aspects_for_category" % tree,
                      headers=H, params={"category_id": cid}, timeout=30)
    if rr.status_code != 200:
        print("  类目 %s 失败 HTTP %s %s" % (cid, rr.status_code, rr.text[:120]))
        continue
    d = rr.json()
    path = os.path.join(OUT_DIR, "%s_%s.json" % (MARKETPLACE, cid))
    payload = {"marketplace": MARKETPLACE, "categoryTreeId": tree,
               "categoryId": cid, "fetched_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
               "category": d.get("category"), "aspects": d.get("aspects") or []}
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    must = [a["localizedAspectName"] for a in payload["aspects"]
            if (a.get("aspectConstraint") or {}).get("aspectRequired")]
    print("  类目 %-8s %2d 个属性 ｜ 必填 %d 个 %s → %s"
          % (cid, len(payload["aspects"]), len(must),
             ("(" + "、".join(must) + ")") if must else "", os.path.basename(path)))
print("缓存目录: %s" % OUT_DIR)
