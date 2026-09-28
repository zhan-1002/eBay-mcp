# -*- coding: utf-8 -*-
"""把 13 张子表合并成 5 张。

目标结构：
  1. 市场概况与价格   —— 概况 + 价格区间占比 + 价格分位
  2. 品牌壁垒        —— 主口径(结构化 brand 字段) + 标题品牌词提及率(辅助) + Price带占位 + 原始取值
  3. 关键词与标题     —— 关键词评分 + 修饰词三分类 + 结构模板 + 推荐标题 30 条 + 策略建议
  4. 采集明细        —— 120 行完整字段
  5. 基础统计        —— 完整title重复 + title词频 + 属性词频 + 类目分布
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "脚本", "run_keyword_research.py"))
src = open(P, encoding="utf-8").read()
print("目标文件: %s" % P)

if "def export_market_sheets_5(" in src:
    print("已存在 5 表版本，跳过")
    raise SystemExit(0)

# 找到 export_market_sheets 函数体范围（从 def 到下一个顶层 def）
m = re.search(r"\ndef export_market_sheets\(.*?(?=\ndef export_report\()", src, re.S)
if not m:
    print("没找到 export_market_sheets 函数")
    raise SystemExit(1)
old_block = m.group(0)

NEW = '''

def export_market_sheets(report, w, kw_rows, brand_pack, mods, templates, notes,
                         target_titles):
    """市场分析子表 —— 合并为 5 张（用户要求：子表数量减到四五个，相关内容合并）。

      1. 市场概况与价格  2. 品牌壁垒  3. 关键词与标题  4. 采集明细  5. 基础统计
    采集明细由 export_report 单独写，这里只写 1/2/3/5。
    """
    price_rows = report.get("price_bands") or []
    price_stat = report.get("price_stat") or {}
    cur = report.get("currency", "")
    cat = report.get("category") or {}
    lang = report.get("language") or {}
    st = brand_pack.get("structured") or {}
    bsum = st.get("summary") or {}
    b_rows = st.get("brand_rows") or []
    b_occ = st.get("occupancy_by_band") or []
    b_raw = st.get("spec_rows") or []
    tm_rows = brand_pack.get("title_mentions") or []
    tm_occ = brand_pack.get("title_occ") or []

    # ---------- 1. 市场概况与价格 ----------
    ws = w.book.create_sheet("市场概况与价格")
    write_sections(ws, [
        ("一、市场概况", ["项", "值"], [
            ["关键词", report.get("keyword")],
            ["站点", report.get("site")],
            ["采集条数", report.get("item_count")],
            ["数据来源", "eBay 官方 Browse API（生产环境）"],
            ["广告位条数", report.get("ad_count")],
            ["标题主语言", lang.get("name")],
            ["产品类别", cat.get("label")],
            ["品类头部词", "、".join(cat.get("head_terms") or [])],
            ["属性里的 Type", cat.get("spec_type")],
            ["推荐末级类目ID", (report.get("category_stats") or {}).get("recommend_leaf_id")],
            ["推荐末级类目名", (report.get("category_stats") or {}).get("recommend_leaf_name")],
        ]),
        ("二、价格区间与占比", ["价格段(%s)" % cur, "下限", "上限", "商品数", "占比%",
                          "累计占比%", "竞争强度"],
         to_rows(price_rows, ["价格段", "下限", "上限", "商品数", "占比%", "累计占比%", "竞争强度"])),
        ("三、价格分位", ["指标", "值(%s)" % cur], [
            ["p10", price_stat.get("p10")], ["p25", price_stat.get("p25")],
            ["p50 中位", price_stat.get("p50")], ["p75", price_stat.get("p75")],
            ["p90", price_stat.get("p90")], ["最低", price_stat.get("min")],
            ["最高", price_stat.get("max")],
            ["空档段", "、".join(price_stat.get("空档段") or []) or "无"],
            ["最稀疏段", price_stat.get("最稀疏段")],
        ]),
        ("四、口径说明", ["说明"], [
            ["占比% = 该段商品数 / 总商品数"],
            ["累计占比% = 从低价段往上累加"],
            ["竞争强度：≥30% 红海 / 20-30% 竞争激烈 / 10-20% 中等 / <10% 稀疏 / 0 空档（蓝海）"],
            ["价格段边界固定为 0-5/5-8/8-10/10-13/13-16/16-20/20+（按真实分位选定，见文档）"],
        ]),
    ])

    # ---------- 2. 品牌壁垒 ----------
    ws = w.book.create_sheet("品牌壁垒")
    write_sections(ws, [
        ("一、结论（主口径：结构化 brand 字段）", ["指标", "值"],
         [[k, v] for k, v in bsum.items()]),
        ("二、各价格带的真品牌占位率（白牌能不能进）",
         ["价格带", "商品数", "真品牌条数", "真品牌占位率%", "白牌条数"],
         to_rows(b_occ, ["价格带", "商品数", "真品牌条数", "真品牌占位率%", "白牌条数"])),
        ("三、各品牌真实份额（数据来自 eBay 官方 brand 字段，非标题猜测）",
         ["品牌", "商品数", "占比%", "类型", "均价", "最低价", "最高价", "覆盖价格带数", "主要价格带"],
         to_rows(b_rows, ["品牌", "商品数", "占比%", "类型", "均价", "最低价", "最高价",
                          "覆盖价格带数", "主要价格带"])),
        ("四、brand 字段原始取值分布（含白牌与卖家乱填）",
         ["brand 字段值", "条数", "归类"],
         to_rows(b_raw, ["brand 字段值", "条数", "归类"])),
        ("五、辅助参考：标题品牌词提及率 ⚠️ 含兼容性词（如 for Samsung），不代表品牌份额",
         ["标题品牌词", "命中条数", "提及率%", "均价", "标题开头占位", "开头占位率%"],
         to_rows(tm_rows, ["标题品牌词", "命中条数", "提及率%", "均价",
                           "标题开头占位", "开头占位率%"])),
        ("六、辅助参考：各价格带的标题品牌词提及率",
         ["价格带", "商品数", "带标题品牌词条数", "提及率%"],
         to_rows(tm_occ, ["价格带", "商品数", "带标题品牌词条数", "提及率%"])),
    ])

    # ---------- 3. 关键词与标题 ----------
    ws = w.book.create_sheet("关键词与标题")
    kw_header = ["关键词", "出现条数", "占比%", "主要位置", "开头", "中间", "结尾",
                 "搜索价值", "差异化价值", "综合评分"]
    kw_body = [[r.get("关键词"), r.get("出现条数"), r.get("占比%"), r.get("主要位置"),
                r.get("开头位置数"), r.get("中间位置数"), r.get("结尾位置数"),
                r.get("搜索价值"), r.get("差异化价值"), r.get("综合评分")] for r in kw_rows]
    mod_rows = []
    for group, rows in (mods or {}).items():
        for r in rows:
            mod_rows.append([group, r.get("关键词"), r.get("出现条数"), r.get("占比%"),
                             r.get("综合评分")])
    def_group = [["品质相关", "决定质感与耐用性的词（waterproof / pro / bass…）"],
                 ["功能相关", "决定功能与兼容性的词（bluetooth / rechargeable / mic…）"],
                 ["场景/用途相关", "决定使用场景的词（sports / sleep / gaming…）"]]
    title_rows = [[i, t, len(t)] for i, t in enumerate(target_titles, 1)]
    note_rows = [[k, v] for k, arr in (notes or {}).items() for v in arr]
    write_sections(ws, [
        ("一、高频关键词分析（任务 2）", kw_header, kw_body),
        ("二、修饰词归类（任务 3）", ["修饰词类别", "关键词", "出现条数", "占比%", "综合评分"], mod_rows),
        ("三、修饰词类别说明", ["类别", "含义"], def_group),
        ("四、标题结构模板（任务 4）", ["模板", "支持条数", "类型"],
         [[t.get("模板"), t.get("支持条数"), t.get("类型")] for t in (templates or [])]),
        ("五、推荐商品标题 30 条（任务 8/9/10/11）", ["序号", "标题", "字符数"], title_rows),
        ("六、策略建议（任务 6/7）", ["类别", "建议"], note_rows),
    ])

    # ---------- 5. 基础统计 ----------
    ws = w.book.create_sheet("基础统计")
    write_sections(ws, [
        ("一、完整 title 重复（保留重复计数，任务 10 依据）",
         ["title", "count"], report.get("titles_exact") or []),
        ("二、title 词频", ["token", "count"], report.get("titles_tokens") or []),
        ("三、属性词频（前 N 位 item 的 item specifics 归并后）",
         ["属性", "属性出现次数", "值", "值次数"], report.get("spec_rows_flat") or []),
        ("四、主类目", ["category_id", "name", "count"],
         (report.get("category_stats") or {}).get("primary") or []),
        ("五、第二类目", ["category_id", "name", "count"],
         (report.get("category_stats") or {}).get("secondary") or []),
    ])
    print("  已导出 5 张子表：市场概况与价格 / 品牌壁垒 / 关键词与标题 / 采集明细 / 基础统计")

'''

src = src.replace(old_block, NEW + "\n")
open(P, "w", encoding="utf-8", newline="\n").write(src)
print("已替换 export_market_sheets 为 5 表版本")
print("旧块 %d 字符 → 新块 %d 字符" % (len(old_block), len(NEW)))
