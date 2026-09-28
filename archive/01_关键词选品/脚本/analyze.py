# -*- coding: utf-8 -*-
"""词频、相似属性合并、价格段、推荐 title。不访问网络。"""

import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher

TITLE_MAX = 80
STOPWORDS = {
    "a", "an", "and", "or", "the", "to", "of", "for", "in", "on", "at", "by",
    "with", "from", "into", "over", "under", "new", "plus", "set", "pack",
    "pcs", "pc", "lot", "free", "shipping", "fast", "hot", "sale", "item",
    "and", "und", "der", "die", "das", "für", "mit", "les", "des", "une",
}

SKIP_ASPECTS = {
    "upc", "ean", "isbn", "mpn", "sku", "custom bundle", "bundle description",
}


def tokenize(text):
    text = (text or "").strip()
    tokens = []
    for word in re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", text):
        w = word.lower()
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        tokens.append(w)
    for ch_block in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(ch_block) <= 2:
            tokens.append(ch_block)
        else:
            for i in range(len(ch_block) - 1):
                tokens.append(ch_block[i:i + 2])
    return tokens


def exact_title_freq(titles):
    """保留重复：相同 title 计多次。"""
    cleaned = [(t or "").strip() for t in titles if (t or "").strip()]
    return Counter(cleaned)


def token_freq(titles):
    c = Counter()
    for title in titles:
        c.update(tokenize(title))
    return c


def _norm_text(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (s or "").lower())


def _similar(a, b, threshold=0.86):
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        if len(shorter) >= 3 and len(shorter) / float(len(longer)) >= 0.7:
            return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def merge_values(values):
    """把手写近义值并到出现最多的写法上。"""
    groups = []
    for raw in values:
        text = (raw or "").strip()
        if not text:
            continue
        hit = None
        for g in groups:
            if _similar(text, g["canon"]):
                hit = g
                break
        if hit is None:
            groups.append({"canon": text, "members": [text], "count": 1})
        else:
            hit["members"].append(text)
            hit["count"] += 1
            hit["canon"] = Counter(hit["members"]).most_common(1)[0][0]
    groups.sort(key=lambda g: (-g["count"], g["canon"].lower()))
    return groups


def collect_specifics(items, top_n_items=10, include_ads=True):
    picked = []
    for it in items:
        if not include_ads and it.get("is_sponsored"):
            continue
        picked.append(it)
        if len(picked) >= top_n_items:
            break
    rows = []
    for it in picked:
        for spec in it.get("item_specifics") or []:
            name = (spec.get("name") or "").strip()
            value = (spec.get("value") or "").strip()
            if not name or not value:
                continue
            if name.lower() in SKIP_ASPECTS:
                continue
            rows.append({"name": name, "value": value, "position": it.get("position")})
    return picked, rows


def specifics_freq(spec_rows):
    by_name = defaultdict(list)
    for row in spec_rows:
        by_name[row["name"]].append(row["value"])

    merged_names = merge_values(list(by_name.keys()))
    name_map = {}
    for g in merged_names:
        for m in g["members"]:
            name_map[m] = g["canon"]

    bucket = defaultdict(list)
    for row in spec_rows:
        bucket[name_map[row["name"]]].append(row["value"])

    result = []
    for name, vals in bucket.items():
        groups = merge_values(vals)
        result.append({
            "name": name,
            "total": sum(g["count"] for g in groups),
            "values": [{"value": g["canon"], "count": g["count"]} for g in groups],
        })
    result.sort(key=lambda x: (-x["total"], x["name"].lower()))
    return result


def _to_float(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def price_bands(items):
    prices = []
    currency = ""
    for it in items:
        p = _to_float(it.get("price"))
        if p is None or p <= 0:
            continue
        prices.append(p)
        if not currency:
            currency = it.get("currency") or ""
    prices.sort()
    n = len(prices)
    if n == 0:
        return {"count": 0, "currency": currency, "min": None, "p20": None,
                "p50": None, "p80": None, "max": None, "bins": []}

    def pct(q):
        if n == 1:
            return prices[0]
        idx = min(n - 1, max(0, int(math.ceil(q * n) - 1)))
        return prices[idx]

    lo, hi = prices[0], prices[-1]
    bins = []
    if hi == lo:
        bins.append({"label": "%.2f" % lo, "min": lo, "max": hi, "count": n})
    else:
        step = (hi - lo) / 5.0
        for i in range(5):
            a = lo + step * i
            b = hi if i == 4 else lo + step * (i + 1)
            if i < 4:
                cnt = sum(1 for p in prices if p >= a - 1e-9 and p < b - 1e-9)
            else:
                cnt = sum(1 for p in prices if p >= a - 1e-9 and p <= b + 1e-9)
            bins.append({"label": "%.2f-%.2f" % (a, b), "min": a, "max": b, "count": cnt})
    return {
        "count": n,
        "currency": currency,
        "min": prices[0],
        "p20": pct(0.2),
        "p50": pct(0.5),
        "p80": pct(0.8),
        "max": prices[-1],
        "bins": bins,
        "suggest_price": pct(0.5),
    }


def category_stats(items):
    primary = Counter()
    secondary = Counter()
    names = {}
    dual = 0
    for it in items:
        ids = [x for x in (it.get("leaf_category_ids") or []) if x]
        cats = it.get("categories") or []
        for c in cats:
            cid = str(c.get("id") or "")
            if cid:
                names[cid] = c.get("name") or names.get(cid, "")
        if not ids and cats:
            ids = [str(c.get("id")) for c in cats if c.get("id")]
        if not ids:
            continue
        primary[str(ids[0])] += 1
        if len(ids) > 1:
            dual += 1
            secondary[str(ids[1])] += 1
    def pack(counter):
        rows = []
        for cid, cnt in counter.most_common():
            rows.append({"category_id": cid, "name": names.get(cid, ""), "count": cnt})
        return rows
    top = pack(primary)
    return {
        "primary": top,
        "secondary": pack(secondary),
        "dual_category_count": dual,
        "recommend_leaf_id": top[0]["category_id"] if top else "",
        "recommend_leaf_name": top[0]["name"] if top else "",
    }


def _clip_title(parts):
    seen = set()
    words = []
    for p in parts:
        for w in re.split(r"\s+", (p or "").strip()):
            if not w:
                continue
            key = w.lower()
            if key in seen:
                continue
            seen.add(key)
            words.append(w)
    title = " ".join(words).strip()
    title = re.sub(r"\s+", " ", title)
    if len(title) <= TITLE_MAX:
        return title
    out = []
    n = 0
    for w in words:
        add = (1 if out else 0) + len(w)
        if n + add > TITLE_MAX:
            break
        out.append(w)
        n += add
    return " ".join(out)


TITLE_MIN_LEN = 18     # 原脚本 ebay_zc 的约束
TITLE_MAX_LEN = 80

# 品牌黑名单：原脚本是硬编码测试品品牌，这里保留少量 + 用语料结构自动补
BRAND_BLACKLIST = {
    "sony", "bose", "apple", "samsung", "anker", "soundcore", "jbl", "jabra",
    "beats", "xiaomi", "huawei", "baseus", "edifier", "sennheiser", "skullcandy",
    "tozo", "qc", "soundz", "airpods", "soundpeats", "haylou", "redmi",
    "oppo", "vivo", "realme", "oneplus",
}

# 这些是品类/技术词，虽然常出现在标题开头，但绝不是品牌，不能剔
CATEGORY_KEEP = {
    "tws", "bluetooth", "wireless", "earbuds", "earbud", "earphones", "headphones",
    "headset", "buds", "pods", "stereo", "hi-fi", "hifi", "usb", "led", "anc", "enc",
    "ipx", "ipx7", "ip55", "ip7", "type", "for",
}

# 修饰词词性（原脚本 mod_re 的思路，去掉测试品专有词）
# 注意：noise / cancelling 单独作为修饰词会把 20 条标题刷成同一个词模
# （实测产出 "wireless earbuds noise mini / noise bass / cancelling mini ..."），
# 所以这里只保留 "noise cancelling" 这个完整搭配。
MODIFIER_RE = re.compile(
    r"(ing|ed|less|able|proof|mini|micro|wireless|wired|electric|recharge|"
    r"waterproof|sweatproof|usb|portable|fold|stereo|digital|smart|touch|led|"
    r"hifi|dual|double|long|fast|anti|ultra|super|invisible|sport|running|gaming)",
    re.I,
)

# 这些词单独出现没有意义，必须成对才有价值（"noise" 单用会被当成修饰词刷屏）
NEEDS_PAIR = {
    "noise": ("cancelling", "canceling", "cancellation", "isolating", "reduction"),
    "type": ("c", "usb"),
    "in": ("ear", "earbud"),
    "built": ("in",),
}


def detect_brands(titles, blacklist=None):
    """从语料里自动识别品牌/型号词（不依赖硬编码清单）。

    规则（都是语料结构特征，不写死具体品牌）：
      1. 出现在标题开头且首字母大写的低频词（Sony xxx / SoundZ xxx）
      2. 形如型号的词（字母+数字组合，如 sz970si / dx-16），出现在多条标题里
    已知非品牌（CATEGORY_KEEP：tws / bluetooth / for / ipx7 之类品类技术词）永不剔除。
    品牌词必须从推荐 title 里剔除，否则拿竞品品牌去上架。
    """
    bl = set(x.lower() for x in (blacklist or BRAND_BLACKLIST))
    heads = Counter()
    modelish = Counter()
    for t in titles:
        words = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", t or "")
        if words:
            w0 = words[0]
            if w0[:1].isupper() and len(w0) > 2:
                heads[w0.lower()] += 1
        for w in words:
            if re.search(r"\d", w) and re.search(r"[A-Za-z]", w) and len(w) >= 4:
                modelish[w.lower()] += 1
    auto = {w for w, c in heads.items() if 2 <= c <= 8}
    auto |= {w for w, c in modelish.items() if c >= 2}
    return (bl | auto) - CATEGORY_KEEP


def _aspect_value_pool(spec_stats, brands, kw_tokens):
    """按类别提取可用的属性值短语。

    实测知识：不是所有属性都适合进标题。优先 Type / Form Factor / Connectivity /
    Features / Colour / Wireless Technology 这类；剔除 "Doesn't Apply"、"No"、
    纯数字型号、带逗号的长串、以及属性值里的品牌词。
    """
    priority = [
        ("type", "item type", "product type"),
        ("form factor", "fit design", "design"),
        ("connectivity", "connector(s)", "wireless technology"),
        ("features", "feature"),
        ("colour", "color", "farbe"),
        ("bluetooth version", "bluetooth"),
        ("microphone type",),
        ("number of earpieces", "earpiece"),
        ("material", "materials"),
    ]
    bad_value = re.compile(r"(?i)^(n/?a|doesn'?t apply|does not apply|no|yes|none|other|unbranded|generic)$")
    # 不适合进 title 的属性值：非商品属性或过泛
    banned_word = re.compile(
        r"(?i)\b(china|united kingdom|usa|2020s|2010s|months?|years?|days?|"
        r"personalise|personalize|manufacturer warranty|country)\b")
    pool = []
    seen = set()
    seen_sig = set()
    for keys in priority:
        for block in spec_stats:
            name = block["name"].lower()
            if name not in keys:
                continue
            for v in block["values"]:
                val = (v["value"] or "").strip()
                low = val.lower()
                if not val or bad_value.match(val) or len(val) > 28:
                    continue
                if "," in val or "/" in val or ":" in val:
                    continue
                if re.search(r"\d{4,}", val) or banned_word.search(val):
                    continue
                toks = [t for t in tokenize(val) if len(t) > 1]
                # 纯编号/型号值（"5 0" 这种来自 Bluetooth version 的噪音）不要
                if not toks or not any(re.search(r"[a-z]{3}", t) for t in toks):
                    continue
                if any(t in brands for t in toks):
                    continue
                if low in seen:
                    continue
                # 同义折叠：In-Ear Only / Earbud In Ear / In Ear 视为同一个属性
                sig = tuple(sorted(set(toks)))
                if sig in seen_sig:
                    continue
                seen.add(low)
                seen_sig.add(sig)
                pool.append(val)
            break
    return pool


def generate_titles(keyword, titles, spec_stats, min_count=20):
    """生成推荐 title。

    结构参照原始脚本 `ebay_zc/ziniao_ebay_search.py::build_recommended_titles`：
      结构1: 修饰词 + 修饰词 + 关键词
      结构2: 修饰词 + 核心词 + 关键词
      兜底  : 候选词串 + 关键词
    硬约束：>=18 字符、<=80 字符、无逗号、同一标题内不重复词、剔除品牌词。
    相对原脚本的改动：
      - 品牌词由 detect_brands 自动识别（原脚本是硬编码测试品清单）
      - 修饰词来自语料高频词 + 属性值短语（原脚本只用语料 + 写死的正则）
      - 去掉 "Lot1" 凑数与单词阶梯这类凑数产物（实测会生成
        "wireless earbuds invisible" 这种不可上架的标题）
    """
    kw = (keyword or "").strip()
    kw_tokens = set(tokenize(kw))
    brands = detect_brands(titles)

    token_rows = token_freq(titles).most_common(60)
    cand = []
    for w, c in token_rows:
        if w in kw_tokens or w in brands or w.isdigit() or len(w) < 3:
            continue
        if w not in cand:
            cand.append(w)
    aspect_pool = _aspect_value_pool(spec_stats, brands, kw_tokens)

    modifiers = [w for w in cand if MODIFIER_RE.search(w)]
    core = [w for w in cand if w not in modifiers]
    if not modifiers:
        modifiers = cand[:]

    results = []
    seen = set()
    use_count = Counter()

    def push(parts, reuse_cap):
        words = []
        seen_words = set()
        for p in parts:
            for w in re.split(r"\s+", (p or "").strip()):
                if not w:
                    continue
                k = w.lower()
                if k in seen_words or k in brands or k in kw_tokens:
                    continue
                seen_words.add(k)
                words.append(w)
        title = " ".join(words).strip()
        title = re.sub(r"[^\w\s%\-]", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            return False
        if not title.lower().startswith(kw.lower()):
            title = (kw + " " + title).strip()
        if len(title) < TITLE_MIN_LEN or len(title) > TITLE_MAX_LEN or "," in title:
            return False
        # 去重：按词集合签名，避免 "词序不同但同一批词" 的重复产出
        key = tuple(sorted(set(re.findall(r"[a-z0-9]+", title.lower()))))
        if key in seen:
            return False
        # 频次护栏：待加入的实词若已用满 reuse_cap 次，则放弃这条
        payload = [w.lower() for w in words if len(w) > 2 and w.lower() != kw.lower()]
        if reuse_cap is not None and any(use_count[w] >= reuse_cap for w in payload):
            return False
        seen.add(key)
        for w in payload:
            use_count[w] += 1
        results.append(title)
        return True

    def run_plan(plan, reuse_cap):
        for parts in plan:
            if len(results) >= min_count:
                return
            push(parts, reuse_cap)

    def build_plan(aspects):
        """顺序很重要：eBay title 是"关键词 + 属性堆叠"的密集结构，单属性太单薄。"""
        plan = []
        for i, v in enumerate(aspects[:12]):
            for v2 in aspects[i + 1:14]:
                plan.append([kw, v, v2])
        for i, v in enumerate(aspects[:8]):
            for v2 in aspects[i + 1:10]:
                for a in modifiers[:4]:
                    plan.append([kw, v, v2, a])
        for v in aspects[:6]:
            for a in modifiers[:6]:
                plan.append([kw, v, a])
        for v in aspects[:12]:
            for c in core[:4]:
                plan.append([kw, v, c])
        for v in aspects[:14]:
            plan.append([kw, v])
        # 修饰词两两组合，打散成"轮转"顺序：a0b1, a1b0, a0b2, a2b0 ...
        pairs = []
        for i, a in enumerate(modifiers[:8]):
            for j, b in enumerate(modifiers[:8]):
                if i < j:
                    pairs.append((a, b))
        for k in range(5):
            for (a, b) in pairs:
                plan.append([kw, a, b] if k % 2 == 0 else [kw, b, a])
        for c in core[:6]:
            for a in modifiers[:6]:
                plan.append([kw, c, a])
        # 最后才是高频词阶梯（原脚本的兜底思路，保证尽量凑满 min_count）
        for i in range(len(cand)):
            for w in range(2, 5):
                plan.append([kw] + cand[i:i + w])
        return plan

    # 三段重试：先严格保多样性；凑不满就放宽复用；再凑不满就只为保量
    # （需求是"至少 20 条给运营上架"，绝不能因为多样性护栏而少给）
    plan = build_plan(aspect_pool)
    run_plan(plan, 3)
    if len(results) < min_count:
        run_plan(plan, 6)
    if len(results) < min_count:
        run_plan(plan, None)

    return results[:min_count] if len(results) >= min_count else results
    kw = (keyword or "").strip()
    token_rows = token_freq(titles).most_common(20)
    top_tokens = [w for w, _ in token_rows if w.lower() not in tokenize(kw)]

    brand = type_name = color = material = style = ""
    extras = []
    for block in spec_stats:
        key = block["name"].lower()
        top_val = block["values"][0]["value"] if block["values"] else ""
        if not top_val:
            continue
        if key in ("brand", "Marke", "marca") and not brand:
            brand = top_val
        elif key in ("type", "style", "item type", "product type") and not type_name:
            type_name = top_val
        elif key in ("color", "colour", "farbe") and not color:
            color = top_val
        elif key in ("material", "materials") and not material:
            material = top_val
        elif key in ("model", "compatible model") and not style:
            style = top_val
        else:
            extras.append(top_val)

    templates = [
        [brand, kw, type_name, color, material],
        [kw, brand, type_name, style],
        [brand, type_name, kw, color],
        [kw, color, material, type_name],
        [brand, kw, material, style],
        [kw, type_name] + top_tokens[:3],
        [brand, kw] + top_tokens[:4],
        [kw] + top_tokens[:5],
        [brand, color, kw, type_name],
        [kw, style, material, color],
    ]
    for extra in extras[:6]:
        templates.append([brand, kw, extra, type_name])
        templates.append([kw, extra] + top_tokens[:2])

    results = []
    seen = set()

    def add(parts):
        title = _clip_title(parts)
        if not title or len(title) < max(8, min(20, len(kw))):
            return
        key = title.lower()
        if key in seen:
            return
        seen.add(key)
        results.append(title)

    for t in templates:
        add(t)
    for i in range(len(top_tokens)):
        add([kw, brand] + top_tokens[i:i + 4])
    for i, tok in enumerate(top_tokens):
        add([brand, kw, tok, color or type_name, material])
        if len(results) >= min_count:
            break

    i = 1
    while len(results) < min_count:
        add([kw, brand, type_name, "Lot%s" % i])
        i += 1
        if i > min_count + 10:
            break
    return results[: max(min_count, len(results))]


def refinements_to_rows(refinements):
    rows = []
    for x in refinements or []:
        name = (x.get("name") or "").strip()
        value = (x.get("value") or "").strip()
        if not name or not value:
            continue
        n = x.get("match_count") or 1
        try:
            n = max(1, min(int(n), 30))
        except (TypeError, ValueError):
            n = 1
        for _ in range(n):
            rows.append({"name": name, "value": value})
    return rows


def build_report(keyword, site, items, recommend_n=20, specifics_n=10, extra_refinements=None):
    titles = [it.get("title") or "" for it in items]
    picked, spec_rows = collect_specifics(items, top_n_items=specifics_n, include_ads=True)
    spec_rows = spec_rows + refinements_to_rows(extra_refinements)
    spec_stats = specifics_freq(spec_rows)
    rec_titles = generate_titles(keyword, titles, spec_stats, min_count=recommend_n)
    return {
        "keyword": keyword,
        "site": site,
        "item_count": len(items),
        "ad_count": sum(1 for it in items if it.get("is_sponsored")),
        "titles_exact": [{"title": t, "count": c} for t, c in exact_title_freq(titles).most_common()],
        "titles_tokens": [{"token": t, "count": c} for t, c in token_freq(titles).most_common(80)],
        "specifics_sample_positions": [it.get("position") for it in picked],
        "specifics": spec_stats,
        "price": price_bands(items),
        "category": category_stats(items),
        "recommended_titles": rec_titles,
        "items": items,
    }
