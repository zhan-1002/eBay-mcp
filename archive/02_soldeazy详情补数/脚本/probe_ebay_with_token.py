# -*- coding: utf-8 -*-
"""用 User Token 跑 Browse API 验证（不依赖 client_id/secret）。

token 来源：开发者后台 / API Explorer 的 User Tokens（沙箱或生产），
放到本地文件（不进版本库）：
  02_soldeazy详情补数/token.local.txt        —— 只放一行 token
或 config.local.json 的 ebay_api.user_token 字段。

用法:
  python probe_ebay_with_token.py            # 默认沙箱域名
  python probe_ebay_with_token.py --prod     # 生产域名
"""
import argparse
import json
import os
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
TOKEN_FILE = os.path.normpath(os.path.join(HERE, "..", "token.local.txt"))
CFG = os.path.join(PROJ, "config.local.json")


def load_token():
    if os.path.isfile(TOKEN_FILE):
        t = open(TOKEN_FILE, encoding="utf-8").read().strip()
        if t:
            print("token 来源: %s（长度 %d）" % (os.path.basename(TOKEN_FILE), len(t)))
            return t
    if os.path.isfile(CFG):
        try:
            d = json.load(open(CFG, encoding="utf-8"))
            t = ((d.get("ebay_api") or {}).get("user_token") or "").strip()
            if t:
                print("token 来源: config.local.json（长度 %d）" % len(t))
                return t
        except Exception:
            pass
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", action="store_true", help="用生产域名（默认沙箱）")
    ap.add_argument("--q", default="wireless earbuds")
    ap.add_argument("--marketplace", default="EBAY_GB")
    ap.add_argument("--zip", default="SW1A1AA")
    ap.add_argument("--country", default="GB")
    args = ap.parse_args()

    token = load_token()
    if not token:
        print("没有找到 token。请把 User Token 写入：")
        print("  %s" % TOKEN_FILE)
        print("（文件只放一行 token；该路径已 gitignore）")
        return 2

    base = "https://api.ebay.com" if args.prod else "https://api.sandbox.ebay.com"
    hdrs = {
        "Authorization": "Bearer " + token,
        "X-EBAY-C-MARKETPLACE-ID": args.marketplace,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%%3D%s%%2Czip%%3D%s"
                               % (args.country, args.zip),
        "Accept": "application/json",
    }
    print("域名: %s | marketplace=%s | 配送地=%s %s"
          % (base, args.marketplace, args.country, args.zip))

    print("\n=== 1. 搜索 item_summary/search ===")
    url = base + "/buy/browse/v1/item_summary/search"
    params = {"q": args.q, "limit": 5,
              "fieldgroups": "EXTENDED,ASPECT_REFINEMENTS,CATEGORY_REFINEMENTS"}
    r = requests.get(url, headers=hdrs, params=params, timeout=45)
    print("HTTP %s" % r.status_code)
    if r.status_code != 200:
        print("返回: %s" % r.text[:400])
        print("\n（401/403 说明 token 无效或域名不匹配：沙箱 token 配沙箱域名，生产 token 配生产域名）")
        return 3
    payload = r.json()
    items = payload.get("itemSummaries") or []
    print("命中 %d 条 | 顶层键: %s" % (len(items), list(payload.keys())))
    if not items:
        print("无结果（沙箱数据可能为空，属正常）")
        return 0

    print("\n第 1 条 itemSummary 字段:")
    for k, v in items[0].items():
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        print("   %-24s = %s" % (k, str(s)[:88]))
    print("\n★ item specifics 相关键: %s"
          % ([k for k in items[0] if any(x in k.lower() for x in ("aspect", "specific"))] or "无"))
    print("★ leafCategoryIds: %s" % items[0].get("leafCategoryIds"))
    print("★ categoryPath: %s" % items[0].get("categoryPath"))

    iid = items[0].get("itemId")
    if not iid:
        return 0
    print("\n=== 2. getItem（%s）===" % iid)
    from urllib.parse import quote
    r2 = requests.get(base + "/buy/browse/v1/item/" + quote(iid, safe=""),
                      headers=hdrs, timeout=30)
    print("HTTP %s" % r2.status_code)
    if r2.status_code == 200:
        det = r2.json()
        print("返回键: %s" % list(det.keys()))
        asp = det.get("localizedAspects") or []
        print("★ localizedAspects 条数: %d" % len(asp))
        for a in asp[:10]:
            print("     %-26s = %s" % (a.get("name"), str(a.get("value"))[:60]))
        print("★ categoryPathIds: %s" % det.get("categoryPathIds"))
        print("★ categoryId: %s" % det.get("categoryId"))
        print("★ 描述长度: %d | 图片数: %d"
              % (len(det.get("description") or ""),
                 len(det.get("additionalImages") or []) + (1 if det.get("image") else 0)))
        out = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
        os.makedirs(out, exist_ok=True)
        p = os.path.join(out, "getitem_%s.json" % iid.replace("|", "_")[:40])
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(det, f, ensure_ascii=False, indent=2)
        print("已存: %s" % os.path.basename(p))
    else:
        print("返回: %s" % r2.text[:300])

    print("\n=== 3. Marketplace Insights（售出数据）权限探测 ===")
    mi = base + "/buy/marketplace_insights/v1_beta/item_sales/search"
    r3 = requests.get(mi, headers=hdrs, params={"q": args.q, "limit": 1}, timeout=30)
    print("HTTP %s" % r3.status_code)
    print("返回: %s" % r3.text[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
