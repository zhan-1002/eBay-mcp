# -*- coding: utf-8 -*-
"""诊断：推荐标题 vs 文档指令的逐条对照。"""
import glob
import json
import os
import re

OUT = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出"
J = sorted(glob.glob(os.path.join(OUT, "api_uk_wireless_earbuds_*.json")))[-1]
d = json.load(open(J, encoding="utf-8"))
its = d["items"]
rec = d["recommended_titles"]
titles = [x["title"] for x in its]

print("=" * 86)
print("真实竞品标题的长度分布（对照 80 字符这条指令）")
print("=" * 86)
lens = sorted(len(t) for t in titles)
n = len(lens)
print("  min=%d  p25=%d  中位=%d  p75=%d  max=%d" %
      (lens[0], lens[n // 4], lens[n // 2], lens[3 * n // 4], lens[-1]))
print("  ≥70 字符: %d 条 | ≥60: %d | <50: %d" % (
    sum(1 for x in lens if x >= 70), sum(1 for x in lens if x >= 60),
    sum(1 for x in lens if x < 50)))
print()
print("  竞品标题样例（前 6 条完整原文）:")
for t in titles[:6]:
    print("    (%2d) %s" % (len(t), t))

print()
print("=" * 86)
print("我的推荐标题 vs 竞品标题长度")
print("=" * 86)
rl = sorted(len(t) for t in rec)
m = len(rl)
print("  推荐: min=%d 中位=%d max=%d | ≥70 的 %d/%d 条"
      % (rl[0], rl[m // 2], rl[-1], sum(1 for x in rl if x >= 70), m))
print("  竞品: min=%d 中位=%d max=%d | ≥70 的 %d/%d 条"
      % (lens[0], lens[n // 2], lens[-1], sum(1 for x in lens if x >= 70), n))
print("  → 文档要求『最好80个字符』，我的产出中位数比竞品真实标题短 %d 字符"
      % (lens[n // 2] - rl[m // 2]))

print()
print("=" * 86)
print("逐条对照文档《输出要求》")
print("=" * 86)
# 指令10：首页重复率>2 的 title 原样保留
from collections import Counter
freq = Counter(titles)
repeated = [t for t, c in freq.most_common() if c > 2]
kept = [t for t in repeated if t in rec]
print("  指令10 首页重复率>2 的 title 原样保留:")
print("     重复>2 的竞品标题: %d 条" % len(repeated))
print("     其中原样出现在推荐里: %d 条" % len(kept))
miss = [t for t in repeated if t not in rec]
if miss:
    print("     ❌ 漏掉的 %d 条（举 3 例）:" % len(miss))
    for t in miss[:3]:
        print("        (%d字符, 重复%d次) %s" % (len(t), freq[t], t[:70]))

# 指令11：去品牌词、无逗号、≤80
bad_comma = [t for t in rec if "," in t]
bad_len = [t for t in rec if len(t) > 80]
from analyze import detect_brands
brands = detect_brands(titles)
bad_brand = [t for t in rec if any(b in t.lower().split() for b in brands)]
print("  指令11 去品牌词/无逗号/≤80:")
print("     含逗号: %d | 超 80: %d | 含品牌词: %d" % (len(bad_comma), len(bad_len), len(bad_brand)))

# 指令9：尽量只用空格（不用其他标点）
punct = [t for t in rec if re.search(r"[^\w\s]", t)]
print("  指令9 尽量只用空格（其他标点）: %d 条含非空格标点" % len(punct))
for t in punct[:3]:
    print("        %s" % t[:78])

# 指令3/8：从竞品标题"自然提取"
print("  指令3/8 『基于竞品标题自然提取』:")
whole = [t for t in rec if t in titles]
print("     与某条竞品标题完全一致(即真实提取而非拼装): %d/%d 条" % (len(whole), len(rec)))
print("     → 其余 %d 条都是把词块拼装出来的" % (len(rec) - len(whole)))

print()
print("=" * 86)
print("我的推荐标题里的机械痕迹")
print("=" * 86)
dup_kw = [t for t in rec if t.lower().count("wireless") > 1]
tail_junk = [t for t in rec if re.search(r"(Ear-hook|Only|ear)$", t)]
prefix_dup = [t for t in rec if t.lower().startswith("wireless earbuds wireless")]
print("  关键词在标题里重复出现(如两个 wireless): %d 条" % len(dup_kw))
print("  结尾是属性碎片(Ear-hook/Only/ear): %d 条" % len(tail_junk))
print("  开头关键词重复(wireless earbuds wireless...): %d 条" % len(prefix_dup))
print("  含大小写混乱(全大写段): %d 条"
      % len([t for t in rec if re.search(r"\b[A-Z]{4,}\b", t)]))
