# -*- coding: utf-8 -*-
"""用现有采集结果离线测试 DeepSeek 生成标题（不采集、不写账号）。"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "脚本"))
sys.path.insert(0, SCRIPTS)

from analyze import detect_brands, specifics_freq, tokenize  # noqa: E402
import report_market as rm  # noqa: E402
import llm_titles  # noqa: E402

OUT = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出"
J = sorted(glob.glob(os.path.join(OUT, "api_uk_wireless_earbuds_*.json")))[-1]
d = json.load(open(J, encoding="utf-8"))
items = d["items"]
keyword = d["keyword"]
site = d.get("site", "uk")
titles = [x["title"] for x in items]

spec_rows = []
for it in items:
    for s in it.get("item_specifics") or []:
        spec_rows.append({"name": s["name"], "value": s["value"], "position": it["position"]})
spec_stats = specifics_freq(spec_rows)

brands = detect_brands(titles)
kw_rows = rm.keyword_analysis(titles, keyword, spec_stats, top_n=20)
mods = rm.modifier_analysis(kw_rows)
templates = rm.structure_templates([tokenize(t) for t in titles], top=5)

from collections import Counter
freq = Counter(titles)
repeated = [t for t, c in freq.most_common() if c > 2]
print("数据: %s（%d 条）" % (os.path.basename(J), len(items)))
print("重复率>2 的竞品标题: %d 条（须原样保留）" % len(repeated))
print("品牌词表: %d 个" % len(brands))
print()

cfg = llm_titles.load_deepseek_cfg()
print("DeepSeek: model=%s | key 前 8 位=%s | url=%s"
      % (cfg["model"], (cfg["api_key"] or "")[:8] + "...", cfg["url"]))
print()

res, meta = llm_titles.generate_titles_llm(
    keyword, site, items, kw_rows, mods, templates, brands, repeated, target=30)

print()
if not res:
    print("❌ LLM 未能产出合规 30 条：%s" % meta)
    sys.exit(2)

print("=" * 88)
print("✅ DeepSeek 产出 %d 条（元信息 %s）" % (len(res), meta))
print("=" * 88)
lens = []
for i, t in enumerate(res, 1):
    lens.append(len(t))
    print("  %2d. (%2d) %s" % (i, len(t), t))
print()
print("字符数: min=%d 中位=%d max=%d | ≥70 的 %d/%d"
      % (min(lens), sorted(lens)[len(lens) // 2], max(lens),
         sum(1 for x in lens if x >= 70), len(lens)))
keep = [t for t in repeated if t in res]
print("原样保留的重复标题: %d/%d 条" % (len(keep), len(repeated)))

p = os.path.join(HERE, "llm_titles_test.json")
with open(p, "w", encoding="utf-8", newline="\n") as f:
    json.dump({"source": os.path.basename(J), "titles": res, "meta": meta,
               "repeated": repeated, "kept": keep}, f, ensure_ascii=False, indent=2)
print("已存 %s" % os.path.basename(p))
