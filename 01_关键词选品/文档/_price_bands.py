# -*- coding: utf-8 -*-
"""为"价格段边界"和"品牌×价格带"提供数据依据。不联网。"""
import json
import sys
from collections import Counter, defaultdict

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)
from analyze import detect_brands  # noqa: E402
import report_market as rm  # noqa: E402

JSON_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_113146.json"
d = json.load(open(JSON_PATH, encoding="utf-8"))
items = d["items"]
titles = [it["title"] for it in items]
prices = sorted(it["price"] for it in items if it.get("price"))
n = len(prices)

print("=" * 76)
print("① 价格真实分布（判断边界该怎么切）")
print("=" * 76)
print("样本 %d 条，min %.2f max %.2f" % (n, prices[0], prices[-1]))
print()
print("整数英镑带的自然分布：")
band = Counter()
for p in prices:
    band[int(p)] += 1
for k in sorted(band):
    bar = "█" * band[k]
    print("   £%-3d %3d %s" % (k, band[k], bar))

print()
print("常用切法的对比（看哪种最均衡、gap 最清楚）：")
SCHEMES = {
    "A 现用整数段": [0, 5, 10, 15, 20, 25, 100],
    "B 合并低段":   [0, 5, 8, 10, 13, 16, 20, 100],
    "C 低价高密":   [0, 8, 12, 16, 20, 100],
    "D 五段均衡":   [0, 8, 12, 16, 22, 100],
    "E 含0-5细分":  [0, 5, 8, 10, 12, 15, 20, 100],
}
for name, edges in SCHEMES.items():
    counts = rm.spread_bins(prices, [float(e) for e in edges])
    tot = sum(counts) or 1
    pcts = [100.0 * c / tot for c in counts]
    labels = ["%g-%g" % (edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    print("   %s:" % name)
    print("      %s" % " | ".join("%s:%.1f%%" % (l, p) for l, p in zip(labels, pcts)))
    spread = max(pcts) - min(pcts)
    print("      极差 %.1f 个百分点（越小越均衡）" % spread)

print()
print("分位：p10 %.2f  p25 %.2f  p50 %.2f  p75 %.2f  p90 %.2f"
      % (prices[int(0.1 * n)], prices[int(0.25 * n)], prices[int(0.5 * n)],
         prices[int(0.75 * n)], prices[int(0.9 * n)]))
print("众数价格点（.99/.49 这类心理价位）：")
ps = Counter(round(p, 2) for p in prices)
for v, c in ps.most_common(10):
    print("   £%-7s %d 条" % (v, c))

print()
print("=" * 76)
print("② 品牌 × 价格带（品牌壁垒该加什么维度）")
print("=" * 76)
brands = detect_brands(titles)
EDGES = [0, 10, 15, 20, 100]
labels = ["<%g" % EDGES[1], "%g-%g" % (EDGES[1], EDGES[2]),
          "%g-%g" % (EDGES[2], EDGES[3]), ">=%g" % EDGES[3]]
print("价格带：%s" % " | ".join(labels))
print()
rows = defaultdict(lambda: [0] * len(labels))
tot_row = [0] * len(labels)
for it in items:
    t = it.get("title") or ""
    p = it.get("price")
    if p is None:
        continue
    idx = 0
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            idx = i
            break
    tot_row[idx] += 1
    for b in {w for w in rm.tokenize(t) if w in brands}:
        rows[b][idx] += 1

print("%-12s %s" % ("品牌", "  ".join("%-8s" % l for l in labels)))
for b, arr in sorted(rows.items(), key=lambda kv: -sum(kv[1]))[:12]:
    print("%-12s %s" % (b, "  ".join("%-8d" % x for x in arr)))
print("%-12s %s" % ("全部商品", "  ".join("%-8d" % x for x in tot_row)))
print()
print("各价格带里的品牌占位情况（品牌条数 / 该带总数）：")
for i, l in enumerate(labels):
    tot = tot_row[i] or 1
    br = sum(arr[i] for arr in rows.values())
    print("   %-8s 品牌条数 %-3d / 总数 %-3d = %.0f%%" % (l, br, tot_row[i], 100.0 * br / tot))
