# -*- coding: utf-8 -*-
"""用已有采集结果离线生成"新输出内容"，供审核。不联网、不采集。

输入：输出/haihu_8075_uk_wireless_earbuds_20260914_113146.json（含前 10 条 item specifics）
输出：打印 + 落盘 文档/新输出预览_20260914.md
"""
import json
import os
import sys

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

from analyze import detect_brands, specifics_freq  # noqa: E402
import report_market as rm  # noqa: E402

JSON_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_113146.json"
MD_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\新输出预览_20260914.md"

d = json.load(open(JSON_PATH, encoding="utf-8"))
items = d["items"]
keyword = d["keyword"]
titles = [it["title"] for it in items]

# 用 items 里已有的 specifics 重建属性统计（等价于 analyze.collect_specifics + specifics_freq）
spec_rows = []
for it in items:
    for s in it.get("item_specifics") or []:
        spec_rows.append({"name": s["name"], "value": s["value"], "position": it["position"]})
spec_stats = specifics_freq(spec_rows)

L = []


def out(line=""):
    print(line)
    L.append(line)


out("# 新输出内容预览（用 2026-09-14 已有采集结果离线生成）")
out()
out("数据源：`%s`" % os.path.basename(JSON_PATH))
out("样本：%d 条；关键词 `%s`；站点 `%s`" % (len(items), keyword, d.get("site")))

# ---------- 1. 语言 / 类别 ----------
lang = rm.detect_language(titles)
cat = rm.detect_product_category(titles, keyword, spec_stats)
out()
out("## 1. 语言与产品类别（任务 1）")
out()
out("| 项 | 值 |")
out("|---|---|")
out("| 标题主语言 | %s |" % lang["name"])
out("| 语言判定得分 | %s |" % lang["scores"])
out("| 产品类别 | %s |" % cat["label"])
out("| 品类头部词 | %s |" % "、".join(cat["head_terms"]))
out("| 属性里的 Type | %s |" % cat["spec_type"])

# ---------- 2. 价格一张表 ----------
band_rows, price_stat = rm.build_price_table(items)
out()
out("## 2. 价格区间与占比（合成一张表 · 边界按真实分位选定）")
out()
out("| 价格段(%s) | 下限 | 上限 | 商品数 | 占比%% | 累计占比%% | 竞争强度 |" % d["price"]["currency"])
out("|---|---|---|---|---|---|---|")
for r in band_rows:
    out("| %s | %s | %s | %d | %.1f | %.1f | %s |"
        % (r["价格段"], r["下限"], "" if r["上限"] is None else r["上限"],
           r["商品数"], r["占比%"], r["累计占比%"], r["竞争强度"]))
out()
out("分位：p10 %s / p25 %s / p50 %s / p75 %s / p90 %s / max %s %s"
    % (price_stat["p10"], price_stat["p25"], price_stat["p50"], price_stat["p75"],
       price_stat["p90"], price_stat["max"], d["price"]["currency"]))
out()
out("空档段：%s ｜ 最稀疏段：%s"
    % ("、".join(price_stat["空档段"]) or "无", price_stat["最稀疏段"]))
out()
out("> 占比%%=该段商品数/总数；累计占比%%=从低价段累加；竞争强度按占比分档（≥30%% 红海 / 20-30%% 激烈 / 10-20%% 中等 / <10%% 稀疏 / 0 空档）")

# ---------- 3. 品牌壁垒 ----------
brand_rows, barriers, spec_brand_rows, band_brand_rows = rm.brand_barrier(
    items, titles, spec_stats, detect_brands(titles))
out()
out("## 3. 市场品牌壁垒")
out()
out("### 3.1 结论")
out()
out("| 指标 | 值 |")
out("|---|---|")
for k, v in barriers.items():
    out("| %s | %s |" % (k, v))
out()
out("### 3.2 各价格带的品牌占位率（白牌能不能进）")
out()
out("| 价格带 | 商品数 | 带品牌词条数 | 品牌占位率%% | 白牌条数 |")
out("|---|---|---|---|---|")
for r in band_brand_rows:
    out("| %s | %d | %d | %.1f | %d |"
        % (r["价格带"], r["商品数"], r["带品牌词条数"], r["品牌占位率%"], r["白牌条数"]))
out()
out("### 3.3 品牌 × 价格带 与品牌强势度")
out()
out("| 品牌词 | 商品数 | 占比%% | 类型 | 均价 | 最低价 | 最高价 | 覆盖价格带数 | 主要价格带 | 标题开头占位 | 开头占位率%% |")
out("|---|---|---|---|---|---|---|---|---|---|---|")
for r in brand_rows[:20]:
    out("| %s | %d | %.1f | %s | %s | %s | %s | %d | %s | %d | %.1f |"
        % (r["品牌词"], r["商品数"], r["占比%"], r["类型"], r["均价"],
           r["最低价"], r["最高价"], r["覆盖价格带数"], r["主要价格带"],
           r["标题开头占位"], r["开头占位率%"]))
out()
out("### 3.4 详情页 Brand 字段取值（前 10 条详情）")
out()
out("| Brand 值 | 出现次数 | 类型 |")
out("|---|---|---|")
for r in spec_brand_rows:
    out("| %s | %d | %s |" % (r["Brand值"], r["出现次数"], r["类型"]))

# ---------- 4. 高频关键词 ----------
kw_rows = rm.keyword_analysis(titles, keyword, spec_stats, top_n=20)
out()
out("## 4. 高频关键词分析（任务 2）")
out()
out("| 关键词 | 出现条数 | 占比%% | 主要位置 | 开头 | 中间 | 结尾 | 搜索价值 | 差异化价值 | 综合评分 |")
out("|---|---|---|---|---|---|---|---|---|---|")
for r in kw_rows:
    out("| %s | %d | %.1f | %s | %d | %d | %d | %.1f | %.1f | **%.1f** |"
        % (r["关键词"], r["出现条数"], r["占比%"], r["主要位置"],
           r["开头位置数"], r["中间位置数"], r["结尾位置数"],
           r["搜索价值"], r["差异化价值"], r["综合评分"]))

# ---------- 5. 修饰词三分类 ----------
mods = rm.modifier_analysis(kw_rows)
out()
out("## 5. 修饰词归类（任务 3）")
out()
for group in ("品质相关", "功能相关", "场景/用途相关"):
    items_g = mods[group]
    out()
    out("**%s**（%d 个）：%s" % (group, len(items_g),
                             "、".join("%s(%.1f)" % (r["关键词"], r["综合评分"]) for r in items_g[:12]) or "无"))

# ---------- 6. 结构模板 ----------
seqs = [rm.tokenize(t) for t in titles]
templates = rm.structure_templates(seqs, top=5)
out()
out("## 6. 标题结构模板（任务 4）")
out()
out("| 模板 | 支持条数 | 类型 |")
out("|---|---|---|")
for t in templates:
    out("| %s | %d | %s |" % (t["模板"], t["支持条数"], t["类型"]))

# ---------- 7. 推荐标题 ----------
rec = rm.recommend_titles(keyword, titles, spec_stats, kw_rows, templates,
                          detect_brands(titles), target=30)
out()
out("## 7. 推荐商品标题（任务 8/9/10/11）：共 %d 条" % len(rec))
out()
for i, t in enumerate(rec, 1):
    flag = ""
    if len(t) > 80:
        flag = " ⚠超长"
    if "," in t:
        flag += " ⚠逗号"
    out("%2d. (%2d) %s%s" % (i, len(t), t, flag))

# ---------- 8. 策略建议 ----------
notes = rm.strategy_notes(keyword, kw_rows, detect_brands(titles), band_rows,
                          price_stat, titles, templates, d.get("ad_count", 0))
out()
out("## 8. 策略建议（任务 6/7）")
out()
out("### 标题优化策略")
out()
for s in notes["标题优化策略"]:
    out("- %s" % s)
out()
out("### eBay 平台建议")
out()
for s in notes["eBay平台建议"]:
    out("- %s" % s)

with open(MD_PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(L) + "\n")
print("\n[已落盘] %s" % MD_PATH)
