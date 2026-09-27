# -*- coding: utf-8 -*-
"""对外依赖连通性自检（临时诊断脚本，可直接当排障工具用）。

过一遍：
  1. eBay OAuth（client_credentials 换 token）
  2. Browse API：item_summary/search
  3. Browse API：getItem（详情 / item specifics）
  4. **Taxonomy API**：默认类目树 → 该类目的必填/推荐/可选属性 + 属性允许值
     （截图里第四节讲的就是这个）
  5. DeepSeek（标题生成用的那个接口）

消耗：eBay 约 4 次调用（可忽略）；DeepSeek 1 次极短调用（不到 1 分钱）。
"""
import io
import json
import os
import sys
import time

import requests

SHARE_SCRIPTS = r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts"
sys.path.insert(0, SHARE_SCRIPTS)
import ebay_auth  # noqa: E402

SITE = "uk"
MARKETPLACE = "EBAY_GB"
CATEGORY_ID = "112529"        # 实测数据里的末级类目 Headphones

results = []


def check(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        results.append((name, True, detail, time.time() - t0))
    except Exception as exc:
        results.append((name, False, str(exc)[:220], time.time() - t0))


auth = ebay_auth.EbayAuth(verbose=False)
TOKEN = auth.token()
H = {"Authorization": "Bearer " + TOKEN,
     "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
     "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA",
     "Accept": "application/json"}
print("=" * 76)
print("eBay 凭据: env=%s ｜ token 来源=%s" % (auth.env, auth._source))
print("=" * 76)

STATE = {}


def c_browse_search():
    r = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                     headers=H, params={"q": "wireless earbuds", "limit": 3}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:150]))
    d = r.json()
    items = d.get("itemSummaries") or []
    STATE["item_id"] = items[0]["itemId"] if items else ""
    return "total=%s ｜ 返回 %d 条 ｜ 首条: %s" % (d.get("total"), len(items),
                                              (items[0].get("title") or "")[:40])


def c_get_item():
    if not STATE.get("item_id"):
        raise RuntimeError("上一步没拿到 itemId")
    r = requests.get("https://api.ebay.com/buy/browse/v1/item/" + STATE["item_id"],
                     headers=H, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:150]))
    d = r.json()
    aspects = d.get("localizedAspects") or []
    return ("localizedAspects=%d ｜ brand=%s ｜ categoryIdPath=%s"
            % (len(aspects), d.get("brand"), (d.get("categoryIdPath") or "")[:40]))


def c_taxonomy_tree():
    r = requests.get("https://api.ebay.com/commerce/taxonomy/v1/get_default_category_tree_id",
                     headers=H, params={"marketplace_id": MARKETPLACE}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:180]))
    d = r.json()
    STATE["tree_id"] = d.get("categoryTreeId")
    return "categoryTreeId=%s" % d.get("categoryTreeId")


def c_taxonomy_aspects():
    tree = STATE.get("tree_id")
    if not tree:
        raise RuntimeError("没拿到 categoryTreeId")
    url = ("https://api.ebay.com/commerce/taxonomy/v1/category_tree/%s"
           "/get_item_aspects_for_category" % tree)
    r = requests.get(url, headers=H, params={"category_id": CATEGORY_ID}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:180]))
    d = r.json()
    aspects = d.get("aspects") or []
    STATE["aspects"] = aspects
    # 按 aspectConstraint.aspectUsage 分组统计
    g = {}
    for a in aspects:
        usage = ((a.get("aspectConstraint") or {}).get("aspectUsage")) or "未标注"
        g[usage] = g.get(usage, 0) + 1
    return ("类目 %s 共 %d 个属性 ｜ 占比: %s"
            % (CATEGORY_ID, len(aspects),
               "、".join("%s=%d" % (k, v) for k, v in sorted(g.items()))))


def c_taxonomy_values():
    aspects = STATE.get("aspects") or []
    if not aspects:
        raise RuntimeError("上一步没拿到属性")
    with_vals = [a for a in aspects if a.get("aspectValues")]
    sample = with_vals[0] if with_vals else None
    if not sample:
        return "属性都带允许值，但本次样本里没有 aspectValues"
    vals = [v.get("localizedValue") for v in (sample.get("aspectValues") or [])][:6]
    return ("%d/%d 个属性带允许值 ｜ 示例 %s: %s"
            % (len(with_vals), len(aspects),
               sample.get("localizedAspectName"), "、".join(str(v) for v in vals)))


def c_deepseek():
    sys.path.insert(0, SHARE_SCRIPTS)
    import llm_titles
    cfg = llm_titles.load_deepseek_cfg()
    r = requests.post(cfg["url"],
                      headers={"Authorization": "Bearer " + cfg["api_key"],
                               "Content-Type": "application/json"},
                      json={"model": cfg["model"],
                            "messages": [{"role": "user", "content": "只回一个字：好"}],
                            "max_tokens": 8},
                      timeout=60)
    if r.status_code != 200:
        raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:150]))
    d = r.json()
    u = d.get("usage") or {}
    txt = ((d.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    return "model=%s ｜ 回: %s ｜ tokens=%s" % (d.get("model"), txt[:20], u.get("total_tokens"))


check("1. eBay OAuth（换 token）", lambda: "token 长度 %d、有效期约 %.0f 分钟"
      % (len(TOKEN), 120))
check("2. Browse: item_summary/search", c_browse_search)
check("3. Browse: getItem（item specifics）", c_get_item)
check("4. Taxonomy: 默认类目树", c_taxonomy_tree)
check("5. Taxonomy: 类目必填/推荐/可选属性", c_taxonomy_aspects)
check("6. Taxonomy: 属性允许值", c_taxonomy_values)
check("7. DeepSeek 接口", c_deepseek)

print()
print("%-38s %-6s %8s  %s" % ("检查项", "结果", "耗时", "详情"))
print("-" * 76)
ok = 0
for name, passed, detail, sec in results:
    print("%-38s %-6s %7.2fs  %s" % (name, "✅ OK" if passed else "❌ 失败", sec, detail))
    ok += 1 if passed else 0
print("-" * 76)
print("通过 %d / %d" % (ok, len(results)))

# Taxonomy 属性清单存一份，方便后面做"竞品属性地图"对照
if STATE.get("aspects"):
    out = os.path.join(os.environ["TEMP"], "taxonomy_aspects_%s.json" % CATEGORY_ID)
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(STATE["aspects"], f, ensure_ascii=False, indent=2)
    print("属性清单已存: %s（%d 条）" % (out, len(STATE["aspects"])))
    print()
    print("前 12 个属性（名称 / 用途 / 是否多值 / 数据类型）:")
    for a in STATE["aspects"][:12]:
        c = a.get("aspectConstraint") or {}
        print("   %-24s %-11s %-8s %s" % (a.get("localizedAspectName"),
                                          c.get("aspectUsage"),
                                          c.get("itemToAspectCardinality"),
                                          c.get("aspectDataType")))
