# -*- coding: utf-8 -*-
"""eBay 关键词选品入口：采集 + 分析 + 导出。"""

import argparse
import json
import os
import re
import sys
import time
import traceback

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from analyze import build_report
from common_path import output_dir
from sites import SITES, get_site


def _safe_name(text):
    return re.sub(r"\W+", "_", text or "kw")[:40].strip("_") or "kw"


def _cell_value(v):
    """写进 Excel 时把纯数字转成真数字（否则 Excel 里是文本，不能求和/排序）。"""
    if isinstance(v, (int, float)) or v is None:
        return v
    s = str(v).strip()
    if not s:
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        if re.fullmatch(r"[-+]?\d*\.\d+", s):
            return float(s)
    except Exception:
        pass
    return v


def to_rows(data, keys):
    """按显式列序把 dict 行转成值列表。

    踩过的坑：直接把 dict 传给 write_sections，迭代出来的是**键**，
    结果整段写成 N 行表头（实测价格段 7 行、品牌占位 7 行全是表头）。
    """
    out = []
    for r in data or []:
        if isinstance(r, dict):
            out.append([r.get(k) for k in keys])
        else:
            out.append(list(r))
    return out


def write_sections(ws, sections):
    """把多段内容写进同一个工作表：段标题 + 表头 + 数据，列宽自适应。

    sections: [(段标题, 表头list, 行list), ...]；行可以是 list 也可以是 dict
    （dict 需由 to_rows 先转好）。
    """
    row = 1
    for title, header, rows in sections:
        if title:
            c = ws.cell(row=row, column=1, value=title)
            c.font = Font(bold=True, size=12)
            row += 1
        widths = {}
        if header:
            for j, h in enumerate(header, 1):
                c = ws.cell(row=row, column=j, value=h)
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="DDEBF7")
                widths[j] = len(str(h))
            row += 1
        for r in rows:
            if isinstance(r, dict):
                r = list(r.values())        # 兜底：dict 未转则按自身顺序取值
            for j, v in enumerate(r, 1):
                val = _cell_value(v)
                ws.cell(row=row, column=j, value=val)
                widths[j] = max(widths.get(j, 0), len(str(v)))
            row += 1
        row += 1            # 段间空一行
        for j, col_w in widths.items():
            ws.column_dimensions[get_column_letter(j)].width = min(46, max(9, col_w + 3))



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
    ad_sum = report.get("ad_summary") or {}
    ad_rows = report.get("ad_rows") or []
    n_items = report.get("item_count") or len(ad_rows and []) or 0
    ad_pct = ad_sum.get("广告位占比%")
    write_sections(ws, [
        ("一、市场概况", ["项", "值"], [
            ["关键词", report.get("keyword")],
            ["站点", report.get("site")],
            ["采集条数", report.get("item_count")],
            ["数据来源", "eBay 官方 Browse API（生产环境）"],
            ["广告位条数",
             "%s（%s%%）" % (ad_sum.get("广告位条数"), ad_pct)
             if ad_pct is not None else report.get("ad_count")],
            ["广告位均价", ad_sum.get("广告位均价")],
            ["全部商品均价", ad_sum.get("全部商品均价")],
            ["投放最凶价格带", ad_sum.get("投放最凶价格带")],
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
        ("三、各价格带的广告位占比（哪一段投广告最凶）",
         ["价格带", "商品数", "广告位条数", "广告位占比%", "自然位条数", "投放强度"],
         to_rows(ad_rows, ["价格带", "商品数", "广告位条数", "广告位占比%",
                           "自然位条数", "投放强度"])),
        ("四、广告位出现在第几位的分布", ["位置区间", "商品数", "广告位条数", "广告位占比%"],
         to_rows(report.get("ad_pos_rows") or [],
                 ["位置区间", "商品数", "广告位条数", "广告位占比%"])),
        ("五、广告位位次概览", ["指标", "值"],
         [[k, v] for k, v in (report.get("ad_pos_summary") or {}).items()]),
        ("六、价格分位", ["指标", "值(%s)" % cur], [
            ["p10", price_stat.get("p10")], ["p25", price_stat.get("p25")],
            ["p50 中位", price_stat.get("p50")], ["p75", price_stat.get("p75")],
            ["p90", price_stat.get("p90")], ["最低", price_stat.get("min")],
            ["最高", price_stat.get("max")],
            ["空档段", "、".join(price_stat.get("空档段") or []) or "无"],
            ["最稀疏段", price_stat.get("最稀疏段")],
        ]),
        ("七、口径说明", ["说明"], [
            ["占比% = 该段商品数 / 总商品数"],
            ["累计占比% = 从低价段往上累加"],
            ["竞争强度：≥30% 红海 / 20-30% 竞争激烈 / 10-20% 中等 / <10% 稀疏 / 0 空档（蓝海）"],
            ["价格段边界固定为 0-5/5-8/8-10/10-13/13-16/16-20/20+（按真实分位选定，见文档）"],
            ["广告位标记来自 eBay 官方 API 的 priorityListing 字段（实测与搜索页 promoted 一致）"],
            ["投放强度：广告位占比 ≥50% 广告最凶 / ≥25% 广告较多 / >0 较少 / 0 无广告"],
            ["位置区间按搜索结果位次每 10 位分桶，用于回答『前 10 位含广告』这条需求"],
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



EXCEL_CELL_MAX = 32000     # Excel 单元格硬上限 32767 字符，留点余量


def _clip_long_cells(df, limit=EXCEL_CELL_MAX):
    """截断超长单元格，并**显式标注**被截断。

    踩过的坑一：eBay 官方 API 的 `description` 是整页 HTML（实测最长 310,582 字符），
    远超 Excel 单元格上限 32767。不处理的话 openpyxl 对**每一条**超长记录都吐一个
    UserWarning，一次 200 条能刷十几屏警告，把 bat 窗口里的正常日志全淹掉。

    踩过的坑二：**不能靠 `dtype == object` 判断字符串列**。
    pandas 2.x 里字符串列是 object，但 **pandas 3.0 改成了 `str` dtype**，
    共享目录那个运行时正是 3.0.3 —— 于是第一版判断全部失效、警告照旧刷屏
    （本地 pandas 2.1.4 测不出来）。这里改成"该列只要有字符串就处理"，与 dtype 无关。

    完整内容仍在同名的 .json 里（JSON 先写，不受影响）。
    """
    for col in list(df.columns):
        s = df[col]
        try:
            has_str = s.map(lambda v: isinstance(v, str)).any()
        except Exception:
            has_str = False
        if not has_str:
            continue
        df[col] = s.map(
            lambda v: (v[:limit] + "…【已截断，原文 %d 字符，完整内容见同名 .json】" % len(v))
            if isinstance(v, str) and len(v) > limit else v)
    return df


USAGE_FILE = "_api用量.json"


def _record_api_usage(calls, dir_path):
    """本地累计当日 eBay API 请求量，返回今日累计次数。

    为什么要自己记：**eBay 不提供额度查询**——
      - Browse API 响应头里没有任何 rate-limit 字段（实测打过完整响应头）
      - 官方那个 getRateLimits 接口在公网全 404（只在 eBay 内网文档里）
      - 所以只能去开发者后台看，或者自己记账
    这里记的是**本工具经手的量**，不等于整个 app 的总量（如果还有别的程序用同一套密钥，
    那些不在计数里）—— 这一点在输出里会写明，不装作是权威数字。
    """
    today = time.strftime("%Y-%m-%d")
    path = os.path.join(dir_path, USAGE_FILE)
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    day = data.get(today) or {"search": 0, "getItem": 0, "token": 0, "其他": 0, "运行段数": 0}
    day["search"] = day.get("search", 0) + (calls.get("search") or 0)
    day["getItem"] = day.get("getItem", 0) + (calls.get("getItem") or 0)
    day["token"] = day.get("token", 0) + (calls.get("token") or 0)
    for k, v in (calls or {}).items():
        if k not in ("search", "getItem", "token"):
            day["其他"] = day.get("其他", 0) + (v or 0)
    day["运行段数"] = day.get("运行段数", 0) + 1
    day["计费请求"] = day["search"] + day["getItem"] + day.get("其他", 0)
    day["更新时间"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data[today] = day
    try:
        _atomic_write_json(path, data)
    except Exception:
        pass
    return day


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def export_report(report, store="", out_dir=None):
    """导出一次采集的结果。

    文件名口径（2026-09-15 用户要求）：**关键词 + 时间 + 站点**，例如
        wireless_earbuds_20260915_094620_uk.xlsx
    同一关键词同站点重跑不会互相覆盖（时间戳精确到秒）。
    """
    out = out_dir or output_dir()
    os.makedirs(out, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = "%s_%s_%s" % (_safe_name(report.get("keyword")),
                         ts,
                         report.get("site") or "site")
    json_path = os.path.join(out, base + ".json")
    xlsx_path = os.path.join(out, base + ".xlsx")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    rec = pd.DataFrame({"推荐title": report.get("recommended_titles") or []})
    items = pd.DataFrame(report.get("items") or [])
    items = _clip_long_cells(items)      # description 是整页 HTML，必须先截断
    if not items.empty:
        items = items.copy()
        if "price_max" in items.columns:
            items["price_range_display"] = items.apply(
                lambda r: ("" if r.get("price") is None else
                           ("%.2f" % r["price"] if r.get("price_max") in (None, r.get("price"))
                            else "%.2f~%.2f" % (r["price"], r["price_max"]))),
                axis=1,
            )
        if "item_specifics" in items.columns:
            items["item_specifics"] = items["item_specifics"].map(
                lambda rows: "; ".join("%s=%s" % (x.get("name"), x.get("value")) for x in (rows or []))
            )
        if "leaf_category_ids" in items.columns:
            items["leaf_category_ids"] = items["leaf_category_ids"].map(
                lambda ids: ",".join(str(x) for x in (ids or []))
            )
        if "has_secondary_category" in items.columns:
            items["可加第二类目"] = items["has_secondary_category"].map(lambda v: "是" if v else "")
        # 广告位：补中文可读列 + 标记来源列（来源=priorityListing 说明取自官方 API 字段）
        # 非广告位也显式写"否"，避免空单元格被下游当成"没查"（需求第 6 条要求能标记是否广告位）
        if "is_sponsored" in items.columns:
            items["是否广告位"] = items["is_sponsored"].map(lambda v: "是" if v else "否")
            items["广告位标记来源"] = items["is_sponsored"].map(
                lambda v: "priorityListing" if v else "无广告位标记")
        # 把下游对接需要的标识列提到最前面（按 item id 去别的站取数）；
        # 广告位相关的机读列 + 中文列放在一起，避免中文列沉到最后一列找不到
        front = [c for c in ("position", "item_id", "legacy_item_id", "item_url",
                             "是否广告位", "is_sponsored", "广告位标记来源",
                             "title", "price", "price_max", "price_range_display",
                             "currency", "image_url", "image_count",
                             "leaf_category_ids", "category_path")
                 if c in items.columns]
        items = items[front + [c for c in items.columns if c not in front]]
    title_exact = pd.DataFrame(report.get("titles_exact") or [])
    title_tokens = pd.DataFrame(report.get("titles_tokens") or [])
    spec_rows = []
    for block in report.get("specifics") or []:
        for v in block.get("values") or []:
            spec_rows.append({
                "属性": block["name"],
                "属性出现次数": block["total"],
                "值": v["value"],
                "值次数": v["count"],
            })
    specifics = pd.DataFrame(spec_rows)
    price = report.get("price") or {}
    price_summary = pd.DataFrame([
        {"指标": k, "值": price.get(k)}
        for k in ("count", "currency", "min", "p20", "p50", "p80", "max", "suggest_price")
    ])
    price_bins = pd.DataFrame(price.get("bins") or [])
    cat = report.get("category") or {}
    cat_primary = pd.DataFrame(cat.get("primary") or [])
    cat_secondary = pd.DataFrame(cat.get("secondary") or [])
    overview = pd.DataFrame([
        {"项": "关键词", "值": report.get("keyword")},
        {"项": "站点", "值": report.get("site")},
        {"项": "采集条数", "值": report.get("item_count")},
        {"项": "广告条数", "值": report.get("ad_count")},
        {"项": "推荐末级类目ID", "值": cat.get("recommend_leaf_id")},
        {"项": "推荐末级类目名", "值": cat.get("recommend_leaf_name")},
        {"项": "含第二类目条数", "值": cat.get("dual_category_count")},
        {"项": "建议价格(中位)", "值": price.get("suggest_price")},
    ])

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        # ---- 市场分析段（对齐《市场调研.xlsx / 输出要求》）----
        market = report.get("market") or {}
        if market:
            export_market_sheets(
                {**report,
                 "price_bands": market.get("price_bands") or [],
                 "price_stat": market.get("price_stat") or {},
                 "currency": (report.get("price") or {}).get("currency", ""),
                 "language": market.get("language") or {},
                 "category": market.get("category") or {},
                 "category_stats": report.get("category") or {},
                 "ad_rows": market.get("ad_rows") or [],
                 "ad_summary": market.get("ad_summary") or {},
                 "ad_pos_rows": market.get("ad_pos_rows") or [],
                 "ad_pos_summary": market.get("ad_pos_summary") or {},
                 },
                w,
                market.get("keyword_rows") or [],
                market.get("brand") or {"brand_rows": [], "spec_rows": [],
                                        "band_rows": [], "summary": {}},
                market.get("modifiers") or {},
                market.get("templates") or [],
                market.get("notes") or {},
                market.get("target_titles") or [],
            )
        # ---- 采集与基础段（内容已合并进 5 张表，这里只写采集明细 + 可选直方图）----
        items.to_excel(w, sheet_name="采集明细", index=False)
        refine = pd.DataFrame(report.get("aspect_refinements") or [])
        if not refine.empty:
            refine.to_excel(w, sheet_name="搜索属性直方图", index=False)
        # 无 market 段时（兼容旧调用）退回分散子表
        if not market:
            rec.to_excel(w, sheet_name="推荐title", index=False)
            overview.to_excel(w, sheet_name="总览", index=False)
            title_exact.to_excel(w, sheet_name="完整title重复", index=False)
            title_tokens.to_excel(w, sheet_name="title词频", index=False)
            specifics.to_excel(w, sheet_name="属性词频", index=False)
            cat_primary.to_excel(w, sheet_name="主类目", index=False)
            cat_secondary.to_excel(w, sheet_name="第二类目", index=False)

    print("  JSON: %s" % json_path)
    print("  Excel: %s" % xlsx_path)
    return xlsx_path


def build_market_report(report, items, keyword, spec_stats, target=30):
    """按《市场调研.xlsx / 输出要求》算市场分析段，并把推荐标题换成新实现的 30 条。

    品牌壁垒口径（2026-09-15 起）：
      - **主口径** structured：用 eBay 官方 `brand` 字段 / item_specifics.Brand
      - **辅助** title_mentions：标题品牌词提及率（含兼容性词，不代表份额）
    """
    from analyze import detect_brands, tokenize
    import report_market as rm

    titles = [it.get("title") or "" for it in items]
    seqs = [tokenize(t) for t in titles if t.strip()]

    lang = rm.detect_language(titles)
    cat = rm.detect_product_category(titles, keyword, spec_stats)
    price_bands, price_stat = rm.build_price_table(items)
    ad_rows, ad_summary = rm.ad_slot_by_band(items)
    ad_pos_rows, ad_pos_summary = rm.ad_slot_positions(items, top_n=10, bucket=10)
    brands = detect_brands(titles)
    structured = rm.brand_from_structured(items)
    tm_rows, tm_occ = rm.title_brand_mentions(items, brands)
    brand_summary = structured["summary"]
    kw_rows = rm.keyword_analysis(titles, keyword, spec_stats, top_n=20)
    mods = rm.modifier_analysis(kw_rows)
    templates = rm.structure_templates(seqs, top=5)
    notes = rm.strategy_notes(keyword, kw_rows, brands, price_bands, price_stat,
                              titles, templates, report.get("ad_count", 0))
    # 品牌壁垒结论并入策略建议（相关内容合并）
    if brand_summary:
        notes["品牌壁垒要点"] = [
            "主口径（eBay 官方 brand 字段）：真品牌占位 %s%%、白牌 %s%%、品牌种类 %s 种；%s"
            % (brand_summary.get("真品牌占位率%"), brand_summary.get("白牌占比%"),
               brand_summary.get("真品牌种类数"), brand_summary.get("结论")),
            "辅助（标题品牌词提及）：%s ｜ 注意标题品牌词含兼容性词（for Samsung 等），不代表份额"
            % "、".join(r["标题品牌词"] for r in tm_rows[:5]),
        ]
    # 广告位位置分布并入平台建议（这些结论直接在表里给出，不让人自己去数）
    if ad_pos_summary.get("广告位总条数"):
        hot_seg = max(ad_pos_rows, key=lambda r: r["广告位条数"]) if ad_pos_rows else None
        tips = notes.setdefault("eBay平台建议", [])
        tips.append(
            "广告位位置分布：首个广告位在第 %s 位，主要集中在第 %s 段"
            "（该段 %d 条广告，占 %.0f%%）；前 10 位里 %s 条广告（%.0f%%）"
            % (ad_pos_summary.get("首个广告位在第几位"),
               hot_seg["位置区间"] if hot_seg else "-",
               hot_seg["广告位条数"] if hot_seg else 0,
               hot_seg["广告位占比%"] if hot_seg else 0.0,
               ad_pos_summary.get("前10位里广告位条数"),
               ad_pos_summary.get("前10位广告位占比%") or 0.0))
        zero_segs = [r["位置区间"] for r in ad_pos_rows if r["广告位条数"] == 0]
        if zero_segs:
            tips.append("第 %s 段本次没有广告位（纯自然位竞争，新品可从这些位次切入）"
                        % "、".join(zero_segs))
    target_titles = rm.recommend_titles(keyword, titles, spec_stats, kw_rows,
                                        templates, brands, target=target)
    return {
        "language": lang,
        "category": cat,
        "price_bands": price_bands,
        "price_stat": price_stat,
        "ad_rows": ad_rows,
        "ad_summary": ad_summary,
        "ad_pos_rows": ad_pos_rows,
        "ad_pos_summary": ad_pos_summary,
        "keyword_rows": kw_rows,
        "modifiers": mods,
        "templates": templates,
        "notes": notes,
        "target_titles": target_titles,
        "brand": {
            "structured": structured,
            "title_mentions": tm_rows,
            "title_occ": tm_occ,
            # 旧字段名保留，避免其它引用断掉
            "brand_rows": structured["brand_rows"],
            "summary": brand_summary,
            "spec_rows": structured["spec_rows"],
            "band_rows": structured["occupancy_by_band"],
        },
    }


def upgrade_titles_with_llm(market, items, keyword, site, target=30, verbose=True):
    """用 DeepSeek 生成最终标题，替换规则版。

    - 素材全部来自本地已算好的真实数据（关键词评分/修饰词/模板/竞品标题/属性）
    - 硬约束由 prompt + 校验函数双重把关（≤80、尽量 70~80、无逗号、去品牌、
      同标题不重复词、重复率>2 的竞品标题原样保留）
    - **失败必须回退规则版**，不能中断流水线
    """
    import llm_titles

    titles = [x.get("title") or "" for x in items]
    from collections import Counter
    repeated = [t for t, c in Counter(titles).most_common() if c > 2]
    from analyze import detect_brands
    brands = detect_brands(titles)
    try:
        res, meta = llm_titles.generate_titles_llm(
            keyword, site, items, market.get("keyword_rows") or [],
            market.get("modifiers") or {}, market.get("templates") or [],
            brands, repeated, target=target, verbose=verbose)
    except Exception as exc:
        print("  [LLM] 异常，回退规则版：%s" % str(exc)[:180])
        return market, {"used": False, "reason": str(exc)[:200]}
    if not res:
        print("  [LLM] 未产出合规标题（%s），回退规则版" % meta)
        return market, {"used": False, "reason": str(meta)[:200]}
    market["target_titles"] = res
    market["titles_source"] = "deepseek"
    market["llm_meta"] = meta
    market["repeated_titles"] = repeated
    lens = [len(t) for t in res]
    print("  [LLM] 采用 DeepSeek 标题 %d 条（字符 %d~%d，中位 %d）"
          % (len(res), min(lens), max(lens), sorted(lens)[len(lens) // 2]))
    return market, {"used": True, "meta": meta}


def run_ziniao(args, keyword, site):
    """紫鸟链路（已封存）。

    代码移至 01_关键词选品/99_归档/紫鸟采集_20260915/，此处按归档路径加载，
    保证 --mode ziniao 仍可运行（备用链路）。默认生产方式已改为 --mode api。
    """
    import sys as _sys
    _archive = os.path.normpath(os.path.join(HERE, "..", "99_归档", "紫鸟采集_20260915", "脚本"))
    if _archive not in _sys.path:
        _sys.path.insert(0, _archive)
    print("  [提示] 紫鸟链路已封存，代码在 99_归档/紫鸟采集_20260915/；"
          "默认生产方式请用 --mode api")
    from ziniao_runtime import (
        close_browser, connect_cdp, exit_ziniao, get_browser_list, kill_ziniao,
        match_store, open_store, start_ziniao, wait_for_server,
    )
    from collect_ziniao import collect_on_page
    from playwright.sync_api import sync_playwright

    if not args.store:
        raise RuntimeError("紫鸟模式请用 --store 指定店铺名")

    print("[1] 关闭现有紫鸟...")
    kill_ziniao()
    print("[2] 启动紫鸟 webdriver...")
    api_port = start_ziniao()
    pw = None
    payload = {"items": []}
    try:
        if not wait_for_server(api_port):
            raise RuntimeError("紫鸟服务启动超时")
        all_stores = get_browser_list(api_port)
        print("  店铺数: %d" % len(all_stores))
        zn_name = match_store(all_stores, args.store)
        if not zn_name:
            names = ", ".join(sorted({s.get("browserName") for s in all_stores})[:30])
            raise RuntimeError("店铺 %s 未找到。现有: %s" % (args.store, names))
        store_info = {s.get("browserName"): s for s in all_stores}[zn_name]
        print("  命中店铺: %s" % zn_name)
        pw = sync_playwright().start()
        result = open_store(api_port, store_info.get("browserOauth", ""))
        debugging_port = result.get("debuggingPort")
        print("  debuggingPort: %s" % debugging_port)
        time.sleep(10)
        browser = connect_cdp(pw, debugging_port)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        time.sleep(5)
        payload = collect_on_page(page, keyword, site, args.max, args.detail)
        close_browser(api_port, store_info.get("browserOauth", ""), browser)
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        exit_ziniao(api_port)
        kill_ziniao()
    return payload


def run_api(args, keyword, site):
    """官方 eBay Browse API 采集（默认生产方式）。

    detail 语义：-1 = 全部条目都取详情（API 侧 200 条实测 100% 覆盖）；
                N>0 = 只取前 N 条；0 = 只搜索不取详情。
    """
    from collect_ebay_api import EbayApi
    api = EbayApi(site=site, env=args.env, verbose=True)
    detail_all = args.detail < 0
    n_detail = args.max if detail_all else min(args.detail, args.max)
    if detail_all or n_detail > 0:
        print("  逐条取详情：%d 条（实测平均 1.24s/条）" % n_detail)
    return api.collect(keyword, max_items=args.max, detail=(n_detail > 0),
                       workers=getattr(args, "workers", 8))


def run_json(args):
    if not args.from_json or not os.path.isfile(args.from_json):
        raise RuntimeError("json 模式请用 --from-json 指向已有采集文件")
    with open(args.from_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"items": data}
    if data.get("items"):
        return data
    raise RuntimeError("JSON 里没有 items")


def run_one(args, keyword, site, out_dir=None, index=None, total=None):
    """跑完一个 (关键词 × 站点) 组合。返回结果 dict（不抛异常，失败也返回状态）。

    拆出来是为了支持"一次跑多个关键词 / 多个站点"：每个组合独立成一份产物，
    文件名 = 关键词_时间_站点，互不覆盖。
    """
    tag = "[%d/%d] " % (index, total) if index and total else ""
    t0 = time.time()
    print("\n" + "-" * 68)
    print("%s站点 %s ｜ 关键词 %s ｜ 开始 %s"
          % (tag, site.upper(), keyword, time.strftime("%H:%M:%S")))
    print("-" * 68)
    res = {"keyword": keyword, "site": site, "ok": False, "xlsx": "",
           "items": 0, "error": "", "seconds": 0.0, "titles": 0}

    # ---- 采集 ----
    try:
        if args.mode == "ziniao":
            payload = run_ziniao(args, keyword, site)
        elif args.mode == "api":
            payload = run_api(args, keyword, site)
        else:
            payload = run_json(args)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print("采集失败: %s" % e)
        print(traceback.format_exc())
        res["error"] = "采集失败: %s" % str(e)[:200]
        res["seconds"] = time.time() - t0
        return res

    items = payload.get("items") or []
    if not items:
        print("未采集到数据")
        res["error"] = "未采集到数据"
        res["seconds"] = time.time() - t0
        return res
    res["items"] = len(items)
    print("采集到 %d 条" % len(items))
    today = None
    if payload.get("api_calls"):
        print("API 调用统计: %s" % payload["api_calls"])
        usage_dir = getattr(args, "log_dir", "") or out_dir
        if usage_dir:
            try:
                today = _record_api_usage(payload["api_calls"], usage_dir)
                print("API 请求：本次 %d 次 ｜ 今日累计 %d 次（本地计数）"
                      % ((payload["api_calls"].get("search") or 0)
                         + (payload["api_calls"].get("getItem") or 0),
                         today.get("计费请求", 0)))
            except Exception as exc:
                print("（今日用量统计写入失败，不影响采集：%s）" % str(exc)[:80])

    # ---- 分析 ----
    report = build_report(
        keyword, site, items, args.recommend, args.detail,
        extra_refinements=payload.get("aspect_refinements") or [],
    )
    report["mode"] = args.mode
    report["store"] = args.store
    report["aspect_refinements"] = payload.get("aspect_refinements") or []
    if payload.get("dominant_category_id") and not report["category"].get("recommend_leaf_id"):
        report["category"]["recommend_leaf_id"] = payload["dominant_category_id"]

    spec_rows = []
    for it in items:
        for s in it.get("item_specifics") or []:
            spec_rows.append({"name": s.get("name"), "value": s.get("value"),
                              "position": it.get("position")})
    from analyze import specifics_freq
    spec_stats = report.get("specifics") or specifics_freq(spec_rows)
    market = build_market_report(report, items, keyword, spec_stats,
                                 target=max(30, args.recommend))
    llm_info = {"used": False, "reason": "not attempted"}
    if not getattr(args, "no_llm", False):
        try:
            market, llm_info = upgrade_titles_with_llm(
                market, items, keyword, site, target=max(30, args.recommend))
        except Exception as exc:
            print("  [LLM] 升级失败，保留规则版标题：%s" % str(exc)[:160])
            llm_info = {"used": False, "reason": str(exc)[:200]}
    report["llm_titles"] = llm_info
    report["market"] = market
    report["spec_rows_flat"] = spec_rows
    if market.get("target_titles"):
        report["recommended_titles"] = market["target_titles"]

    # ---- 导出 ----
    xlsx_path = export_report(report, store=args.store or args.mode, out_dir=out_dir)

    # ---- 结果摘要（详细日志）----
    print("\n推荐末级类目ID: %s %s" % (
        report["category"].get("recommend_leaf_id"),
        report["category"].get("recommend_leaf_name") or ""))
    print("价格中位: %s %s" % (
        (report["price"] or {}).get("suggest_price"),
        (report["price"] or {}).get("currency") or ""))
    pb = market.get("price_stat") or {}
    print("价格分位: p25=%s p50=%s p75=%s ｜ 最稀疏段=%s"
          % (pb.get("p25"), pb.get("p50"), pb.get("p75"), pb.get("最稀疏段")))
    bs = (market.get("brand") or {}).get("summary") or {}
    print("品牌壁垒: 真品牌占位 %s%%（白牌 %s%%、品牌 %s 种）｜ %s"
          % (bs.get("真品牌占位率%"), bs.get("白牌占比%"),
             bs.get("真品牌种类数"), bs.get("结论")))
    ad = market.get("ad_summary") or {}
    print("广告位: %s 条（%s%%）｜ %s"
          % (ad.get("广告位条数"), ad.get("广告位占比%"), ad.get("投放最凶价格带")))
    titles = report.get("recommended_titles") or []
    print("推荐 title %d 条（来源 %s）:"
          % (len(titles), "DeepSeek" if llm_info.get("used") else "规则版兜底"))
    for i, t in enumerate(titles, 1):
        print("  %2d. %s" % (i, t))

    res.update({"ok": True, "xlsx": xlsx_path, "titles": len(titles),
                "api_calls": payload.get("api_calls") or {},
                "seconds": time.time() - t0})
    return res


def _tee_console(log_path):
    """把控制台输出同时写一份到日志文件（壳程序要看详细日志，但也得留档）。

    用 contextlib.redirect_stdout 换掉 sys.stdout，**不缓冲**（每行 flush），
    这样 bat 窗口里能实时看到进度，而不是跑完才一次性刷出来。
    日志文件写失败不影响主流程（只警告）。
    """
    import contextlib

    if not log_path:
        return contextlib.nullcontext()

    class _Tee(object):
        def __init__(self, original, fh):
            self.original = original
            self.fh = fh

        def write(self, data):
            if not data:
                return 0
            self.original.write(data)
            try:
                self.fh.write(data)
            except Exception:
                pass
            return len(data)

        def flush(self):
            try:
                self.original.flush()
            except Exception:
                pass
            try:
                self.fh.flush()
            except Exception:
                pass

        def isatty(self):
            return False

    @contextlib.contextmanager
    def _cm():
        try:
            fh = open(log_path, "w", encoding="utf-8")
        except Exception as exc:
            print("  [警告] 日志文件打不开（%s），只在控制台输出" % exc)
            yield
            return
        original = sys.stdout
        sys.stdout = _Tee(original, fh)
        try:
            yield
        finally:
            sys.stdout = original
            try:
                fh.close()
            except Exception:
                pass

    return _cm()


# 复制粘贴常见的**零宽/隐形字符**：BOM、零宽空格、零宽非连接符、零宽连接符、词连接符。
# 这些要**删掉**。
# 注意：不换行空格(\xa0)、全角空格(\u3000) 属于**空白**，要替换成普通空格而不是删掉 ——
# 删掉会把 "wireless\xa0earbuds" 粘成 "wirelessearbuds"，等于拿一个不存在的词去搜。
# （这个区分有单测钉住）
_INVISIBLE_CHARS = dict.fromkeys(map(ord, "\ufeff\u200b\u200c\u200d\u2060"), None)


def _clean_query(text):
    """清掉复制粘贴带进来的隐形字符，并把连续空白压成一个空格。

    踩过的坑：从 Excel / 聊天窗口复制关键词，很常见会带上 **U+FEFF（BOM）**
    或 U+200B（零宽空格）。Python 的 `str.strip()` **不会**去掉它们
    （它们不属于 Unicode 空白），于是"空关键词"变成"有 1 个关键词"，
    一路跑到 eBay 才报 `HTTP 400 errorId 12023`，报错还完全看不出原因。

    实测复现：输入一个空行（管道里被前面加了 BOM）→
    参数确认里显示"关键词 : ﻿（1 个）"，肉眼什么都看不见。

    处理口径：零宽字符**删掉**；不换行空格/全角空格/连续空白**并成一个普通空格**。
    """
    if text is None:
        return ""
    t = str(text).translate(_INVISIBLE_CHARS)
    t = re.sub(r"\s+", " ", t)      # \s 含 \xa0、\u3000，都会变成普通空格
    return t.strip()


def _split_keywords(value):
    """拆多关键词：**只按逗号/分号/竖线/换行拆，绝不按空格拆**。

    踩过的坑：关键词绝大多数是多词的（`wireless earbuds` 是一个关键词，不是两个），
    早期按空格拆会把 `wireless earbuds` 拆成两次采集 —— 产物变成
    `wireless_..._uk.xlsx` + `earbuds_..._uk.xlsx`，完全错。
    """
    if not value:
        return []
    for ch in (",", "，", ";", "；", "|", "\n", "\r", "\t"):
        value = value.replace(ch, "\x00")
    return [x for x in (_clean_query(p) for p in value.split("\x00")) if x]


def _split_sites(value):
    """拆多站点：站点码不含空格，所以空格也能当分隔符（uk,us / uk us 都行）。"""
    out = []
    for part in _split_keywords(value):
        out.extend(x for x in part.split(" ") if x.strip())
    return [x.lower() for x in out if x]


def main(argv=None):
    p = argparse.ArgumentParser(description="eBay 关键词选品：200 条 title + 属性/类目/价格段 + 30 条推荐标题")
    p.add_argument("--mode", choices=("api", "ziniao", "json"), default="api",
                   help="api=官方 Browse API（默认、生产用）；"
                        "ziniao=紫鸟浏览器（已封存，备用）；json=只分析已有采集结果")
    p.add_argument("--store", default="", help="紫鸟店铺名")
    p.add_argument("--keyword", required=True,
                   help="关键词；多个用**逗号**分隔（如 \"wireless earbuds,phone case\"）。"
                        "多词关键词不用加引号也不用逗号，空格原样保留")
    p.add_argument("--site", default="", help="站点: %s" % ", ".join(sorted(SITES)))
    p.add_argument("--sites", default="",
                   help="多站点用逗号/空格分隔（如 uk,us,de）；与 --site 等效，二者都填会合并")
    p.add_argument("--max", type=int, default=200,
                   help="每个组合取多少条（默认 200 = eBay Browse API 单页上限，"
                        "一次请求就能拿满；>200 会自动翻页）")
    p.add_argument("--detail", type=int, default=-1,
                   help="取详情的条数。-1=全部（API 模式默认，实测 100%% 覆盖）；"
                        "0=不取详情（紫鸟模式默认）；N>0=只取前 N 条")
    p.add_argument("--recommend", type=int, default=20)
    p.add_argument("--from-json", dest="from_json", default="")
    p.add_argument("--workers", type=int, default=8,
                   help="并发取详情的线程数（默认 8，上限 16；1=串行）。"
                        "实测 8 线程：120 条 145s → 11.5s；200 条约 20s")
    p.add_argument("--env", choices=("sandbox", "production"), default="production",
                   help="官方 API 环境：默认 production；沙箱只有测试数据")
    p.add_argument("--out-dir", dest="out_dir", default="",
                   help="产物目录（默认工程内的 输出/；壳程序会指到单独文件夹）")
    p.add_argument("--log-dir", dest="log_dir", default="",
                   help="把控制台日志同时写一份到该目录（每次运行一个 txt）")
    p.add_argument("--no-llm", action="store_true",
                   help="不用 DeepSeek 生成标题（默认会用；LLM 负责品牌词判断与清洗，"
                        "失败自动回退规则版拼装）")
    args = p.parse_args(argv)

    keywords = _split_keywords(args.keyword)
    sites = []
    for s in _split_sites(args.site) + _split_sites(args.sites):
        if s not in sites:
            sites.append(s)
    if not keywords:
        print("未提供关键词")
        return 1
    if not sites:
        sites = ["us"]
    for s in sites:
        get_site(s)          # 站点码非法就早点报错，别等跑到一半
    for k in keywords:
        if not _safe_name(k):
            print("关键词 %r 无法作为文件名，请换个词" % k)
            return 1

    out_dir = args.out_dir or output_dir()
    os.makedirs(out_dir, exist_ok=True)
    log_path = ""
    if args.log_dir:
        os.makedirs(args.log_dir, exist_ok=True)
        log_path = os.path.join(args.log_dir, "关键词选品_%s.log"
                                % time.strftime("%Y%m%d_%H%M%S"))

    with _tee_console(log_path):
        print("=" * 68)
        print("eBay 关键词选品")
        print("  关键词   %s（%d 个）" % ("、".join(keywords), len(keywords)))
        print("  站点     %s（%d 个）" % ("、".join(s.upper() for s in sites), len(sites)))
        print("  组合数   %d 个（%d 关键词 × %d 站点）"
              % (len(keywords) * len(sites), len(keywords), len(sites)))
        print("  模式     %s ｜ 环境 %s ｜ 条数 %d ｜ 并发 %d ｜ 详情 %s"
              % (args.mode, getattr(args, "env", "-"), args.max,
                 getattr(args, "workers", 8),
                 "全部" if args.detail < 0 else args.detail))
        print("  产物目录 %s" % out_dir)
        if log_path:
            print("  日志文件 %s" % log_path)
        print("  开始时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
        print("=" * 68)

        results = []
        t_all = time.time()
        pairs = [(k, s) for k in keywords for s in sites]
        for i, (k, s) in enumerate(pairs, 1):
            try:
                results.append(run_one(args, k, s, out_dir=out_dir, index=i,
                                       total=len(pairs)))
            except KeyboardInterrupt:
                print("\n用户中断，已完成 %d/%d 个组合" % (i - 1, len(pairs)))
                break

        # ---- 总汇总 ----
        ok = [r for r in results if r["ok"]]
        fail = [r for r in results if not r["ok"]]
        print("\n" + "=" * 68)
        print("全部完成 ｜ 成功 %d / 失败 %d ｜ 总耗时 %.1f 秒"
              % (len(ok), len(fail), time.time() - t_all))
        print("=" * 68)
        print("%-28s %-6s %7s %8s %8s  %s"
              % ("关键词", "站点", "条数", "标题", "耗时s", "产物文件"))
        for r in results:
            print("%-28s %-6s %7s %8s %8.1f  %s"
                  % (r["keyword"][:28], r["site"].upper(),
                     r["items"] or "-", r["titles"] or "-", r["seconds"],
                     os.path.basename(r["xlsx"]) if r["xlsx"] else ("失败：" + r["error"])[:40]))
        if fail:
            print("\n⚠️ 有 %d 个组合失败，前面已打印各自原因（不影响其它组合）" % len(fail))

        # 用量小结（eBay 不给额度查询，只能自己记；这里给出本地口径）
        used = sum((r.get("api_calls") or {}).get("search", 0)
                   + (r.get("api_calls") or {}).get("getItem", 0) for r in results)
        if used:
            usage_dir = getattr(args, "log_dir", "") or out_dir
            day = {}
            try:
                path = os.path.join(usage_dir, USAGE_FILE)
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        day = (json.load(f) or {}).get(time.strftime("%Y-%m-%d")) or {}
            except Exception:
                day = {}
            print("\nAPI 请求量：本次 %d 次 ｜ 今日累计 %d 次（本地计数，"
                  "eBay 后台的数字才权威）" % (used, day.get("计费请求", used)))

        print("\n产物目录：%s" % out_dir)
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
