# -*- coding: utf-8 -*-
"""生产环境覆盖度实测（只读）：120 条量级的 localizedAspects 覆盖率 + 字段完整度 + 额度消耗。

不写任何账号，不调用任何写接口。
"""
import json
import os
import time
from collections import Counter
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = open(os.path.normpath(os.path.join(HERE, "..", "token.local.txt")),
             encoding="utf-8").read().strip()
BASE = "https://api.ebay.com"
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
os.makedirs(OUT, exist_ok=True)

KEYWORD = "wireless earbuds"
SITE = ("EBAY_GB", "GB", "SW1A1AA")
MAX_DETAIL = 120
CALLS = Counter()


def hdrs(mp=SITE[0], ctry=SITE[1], zp=SITE[2]):
    return {"Authorization": "Bearer " + TOKEN,
            "X-EBAY-C-MARKETPLACE-ID": mp,
            "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%%3D%s%%2Czip%%3D%s" % (ctry, zp),
            "Accept": "application/json"}


print("=" * 78)
print("① 搜索：拿 120 条量级")
print("=" * 78)
CALLS["search"] += 1
t0 = time.time()
r = requests.get(BASE + "/buy/browse/v1/item_summary/search", headers=hdrs(),
                 params={"q": KEYWORD, "limit": 200}, timeout=60)
print("  HTTP %s | 耗时 %.1fs" % (r.status_code, time.time() - t0))
if r.status_code != 200:
    print("  失败: %s" % r.text[:300])
    raise SystemExit(1)
payload = r.json()
summaries = payload.get("itemSummaries") or []
print("  total=%s | 本页返回 %d 条 | 是否有 next: %s"
      % (payload.get("total"), len(summaries), bool(payload.get("next"))))

targets = summaries[:MAX_DETAIL]
print("  取前 %d 条做逐条详情" % len(targets))

print()
print("=" * 78)
print("② 逐条 getItem：localizedAspects 覆盖率与字段完整度")
print("=" * 78)
rows = []
t0 = time.time()
for i, s in enumerate(targets, 1):
    iid = s.get("itemId")
    rec = {"itemId": iid, "legacyItemId": s.get("legacyItemId"),
           "title": s.get("title"), "summary": s}
    try:
        CALLS["getItem"] += 1
        g = requests.get(BASE + "/buy/browse/v1/item/" + quote(iid, safe=""),
                         headers=hdrs(), timeout=30)
    except Exception as exc:
        rec["err"] = str(exc)[:80]
        rows.append(rec)
        continue
    if g.status_code != 200:
        rec["err"] = "HTTP %s %s" % (g.status_code, g.text[:100])
        rows.append(rec)
        continue
    d = g.json()
    asp = d.get("localizedAspects") or []
    rec.update({
        "ok": True,
        "aspects_n": len(asp),
        "aspects": [{"name": a.get("name"), "value": a.get("value")} for a in asp],
        "categoryPath": d.get("categoryPath"),
        "categoryId": d.get("categoryId"),
        "categoryPathIds": d.get("categoryPathIds"),
        "desc_len": len(d.get("description") or ""),
        "short_desc_len": len(d.get("shortDescription") or ""),
        "images_n": len(d.get("additionalImages") or []) + (1 if d.get("image") else 0),
        "brand": d.get("brand"),
        "color": d.get("color"),
        "condition": d.get("condition"),
        "itemLocation": d.get("itemLocation"),
        "returnTerms": bool(d.get("returnTerms")),
        "shippingOptions_n": len(d.get("shippingOptions") or []),
        "raw_keys": list(d.keys()),
    })
    rows.append(rec)
    if i % 20 == 0:
        print("     已处理 %d/%d ..." % (i, len(targets)))
    time.sleep(0.05)

dt = time.time() - t0
ok = [x for x in rows if x.get("ok")]
bad = [x for x in rows if not x.get("ok")]
with_asp = [x for x in ok if x["aspects_n"] > 0]
print()
print("  getItem 成功: %d / %d | 失败: %d | 总耗时 %.1fs（平均 %.2fs/条）"
      % (len(ok), len(rows), len(bad), dt, dt / max(1, len(rows))))
print("  ┌─ 有 localizedAspects: %d" % len(with_asp))
print("  └─ 无 localizedAspects: %d" % (len(ok) - len(with_asp)))
if ok:
    print("  ★ 覆盖率 = %.1f%%" % (100.0 * len(with_asp) / len(ok)))
for x in bad[:5]:
    print("     失败 %s -> %s" % (str(x.get("itemId"))[:30], str(x.get("err"))[:90]))

print()
print("=" * 78)
print("③ 字段完整度（在成功的 %d 条里）" % len(ok))
print("=" * 78)
def rate(key, pred=lambda v: bool(v)):
    n = sum(1 for x in ok if pred(x.get(key)))
    return n, (100.0 * n / len(ok) if ok else 0)

for label, key, pred in [
    ("localizedAspects 非空", "aspects_n", lambda v: v and v > 0),
    ("描述非空(>0)", "desc_len", lambda v: v and v > 0),
    ("描述较长(>300)", "desc_len", lambda v: v and v > 300),
    ("有图片", "images_n", lambda v: v and v > 0),
    ("categoryPath 有值", "categoryPath", lambda v: bool(v)),
    ("categoryId 有值", "categoryId", lambda v: bool(v)),
    ("brand 顶层字段有值", "brand", lambda v: bool(v)),
    ("color 顶层字段有值", "color", lambda v: bool(v)),
    ("condition 有值", "condition", lambda v: bool(v)),
    ("returnTerms 有值", "returnTerms", lambda v: bool(v)),
]:
    n, p = rate(key, pred)
    print("  %-24s %3d/%d = %5.1f%%" % (label, n, len(ok), p))

print()
print("=" * 78)
print("④ 刊登表单必填项在 localizedAspects 里的覆盖（关键）")
print("=" * 78)
NEED = ["Brand", "Connectivity", "Model", "Colour", "Type"]
for item_name in NEED:
    n = 0
    for x in with_asp:
        if any((a.get("name") or "").strip().lower() == item_name.lower() for a in x["aspects"]):
            n += 1
    print("  %-16s 有值 %3d/%d = %5.1f%%" % (item_name, n, len(ok),
                                             100.0 * n / len(ok) if ok else 0))

# aspects 名称频次
name_cnt = Counter()
for x in with_asp:
    for a in x["aspects"]:
        name_cnt[(a.get("name") or "").strip()] += 1
print()
print("  localizedAspects 字段名出现频次 top 20:")
for nm, c in name_cnt.most_common(20):
    print("     %-30s %d" % (nm, c))

print()
print("=" * 78)
print("⑤ 调用消耗（本次）")
print("=" * 78)
print("  search=%d  getItem=%d  合计=%d 次" % (CALLS["search"], CALLS["getItem"],
                                              CALLS["search"] + CALLS["getItem"]))
print("  按此推算：一个关键词+一个站点跑 120 条 = %d + 120 = %d 次调用"
      % (CALLS["search"], CALLS["search"] + CALLS["getItem"]))

with open(os.path.join(OUT, "prod_coverage.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump({"keyword": KEYWORD, "site": SITE, "calls": dict(CALLS),
               "total": payload.get("total"), "rows": rows}, f, ensure_ascii=False, indent=2)
print("\n已存 prod_coverage.json")
