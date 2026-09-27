# -*- coding: utf-8 -*-
"""从 apis.guru 的官方 OpenAPI 规格里读出 eBay 各 API 的**真实路径**与**所需 scope**。

为什么要这么做：上一轮我用"猜的路径"探端点，404 未必等于不存在。
OpenAPI 规格里有权威的 paths + security（scope）定义，一次就能拿准。
"""
import io
import json
import os
import re

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
CACHE = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\apisguru_list.json"

if os.path.isfile(CACHE):
    data = json.load(io.open(CACHE, encoding="utf-8"))
    print("用缓存的索引（%d 字节）" % os.path.getsize(CACHE))
else:
    r = requests.get("https://api.apis.guru/v2/list.json", headers=H, timeout=120)
    r.raise_for_status()
    io.open(CACHE, "w", encoding="utf-8").write(r.text)
    data = r.json()
    print("已下载索引（%d 字节）" % os.path.getsize(CACHE))

ebay = {k: v for k, v in data.items() if "ebay" in k.lower()}
print("eBay 规格 %d 个\n" % len(ebay))

# 只关心这些（对我们可能有用）
WANT = ["sell-analytics", "sell-finances", "sell-listing", "sell-marketing",
        "sell-metadata", "sell-negotiation", "sell-recommendation",
        "developer-analytics", "commerce-translation", "sell-fulfillment",
        "sell-account", "sell-feed", "sell-compliance", "sell-logistics",
        "buy-browse", "commerce-taxonomy"]

for key in sorted(ebay):
    short = key.split(":")[-1]
    if short not in WANT:
        continue
    pref = ebay[key].get("preferred")
    ver = (ebay[key].get("versions") or {}).get(pref) or {}
    info = ver.get("info") or {}
    url = ver.get("swaggerUrl") or ver.get("openapiUrl")
    print("=" * 96)
    print("%s  →  %s" % (short, info.get("title")))
    print("  规格: %s" % url)
    if not url:
        continue
    try:
        s = requests.get(url, headers=H, timeout=60).json()
        servers = s.get("servers") or [{"url": "-"}]
        print("  host: %s" % ", ".join(x.get("url", "-") for x in servers[:2]))
        paths = s.get("paths") or {}
        # 收集所有 security scope
        scopes = set()

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "security" and isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                for _n, sc in item.items():
                                    if isinstance(sc, list):
                                        scopes.update(sc)
                    walk(v)
            elif isinstance(o, list):
                for x in o:
                    walk(x)

        walk(s)
        if scopes:
            print("  需要的 scope:")
            for sc in sorted(scopes):
                print("     · %s" % sc)
        # 路径：只列前 12 个，太长就截断
        plist = sorted(paths.keys())
        print("  路径 %d 个:" % len(plist))
        for p in plist[:12]:
            methods = ",".join(sorted(m.upper() for m in paths[p]
                                      if m in ("get", "post", "put", "delete")))
            desc = ""
            for m in paths[p].values():
                if isinstance(m, dict) and m.get("summary"):
                    desc = m["summary"][:52]
                    break
            print("     %-56s %-10s %s" % (p[:56], methods, desc))
        if len(plist) > 12:
            print("     … 还有 %d 个" % (len(plist) - 12))
    except Exception as exc:
        print("  取规格失败: %s" % str(exc)[:100])
    print()
