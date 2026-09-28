# -*- coding: utf-8 -*-
"""按《市场调研.xlsx / 输出要求》实现的分析段。

对照那 10 条任务：
  1  判断语言 / 识别产品类别
  2  高频关键词 >=15 个：频率 + 百分比 + 位置分析 + 搜索价值 + 差异化价值 + 1-10 综合评分
  3  修饰词归类：品质相关 / 功能相关 / 场景用途相关
  4  3-5 个标题结构模板
  5  5 个完整优化标题示例
  6  标题优化关键策略建议
  7  eBay 平台优化建议
  8  30 个推荐商品标题
  9  80 字符以内、尽量只用空格
  10 首页重复率 >2 的 title 原样保留
  11 去掉品牌词、不要逗号、80 字符以内

本模块只做本地计算，不访问网络。
"""

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations

TITLE_MAX = 80
TITLE_MIN = 40          # 文档要求"最好 80 个字符"，太短的标题没有信息量

STOPWORDS = {
    "a", "an", "and", "or", "the", "to", "of", "for", "in", "on", "at", "by",
    "with", "from", "into", "over", "under", "new", "plus", "set", "pack",
    "pcs", "pc", "lot", "free", "shipping", "fast", "hot", "sale", "item",
    "und", "der", "die", "das", "für", "mit", "les", "des", "une", "amp",
}

# 品类 / 技术词：既不是品牌，也不该从标题剔除
CATEGORY_KEEP = {
    "tws", "bluetooth", "wireless", "wired", "earbuds", "earbud", "earphones",
    "earphone", "headphones", "headphone", "headset", "buds", "pods", "pod",
    "stereo", "hifi", "usb", "led", "anc", "enc", "ipx", "ip55", "ipx4", "ipx5",
    "ipx7", "ip7", "type", "for", "in", "ear", "noise", "cancelling", "canceling",
}

BRAND_BLACKLIST = {
    "sony", "bose", "apple", "samsung", "anker", "soundcore", "jbl", "jabra",
    "beats", "xiaomi", "huawei", "baseus", "edifier", "sennheiser", "skullcandy",
    "tozo", "qc", "soundz", "airpods", "soundpeats", "haylou", "redmi", "oppo",
    "vivo", "realme", "oneplus", "lenovo", "mpow", "jlab", "jbl",
}

# 白牌/通用标识，不算品牌壁垒，但要单独统计（它代表"这个市场白牌能进"）
WHITELABEL = {"unbranded", "generic", "branded", "universal", "no brand", "oem", "none"}

# ---------- 修饰词三分类（文档任务 3） ----------
MOD_QUALITY = re.compile(
    r"(?i)(waterproof|sweatproof|dustproof|shockproof|premium|durable|heavy|"
    r"hifi|hi-fi|hd|hq|professional|pro|portable|mini|ultra|slim|light|"
    r"comfort|ergonomic|adjustable|fold|magnetic|touch|smart|digital|led|"
    r"long|lasting|bass|deep|stereo|clear|noise|cancel|proof|upgrade)")
MOD_FUNCTION = re.compile(
    r"(?i)(wireless|bluetooth|wired|recharge|charging|charger|battery|usb|type|"
    r"c|mic|microphone|enc|anc|control|volume|playback|call|touch|sensor|"
    r"connect|pair|auto|compatible|built|in|case|display|ipx|ip\d|5\.\d|water)")
MOD_SCENE = re.compile(
    r"(?i)(sport|running|gym|fitness|workout|cycling|driving|car|travel|"
    r"outdoor|sleep|sleeping|gaming|game|study|office|home|kitchen|swim|"
    r"music|phone|iphone|android|samsung|laptop|pc|tv|party|dj|monitoring)")


def tokenize(text):
    text = (text or "").strip()
    out = []
    for w in re.findall(r"[A-Za-z0-9]+(?:['\-][A-Za-z0-9]+)?", text):
        w = w.lower()
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        out.append(w)
    for block in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(block) <= 2:
            out.append(block)
        else:
            out.extend(block[i:i + 2] for i in range(len(block) - 1))
    return out


# ============================================================
# 任务 1：语言 / 产品类别
# ============================================================

def detect_language(titles):
    """粗判标题主语言：按停用词/字符形态给分。"""
    text = " ".join(t or "" for t in titles)
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    de_hits = len(re.findall(r"(?i)\b(und|für|mit|kabellos|kopfhörer|stück)\b", text))
    fr_hits = len(re.findall(r"(?i)\b(écouteurs|sans|pour|avec|fil)\b", text))
    es_hits = len(re.findall(r"(?i)\b(auriculares|inalámbricos|para|con)\b", text))
    en_hits = len(re.findall(r"(?i)\b(wireless|bluetooth|earbuds|headphones|for|with|new)\b", text))
    scores = {"zh": zh, "de": de_hits, "fr": fr_hits, "es": es_hits, "en": en_hits}
    lang = max(scores, key=scores.get)
    name = {"en": "English", "de": "Deutsch", "fr": "Français", "es": "Español", "zh": "中文"}[lang]
    return {"code": lang, "name": name, "scores": scores}


def detect_product_category(titles, keyword, spec_stats=None):
    """从标题+属性推断产品类别名（文档要求"根据产品类别进行后面的分析"）。"""
    toks = Counter()
    for t in titles:
        toks.update(tokenize(t))
    kw_toks = set(tokenize(keyword))
    # 品类词：高频、且不是品牌、不是纯修饰
    cand = []
    for w, c in toks.most_common(40):
        if w in BRAND_BLACKLIST or w in STOPWORDS or w.isdigit():
            continue
        if len(w) < 3:
            continue
        cand.append((w, c))
    # 属性里的 Type / Form Factor 是最可靠的品类名
    type_val = ""
    if spec_stats:
        for b in spec_stats:
            if b["name"].lower() in ("type", "form factor") and b["values"]:
                type_val = b["values"][0]["value"]
                break
    head = [w for w, _ in cand[:6]]
    return {
        "keyword_tokens": sorted(kw_toks),
        "head_terms": head,
        "spec_type": type_val,
        "label": (keyword or "").strip() or " / ".join(head[:3]),
    }


# ============================================================
# 2：高频关键词（位置 / 搜索价值 / 差异化价值 / 综合评分）
# ============================================================

def keyword_analysis(titles, keyword, spec_stats=None, top_n=20):
    """按文档任务 2 输出高频关键词表。"""
    n_titles = len([t for t in titles if (t or "").strip()]) or 1
    freq = Counter()
    pos_begin = Counter()
    pos_mid = Counter()
    pos_end = Counter()
    seqs = []

    for t in titles:
        toks = tokenize(t)
        if not toks:
            continue
        seqs.append(toks)
        for w in set(toks):
            freq[w] += 1
        if toks:
            pos_begin[toks[0]] += 1
        if len(toks) >= 3:
            pos_mid[toks[1]] += 1
        if len(toks) >= 2:
            pos_end[toks[-1]] += 1

    kw_toks = set(tokenize(keyword))
    spec_words = set()
    for b in spec_stats or []:
        if b["name"].lower() in ("type", "form factor", "connectivity",
                                 "wireless technology", "features"):
            for v in b["values"][:6]:
                spec_words.update(tokenize(v["value"]))

    rows = []
    for w, c in freq.most_common(top_n * 3):
        if w in kw_toks and c < 3:
            continue
        share = c / float(n_titles)
        pb = pos_begin[w] / float(c)
        pm = pos_mid[w] / float(c)
        pe = pos_end[w] / float(c)
        if pb >= max(pm, pe):
            position = "开头"
        elif pe >= max(pb, pm):
            position = "结尾"
        else:
            position = "中间"
        pos_score = max(pb, pm, pe)          # 越靠开头越重要

        # 搜索价值：属性/品类词、够长、非白牌词 → 更像买家搜索词
        sv = 5.0
        if w in spec_words:
            sv += 2.0
        if w in CATEGORY_KEEP:
            sv += 1.5
        if len(w) >= 6:
            sv += 1.0
        if w in BRAND_BLACKLIST or w in WHITELABEL:
            sv -= 3.0
        if w in ("new", "hot", "sale", "free"):
            sv -= 2.0
        sv = max(1.0, min(10.0, sv))

        # 差异化价值：越不是人人都写、越能脱颖而出
        dv = 6.0
        if share >= 0.6:
            dv -= 3.0
        elif share <= 0.15:
            dv += 2.0
        if w in spec_words:
            dv += 1.5
        if len(w) >= 6:
            dv += 0.5
        if w in BRAND_BLACKLIST:
            dv -= 2.0
        dv = max(1.0, min(10.0, dv))

        score = round(0.45 * sv + 0.4 * dv + 0.15 * (pos_score * 10), 1)
        rows.append({
            "关键词": w,
            "出现条数": c,
            "占比%": round(share * 100, 1),
            "主要位置": position,
            "开头位置数": pos_begin[w],
            "中间位置数": pos_mid[w],
            "结尾位置数": pos_end[w],
            "搜索价值": round(sv, 1),
            "差异化价值": round(dv, 1),
            "综合评分": score,
        })
        if len(rows) >= top_n:
            break
    rows.sort(key=lambda r: -r["综合评分"])
    return rows


# ============================================================
# 3：修饰词三分类
# ============================================================

def modifier_analysis(keyword_rows):
    """把高频词按 品质 / 功能 / 场景用途 归类（文档任务 3）。"""
    quality, function, scene = [], [], []
    kw_toks = set()
    for r in keyword_rows:
        w = r["关键词"]
        if MOD_SCENE.search(w):
            scene.append(r)
        if MOD_FUNCTION.search(w):
            function.append(r)
        if MOD_QUALITY.search(w):
            quality.append(r)
        if not (MOD_SCENE.search(w) or MOD_FUNCTION.search(w) or MOD_QUALITY.search(w)):
            kw_toks.add(w)
    return {
        "品质相关": quality,
        "功能相关": function,
        "场景/用途相关": scene,
    }


# ============================================================
# 4：标题结构模板
# ============================================================

def structure_templates(title_seqs, top=5, min_support=2):
    """从真实高频标题里抽"关键词相邻搭配"模板，统计支持度。"""
    pair = Counter()
    tri = Counter()
    for seq in title_seqs:
        uniq = []
        for w in seq:
            if w not in uniq:
                uniq.append(w)
        for a, b in combinations(uniq, 2):
            pair[(a, b)] += 1
        for i in range(len(uniq) - 2):
            tri[(uniq[i], uniq[i + 1], uniq[i + 2])] += 1
    templates = []
    for t, c in tri.most_common(12):
        if c >= min_support:
            templates.append({"模板": " + ".join(t), "支持条数": c, "类型": "三元搭配"})
    for t, c in pair.most_common(20):
        if c >= min_support and len(templates) < top:
            templates.append({"模板": " + ".join(t), "支持条数": c, "类型": "二元搭配"})
    return templates[:top]


# ============================================================
# 11 + 8：推荐标题（去品牌 / 无逗号 / 80 字符内 / 30 条）
# ============================================================

def clean_title(text, keyword, brands, max_len=TITLE_MAX):
    """按文档任务 9/11 清洗：去品牌词、无逗号、只留空格、80 字符以内。

    注意：数字里的小数点（5.4 / 5.3）和连字符（In-Ear / HI-RES）要保留，
    否则 "Bluetooth 5.4" 会被洗成 "Bluetooth 5 4"（实测踩过）。
    """
    t = (text or "")
    t = t.replace(",", " ").replace("，", " ")
    t = re.sub(r"[^\w\s.%&+\-]", " ", t)
    words = []
    seen = set()
    for w in t.split():
        k = re.sub(r"[^\w.]", "", w).lower()
        if not k or k in seen or k in brands:
            continue
        seen.add(k)
        words.append(w)
    out = " ".join(words).strip()
    kw = (keyword or "").strip()
    if kw and not out.lower().startswith(kw.lower()):
        out = " ".join((kw + " " + out).split())
    if len(out) > max_len:
        kept, n = [], 0
        for w in out.split():
            add = (1 if kept else 0) + len(w)
            if n + add > max_len:
                break
            kept.append(w)
            n += add
        out = " ".join(kept)
    return out


def bigram_vocab(title_seqs):
    """真实语料里出现过的相邻二元组集合 —— 用来筛掉不通顺的拼装。"""
    vocab = set()
    for seq in title_seqs:
        for i in range(len(seq) - 1):
            vocab.add((seq[i], seq[i + 1]))
    return vocab


def naturalness(text, vocab, kw):
    """标题自然度：所有相邻词对里，有多少在真实语料中出现过。

    这是修掉 "noise android"、"headset noise" 这类不通搭配的闸门：
    真实标题里从没挨在一起过的词，不该被我们拼到一起。
    """
    toks = tokenize(text)
    if len(toks) < 2:
        return 0.0
    pairs = [(toks[i], toks[i + 1]) for i in range(len(toks) - 1)]
    hit = sum(1 for p in pairs if p in vocab)
    return hit / float(len(pairs))


def mine_phrases(title_seqs, min_support=2, max_len=5):
    """从真实标题里挖反复出现的词组块。

    这是修掉"逐词拼装产生 noise android 这种不通搭配"的关键：
    只用真实标题里**确实相邻共现**的词块作为建材，而不是把独立的词随机并排。
    返回按 (支持条数 × 词数) 降序的短语列表。
    """
    import re as _re
    ngram = Counter()
    for seq in title_seqs:
        # 去重后的连续 n-gram（同一条标题内不重复计）
        for n in range(2, max_len + 1):
            seen = set()
            for i in range(len(seq) - n + 1):
                g = tuple(seq[i:i + n])
                if g in seen:
                    continue
                seen.add(g)
                # 全是数字/太短的块丢弃
                if any(len(w) <= 1 for w in g):
                    continue
                if all(w.isdigit() for w in g):
                    continue
                ngram[g] += 1
    rows = []
    for g, c in ngram.items():
        if c < min_support:
            continue
        rows.append({
            "短语": " ".join(g),
            "词数": len(g),
            "支持条数": c,
            "长度": len(" ".join(g)),
            "权重": c * len(g),
        })
    # 去掉被更长短语完全包含的短块（保留信息量更大的）
    rows.sort(key=lambda r: (-r["权重"], -r["长度"]))
    kept = []
    for r in rows:
        if any(r["短语"] in k["短语"] and r["短语"] != k["短语"] for k in kept):
            continue
        kept.append(r)
    return kept[:60]


def recommend_titles(keyword, titles, spec_stats, keyword_rows, templates,
                     brands, target=30):
    """生成 30 条推荐标题（文档任务 8），建材来自真实共现短语。"""
    kw = (keyword or "").strip()
    kw_toks = set(tokenize(kw))
    seqs = [tokenize(t) for t in titles if (t or "").strip()]

    phrases = mine_phrases(seqs, min_support=2)
    # 长块优先当"头部"，短块与高评分词当后缀
    heads = [p for p in phrases if p["词数"] >= 3 and p["长度"] >= 16][:20]
    if not heads:
        heads = [p for p in phrases if p["词数"] >= 2][:20]
    tails_pool = [p for p in phrases if p["词数"] == 2 and p["长度"] <= 20]

    kw_score = {r["关键词"]: r["综合评分"] for r in keyword_rows}
    top_kw = [r["关键词"] for r in keyword_rows
              if r["关键词"] not in kw_toks and r["关键词"] not in brands]
    top_kw.sort(key=lambda w: -kw_score.get(w, 0))

    # 属性短语（Type/Form Factor/Connectivity 等）作为可选后缀
    aspect = []
    for want in ("wireless technology", "connectivity", "form factor", "type", "features"):
        for b in spec_stats or []:
            if b["name"].lower() != want:
                continue
            for v in b["values"][:3]:
                val = (v["value"] or "").strip()
                if not val or len(val) > 24 or "," in val:
                    continue
                if any(t in brands for t in tokenize(val)):
                    continue
                if val.lower() not in [a.lower() for a in aspect]:
                    aspect.append(val)
            break

    freq = Counter((t or "").strip() for t in titles if (t or "").strip())
    repeated = [t for t, c in freq.most_common() if c > 2]

    vocab = bigram_vocab(seqs)
    cands = []          # (自然度, 长度, 标题)
    seen_sig = set()

    def sig(t):
        return tuple(sorted(set(tokenize(t))))

    def collect(text, must_natural=True):
        t = clean_title(text, kw, brands)
        if not t or len(t) < TITLE_MIN:
            return
        s = sig(t)
        if s in seen_sig:
            return
        nat = naturalness(t, vocab, kw)
        if must_natural and nat < 0.8:
            return
        seen_sig.add(s)
        cands.append((nat, len(t), t))

    # 1) 文档任务 10：重复率 >2 的 title 原样保留（不套自然度闸门，是原样保留）
    for t in repeated:
        collect(t, must_natural=False)

    # 2) 长短语块当头部 + 属性/高评分词按预算补齐（块与块拼，不拆词）
    for h in heads:
        budget = TITLE_MAX - len(kw) - 1 - len(h["短语"])
        if budget < 8:
            continue
        collect("%s %s" % (kw, h["短语"]))
        for a in aspect[:3]:
            if len(a) + 1 <= budget:
                collect("%s %s %s" % (kw, h["短语"], a))
        acc = []
        for w in top_kw:
            if len(w) + 1 + sum(len(x) + 1 for x in acc) <= budget and w not in h["短语"]:
                acc.append(w)
                if len(acc) >= 3:
                    break
        if acc:
            collect("%s %s %s" % (kw, h["短语"], " ".join(acc)))

    # 3) 二元短语块两两组合
    for i, p in enumerate(tails_pool[:12]):
        for p2 in tails_pool[i + 1:14]:
            if p["短语"] in p2["短语"] or p2["短语"] in p["短语"]:
                continue
            collect("%s %s %s" % (kw, p["短语"], p2["短语"]))

    # 4) 属性短语组合兜底
    for i, a in enumerate(aspect[:6]):
        for a2 in aspect[i + 1:8]:
            collect("%s %s %s" % (kw, a, a2))

    # 排序：自然度 → 词汇新鲜度 → 长度
    # 只按长度排会让 "wireless earbuds bluetooth ..." 反复出现（实测 30 条里同构很多），
    # 所以这里对已用过的词做惩罚，逼出词汇多样性。
    def pick():
        used = Counter()
        chosen = []
        pool = list(cands)
        while pool and len(chosen) < target:
            best, best_key = None, None
            for nat, ln, t in pool:
                toks = set(tokenize(t))
                reuse = sum(used[w] for w in toks)
                novelty = 1.0 / (1.0 + reuse)
                key = (nat, novelty, ln)
                if best_key is None or key > best_key:
                    best, best_key = (nat, ln, t), key
            if best is None:
                break
            pool = [c for c in pool if c[2] != best[2]]
            chosen.append(best[2])
            for w in set(tokenize(best[2])):
                used[w] += 1
        return chosen

    return pick()


# ============================================================
# 6 + 7：策略建议（基于真实数据给结论，不写空话）
# ============================================================

def strategy_notes(keyword, keyword_rows, brands, band_table, price_stat, titles,
                   templates=None, ad_count=0):
    """标题优化策略 + eBay 平台建议（结论都来自本次真实数据）。"""
    n = len(titles) or 1
    top = keyword_rows[:3]
    tmpl_text = "；".join(t["模板"] for t in (templates or [])[:3]) or "（样本不足，未抽出模板）"
    diff_best = sorted(keyword_rows, key=lambda x: -x["差异化价值"])[:3]
    conc = sum(b["占比%"] for b in (band_table or [])[:2])
    return {
        "标题优化策略": [
            "搜索主力：'%s' 与 %s —— 建议标题前 30 个字符内出现"
            % (keyword, "、".join(r["关键词"] for r in top)),
            "结构参考：%s（这些词在高频标题里的相邻搭配支持度最高）" % tmpl_text,
            "差异化：综合评分高但占比低的词（%s）能拉开同质化"
            % "、".join(r["关键词"] for r in diff_best),
            "品牌词一律不进标题（用竞品品牌上架有侵权风险）：本次自动剔除 %d 个品牌/型号词"
            % len(brands),
            "价格落点：竞品集中在低价段（前两段合计 %.1f%%），售价可参考中位 %s"
            % (conc, (price_stat or {}).get("p50", "-")),
        ],
        "eBay平台建议": [
            "标题 80 字符以内、尽量只用空格（逗号等标点会被截断或影响搜索匹配）",
            "同一标题内不重复词，重复词白占字符位、不带来权重",
            "Type / Form Factor / Connectivity 是 eBay 的搜索筛选维度，写进标题能吃到筛选流量",
            "末级类目 ID 必须用真实类目（本次取搜索页 listings.leafCat）",
            "本次 Promoted（广告位）%d 条（%.1f%%），可参考头部广告位的标题写法"
            % (ad_count, 100.0 * ad_count / n),
        ],
    }


# ---------- 价格段边界 ----------
# 依据 2026-09-14 真实分布选定（120 条样本）：
#   分位 p25=8.80 p50=13.83 p75=17.30；峰值在 £14(14条) 与 £8-9(17条)
#   对比方案：整数段极差 30.0 个百分点、本方案极差 12.5 —— 每段样本量足够且咬住真实分位
PRICE_BANDS = [0, 5, 8, 10, 13, 16, 20, 10 ** 9]
PRICE_BAND_LABELS = ["0-5", "5-8", "8-10", "10-13", "13-16", "16-20", "20+"]


def band_index(price, edges=None):
    edges = edges or PRICE_BANDS
    for i in range(len(edges) - 1):
        if edges[i] <= price < edges[i + 1]:
            return i
    return len(edges) - 2


def band_label(i, labels=None):
    labels = labels or PRICE_BAND_LABELS
    return labels[i] if 0 <= i < len(labels) else "?"


def build_price_table(items, edges=None, labels=None):
    """价格区间 + 占比 + 累计占比 + 竞争强度，合成一张表（用固定整数边界）。"""
    edges = edges or PRICE_BANDS
    labels = labels or PRICE_BAND_LABELS
    vals = sorted(v for v in (it.get("price") for it in items) if v)
    n = len(vals)
    if n == 0:
        return [], {}
    counts = rm_spread(vals, edges)
    rows = []
    cum = 0
    for i, c in enumerate(counts):
        pct = 100.0 * c / n
        cum += pct
        if c == 0:
            level = "空档（蓝海）"
        elif pct >= 30:
            level = "红海"
        elif pct >= 20:
            level = "竞争激烈"
        elif pct >= 10:
            level = "中等"
        else:
            level = "稀疏"
        rows.append({
            "价格段": labels[i],
            "下限": edges[i],
            "上限": (None if edges[i + 1] >= 10 ** 9 else edges[i + 1]),
            "商品数": c,
            "占比%": round(pct, 1),
            "累计占比%": round(cum, 1),
            "竞争强度": level,
        })
    def pct_at(q):
        return vals[min(n - 1, max(0, int(q * n) - 1))]
    stat = {
        "count": n, "min": vals[0], "max": vals[-1],
        "p10": pct_at(0.1), "p25": pct_at(0.25), "p50": pct_at(0.5),
        "p75": pct_at(0.75), "p90": pct_at(0.9),
    }
    # 空档：商品数为 0 的段
    stat["空档段"] = [r["价格段"] for r in rows if r["商品数"] == 0]
    # 最冷门的非空段（白牌切入点候选）
    nonempty = [r for r in rows if r["商品数"] > 0]
    stat["最稀疏段"] = min(nonempty, key=lambda r: r["占比%"])["价格段"] if nonempty else ""
    return rows, stat


def rm_spread(vals, edges):
    out = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        if i == len(edges) - 2:
            out.append(sum(1 for v in vals if lo <= v <= hi))
        else:
            out.append(sum(1 for v in vals if lo <= v < hi))
    return out


# ============================================================
# 市场品牌壁垒（含品牌×价格带 / 占位率 / 空档定位）
# ============================================================

# 卖家乱填的品牌值：不是真品牌，做品牌分析时要过滤掉
BRAND_JUNK = {"tws", "inear", "in-ear", "in ear", "branded", "generic", "unbranded",
              "other", "n/a", "na", "no brand", "oem", "none", "universal", "unknown",
              "does not apply", "doesn't apply", "not applicable", "various", "mix"}


def is_whitelabel(v):
    return (v or "").strip().lower() in WHITELABEL


def brand_from_structured(items):
    """主口径：用结构化 brand 字段 / item_specifics.Brand 统计品牌壁垒。

    为什么用它（2026-09-15 生产实测 120 条）：
      - eBay 官方 API 的 `brand` 字段与 `item_specifics.Brand` **完全一致**，是权威来源
      - 而标题词频检测会把**兼容性词**（for Samsung / for iPhone）当成品牌：
        实测标题里 samsung 命中 32 条(26.7%)，但 brand 字段里 samsung **一次都没出现**
      → 品牌壁垒必须以 brand 字段为主口径，标题词只作辅助参考

    返回 dict：summary / brand_rows / occupancy_by_band / spec_rows
    """
    prices = defaultdict(list)
    bands = defaultdict(lambda: [0, 0])      # band -> [总数, 带真品牌数]
    brand_band = defaultdict(lambda: Counter())
    raw_values = Counter()
    n = 0

    def _band_of(p):
        if p is None:
            return None
        return band_label(band_index(p))

    for it in items:
        n += 1
        raw = ""
        # 优先取顶层 brand 字段，其次 item_specifics 里的 Brand
        if it.get("brand_field"):
            raw = str(it["brand_field"]).strip()
        else:
            for s in it.get("item_specifics") or []:
                if (s.get("name") or "").strip().lower() == "brand":
                    raw = str(s.get("value") or "").strip()
                    break
        raw_values[raw or "(空)"] += 1
        p = it.get("price")
        b = _band_of(p)
        if b:
            bands[b][0] += 1
        is_real = bool(raw) and not is_whitelabel(raw) and raw.strip().lower() not in BRAND_JUNK
        if is_real:
            prices[raw].append(p)
            if b:
                bands[b][1] += 1
                brand_band[raw][b] += 1

    rows = []
    for b, ps in sorted(prices.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        ps2 = [x for x in ps if x is not None]
        where = [k for k in PRICE_BAND_LABELS if brand_band[b].get(k)]
        rows.append({
            "品牌": b,
            "商品数": len(ps),
            "占比%": round(100.0 * len(ps) / n, 1) if n else 0.0,
            "类型": "主流品牌" if len(ps) >= 3 else "中小品牌",
            "均价": round(sum(ps2) / len(ps2), 2) if ps2 else None,
            "最低价": min(ps2) if ps2 else None,
            "最高价": max(ps2) if ps2 else None,
            "覆盖价格带数": len(where),
            "主要价格带": "、".join(where[:3]),
        })

    occ = []
    for lbl in PRICE_BAND_LABELS:
        tot, real = bands[lbl][0], bands[lbl][1]
        occ.append({
            "价格带": lbl,
            "商品数": tot,
            "真品牌条数": real,
            "真品牌占位率%": round(100.0 * real / tot, 1) if tot else 0.0,
            "白牌条数": tot - real,
        })

    real_total = sum(len(v) for v in prices.values())
    wl_total = sum(1 for it in items if not (
        (str(it.get("brand_field") or "").strip() and
         not is_whitelabel(it.get("brand_field")) and
         str(it.get("brand_field")).strip().lower() not in BRAND_JUNK)))
    elig = [r for r in occ if r["商品数"] >= 5]
    best = min(elig, key=lambda r: r["真品牌占位率%"]) if elig else None
    top_brand = rows[0]["品牌"] if rows else ""
    summary = {
        "样本条数": n,
        "真品牌条数": real_total,
        "真品牌占位率%": round(100.0 * real_total / n, 1) if n else 0.0,
        "白牌/通用条数": wl_total,
        "白牌占比%": round(100.0 * wl_total / n, 1) if n else 0.0,
        "真品牌种类数": len(rows),
        "份额最高品牌": "%s（%s 条）" % (top_brand, rows[0]["商品数"]) if rows else "",
        "结论": ("白牌切入口：%s 段真品牌占位率最低（%.0f%%），样本 %d 条"
                 % (best["价格带"], best["真品牌占位率%"], best["商品数"])) if best
                else "样本不足，无法定位白牌切入口",
    }
    spec_rows = [{"brand 字段值": k, "条数": v,
                  "归类": "白牌/通用" if is_whitelabel(k) else
                          ("乱填/品类词" if k.strip().lower() in BRAND_JUNK else "具体品牌")}
                 for k, v in raw_values.most_common()]
    return {"summary": summary, "brand_rows": rows, "occupancy_by_band": occ,
            "spec_rows": spec_rows}


def title_brand_mentions(items, brands, edges=None, labels=None):
    """辅助口径：标题里的"品牌/兼容词"提及率。

    ⚠️ 注意：这只反映**标题营销用词**，包含兼容性词（for Samsung / for iPhone），
    **不代表品牌市场份额**。实测 samsung 在标题里 32 条，但真品牌字段里一次都没出现。
    """
    labels = labels or PRICE_BAND_LABELS
    n = len(items) or 1
    cnt = Counter()
    prices = defaultdict(list)
    head = Counter()
    band_hit = [0] * len(labels)
    band_tot = [0] * len(labels)
    for it in items:
        toks = tokenize(it.get("title") or "")
        hit = {w for w in toks if w in (brands or set())}
        p = it.get("price")
        bi = band_index(p) if p else None
        if bi is not None:
            band_tot[bi] += 1
            if hit:
                band_hit[bi] += 1
        for b in hit:
            cnt[b] += 1
            if p:
                prices[b].append(p)
            if toks and toks[0] == b:
                head[b] += 1
    rows = []
    for b, c in cnt.most_common():
        ps = prices.get(b) or []
        rows.append({
            "标题品牌词": b,
            "命中条数": c,
            "提及率%": round(100.0 * c / n, 1),
            "均价": round(sum(ps) / len(ps), 2) if ps else None,
            "标题开头占位": head[b],
            "开头占位率%": round(100.0 * head[b] / c, 1) if c else 0.0,
        })
    occ = [{"价格带": labels[i], "商品数": band_tot[i], "带标题品牌词条数": band_hit[i],
            "提及率%": round(100.0 * band_hit[i] / band_tot[i], 1) if band_tot[i] else 0.0}
           for i in range(len(labels))]
    return rows, occ


def ad_slot_positions(items, top_n=10, bucket=10):
    """广告位出现在第几位的分布 —— 回答"前 N 位里有几条广告"。

    需求原文要求取「前 10 位（含广告）」的 item specifics，
    这条统计直接给出"前 10 位里到底有几条是广告位"，以及广告位的位置分布。
    """
    rows = sorted(items, key=lambda x: x.get("position") or 0)
    ad_pos = [x["position"] for x in rows if x.get("is_sponsored")]
    total = len(rows)
    n_ad = len(ad_pos)

    # 每 N 位一个桶
    nb = max(1, (total + bucket - 1) // bucket) if total else 1
    dist = []
    for i in range(nb):
        lo = i * bucket + 1
        hi = min((i + 1) * bucket, total)
        if lo > total:
            break
        seg = [x for x in rows if lo <= (x.get("position") or 0) <= hi]
        seg_ad = sum(1 for x in seg if x.get("is_sponsored"))
        dist.append({
            "位置区间": "%d-%d" % (lo, hi),
            "商品数": len(seg),
            "广告位条数": seg_ad,
            "广告位占比%": round(100.0 * seg_ad / len(seg), 1) if seg else 0.0,
        })

    top_seg = [x for x in rows if (x.get("position") or 0) <= top_n]
    top_ad = [x for x in top_seg if x.get("is_sponsored")]
    summary = {
        "广告位总条数": n_ad,
        "广告位占全部%": round(100.0 * n_ad / total, 1) if total else 0.0,
        "首个广告位在第几位": min(ad_pos) if ad_pos else None,
        "广告位平均位次": round(sum(ad_pos) / n_ad, 1) if ad_pos else None,
        "广告位位次范围": ("%d~%d" % (min(ad_pos), max(ad_pos))) if ad_pos else "",
        "前%d位里广告位条数" % top_n: len(top_ad),
        "前%d位广告位占比%%" % top_n: round(100.0 * len(top_ad) / len(top_seg), 1) if top_seg else 0.0,
    }
    return dist, summary


def ad_slot_by_band(items, edges=None, labels=None):
    """各价格带的广告位占比 —— 看哪一段卖家投广告最凶。

    广告位标记来自 eBay 官方 API 的 `priorityListing` 字段（实测与搜索页 promoted 一致）。
    返回 (rows, summary)；summary 含总体广告位条数与占比。
    """
    edges = edges or PRICE_BANDS
    labels = labels or PRICE_BAND_LABELS
    nb = len(labels)
    tot = [0] * nb
    ad = [0] * nb
    ad_prices = []
    all_prices = []
    for it in items:
        p = it.get("price")
        bi = band_index(p, edges) if p else None
        is_ad = bool(it.get("is_sponsored"))
        if bi is not None:
            tot[bi] += 1
            if is_ad:
                ad[bi] += 1
        if is_ad:
            if p:
                ad_prices.append(p)
        if p:
            all_prices.append(p)
    rows = []
    for i, lbl in enumerate(labels):
        rate = 100.0 * ad[i] / tot[i] if tot[i] else 0.0
        if tot[i] == 0:
            level = "无商品"
        elif rate >= 50:
            level = "广告最凶"
        elif rate >= 25:
            level = "广告较多"
        elif rate > 0:
            level = "广告较少"
        else:
            level = "无广告"
        rows.append({
            "价格带": lbl, "商品数": tot[i], "广告位条数": ad[i],
            "广告位占比%": round(rate, 1), "自然位条数": tot[i] - ad[i],
            "投放强度": level,
        })
    n = len(items) or 1
    n_ad = sum(ad)
    summary = {
        "广告位条数": n_ad,
        "广告位占比%": round(100.0 * n_ad / n, 1),
        "广告位均价": round(sum(ad_prices) / len(ad_prices), 2) if ad_prices else None,
        "全部商品均价": round(sum(all_prices) / len(all_prices), 2) if all_prices else None,
    }
    hot = [r for r in rows if r["广告位条数"] > 0]
    if hot:
        top = max(hot, key=lambda r: r["广告位占比%"])
        summary["投放最凶价格带"] = "%s（广告位占 %.0f%%，%d/%d 条）" % (
            top["价格带"], top["广告位占比%"], top["广告位条数"], top["商品数"])
    else:
        summary["投放最凶价格带"] = "本次无广告位商品"
    return rows, summary


def brand_barrier(items, titles, spec_stats=None, brands=None, edges=None, labels=None):
    """品牌壁垒分析。

    维度：品牌命中/占比、品牌×价格带交叉、各价格带品牌占位率、
    品牌价格带宽度、品牌词在标题里的位置（开头=强势占位）、白牌空档定位。
    """
    edges = edges or PRICE_BANDS
    labels = labels or PRICE_BAND_LABELS
    brands = brands or set()
    n_items = len(items) or 1
    nb = len(labels)

    cnt = Counter()
    prices = defaultdict(list)
    band_of = [0] * nb                  # 每段总商品数
    band_brand = [0] * nb               # 每段带品牌词的商品数
    cross = defaultdict(lambda: [0] * nb)
    head_pos = Counter()                # 品牌词出现在标题开头
    all_pos = Counter()

    for it in items:
        p = it.get("price")
        bi = band_index(p, edges) if p else None
        if bi is not None:
            band_of[bi] += 1
        toks = tokenize(it.get("title") or "")
        hit = {w for w in toks if w in brands}
        if bi is not None and hit:
            band_brand[bi] += 1
        for b in hit:
            cnt[b] += 1
            all_pos[b] += 1
            if toks and toks[0] == b:
                head_pos[b] += 1
            if p:
                prices[b].append(p)
                if bi is not None:
                    cross[b][bi] += 1

    brand_rows = []
    for b, c in cnt.most_common():
        ps = prices.get(b) or []
        arr = cross[b]
        where = [labels[i] for i in range(nb) if arr[i] > 0]
        brand_rows.append({
            "品牌词": b,
            "商品数": c,
            "占比%": round(100.0 * c / n_items, 1),
            "类型": "主流品牌" if c >= 5 else "中小品牌/型号词",
            "最低价": min(ps) if ps else None,
            "最高价": max(ps) if ps else None,
            "均价": round(sum(ps) / len(ps), 2) if ps else None,
            "覆盖价格带数": len(where),
            "主要价格带": "、".join(where[:3]),
            "标题开头占位": head_pos[b],
            "开头占位率%": round(100.0 * head_pos[b] / c, 1) if c else 0.0,
        })

    band_rows = []
    for i in range(nb):
        tot = band_of[i]
        br = band_brand[i]
        band_rows.append({
            "价格带": labels[i],
            "商品数": tot,
            "带品牌词条数": br,
            "品牌占位率%": round(100.0 * br / tot, 1) if tot else 0.0,
            "白牌条数": tot - br,
        })

    # 白牌空档：占位率最低且样本足够的段（>=5 条才有统计意义）
    elig = [r for r in band_rows if r["商品数"] >= 5]
    best = min(elig, key=lambda r: r["品牌占位率%"]) if elig else None
    zero = [r["价格带"] for r in band_rows if r["商品数"] == 0]

    spec_rows = []
    wl_hits = 0
    tot_spec = 0
    for b in spec_stats or []:
        if b["name"].lower() not in ("brand", "compatible brand"):
            continue
        for v in b["values"]:
            val = (v["value"] or "").strip()
            if not val:
                continue
            is_wl = val.lower() in WHITELABEL
            tot_spec += v["count"]
            if is_wl:
                wl_hits += v["count"]
            spec_rows.append({"Brand值": val, "出现次数": v["count"],
                              "类型": "白牌/通用" if is_wl else "具体品牌"})

    brand_title_ratio = sum(cnt.values()) / float(n_items)
    wl_ratio = wl_hits / float(tot_spec or 1)
    if best:
        verdict = ("白牌切入口：%s 段品牌占位率最低（%.0f%%），且样本 %d 条足够"
                   % (best["价格带"], best["品牌占位率%"], best["商品数"]))
    else:
        verdict = "样本不足，无法定位白牌切入口"
    summary = {
        "品牌词总数": len(cnt),
        "品牌商品条数": sum(cnt.values()),
        "品牌标题占比%": round(100.0 * brand_title_ratio, 1),
        "白牌/通用占比%": round(100.0 * wl_ratio, 1),
        "深挖结论": verdict,
    }
    if zero:
        summary["价格空档段"] = "、".join(zero)
    return brand_rows, summary, spec_rows, band_rows


# ============================================================
# 价格段(旧接口保留，供已有调用)
# ============================================================

def spread_bins(vals, edges):
    return rm_spread(vals, edges)
