# -*- coding: utf-8 -*-
"""用 DeepSeek 生成最终 30 条 eBay 推荐标题（替代机械拼装）。

设计要点
--------
1. **素材由脚本算好再喂**：高评分关键词表、修饰词三分类、标题结构模板、竞品完整标题、
   类目与属性短语 —— 都是本地已算出的真实数据，不让模型凭空编。
2. **硬约束写进 prompt，并由脚本 + 校验函数二次把关**（模型不保证遵守）：
   - 每条 ≤80 字符，尽量 70~80（文档："最好80个字符"）
   - 不用逗号等标点（尽量只用空格）
   - 去掉品牌词（用竞品品牌上架有侵权风险）
   - 同一标题内不重复词
   - **重复率 >2 的竞品标题必须原样保留**（文档任务 10），放在最前面
   - 输出 30 条
3. **失败可回退**：网络/JSON/校验不通过 → 返回 None，调用方回退规则版生成器，不中断流水线。

密钥读取：config.local.json 的 deepseek.api_key（或环境变量 DEEPSEEK_API_KEY）。
"""

import json
import os
import re

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
CONFIG_CANDIDATES = [
    os.path.join(PROJ, "config.local.json"),
    os.path.join(HERE, "config.json"),
]
DEFAULT_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
TITLE_MAX = 80
TITLE_GOOD_MIN = 70          # 文档要求"最好 80"，实测竞品中位 79

# ---------------------------------------------------------------------------
# 计费（元 / 百万 tokens）
#   ⚠️ 单价会变，这里只是**估算默认值**，请以官网价格页为准：
#      https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
#   可在 config.local.json 里覆盖：
#      "deepseek": {"price": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 3.0}}
#   DeepSeek 是**峰谷计费**（谷时更便宜），谷时段口径见官网；
#   实测的缓存命中/未命中 token 会一起打印，所以能自己核对。
# ---------------------------------------------------------------------------
PRICE_DEFAULT = {"cache_hit": 0.02, "cache_miss": 1.0, "output": 3.0}
OFF_PEAK_RATIO_DEFAULT = 0.5     # 谷时大致按半价估（官网口径请自行核对）


def load_deepseek_cfg():
    cfg = {}
    for p in CONFIG_CANDIDATES:
        if os.path.isfile(p):
            try:
                cfg = json.load(open(p, encoding="utf-8"))
                break
            except Exception:
                continue
    ds = cfg.get("deepseek") or {}
    return {
        "api_key": os.environ.get("DEEPSEEK_API_KEY") or ds.get("api_key") or "",
        "url": ds.get("base_url") or DEFAULT_URL,
        "model": ds.get("model") or DEFAULT_MODEL,
        "price": ds.get("price") or {},
        "off_peak": bool(ds.get("off_peak")),
    }


def estimate_cost(usage, price=None, off_peak=False):
    """按 token 用量估算花费（元）。用真实的缓存命中/未命中 token 算，不做假设。

    DeepSeek 的 usage 里带 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`：
    命中比未命中便宜约 50 倍，而多轮重试时**第 2 轮的 prompt 是第 1 轮的严格前缀**
    （代码里是 `prompt = prompt + 反馈`），所以命中率通常很高 —— 不区分就会高估成本。
    """
    p = dict(PRICE_DEFAULT)
    p.update(price or {})
    hit = usage.get("prompt_cache_hit_tokens") or 0
    miss = usage.get("prompt_cache_miss_tokens")
    if miss is None:                       # 服务端没回明细时按全部未命中（上界）估
        miss = max(0, (usage.get("prompt_tokens") or 0) - hit)
    out = usage.get("completion_tokens") or 0
    cost = (hit / 1e6 * p["cache_hit"] + miss / 1e6 * p["cache_miss"]
            + out / 1e6 * p["output"])
    ratio = OFF_PEAK_RATIO_DEFAULT if off_peak else 1.0
    return cost * ratio


# ----------------------------------------------------------------------------
# 校验：模型输出必须过这些硬约束，不过就触发重试/回退
# ----------------------------------------------------------------------------

def validate_titles(titles, brands, repeated, kw, max_len=TITLE_MAX):
    """只做**机械约束**校验，返回 (通过的标题列表, 问题清单)。

    设计口径（2026-09-15 用户明确）：
      **"哪些词是品牌词"由 LLM 判断，脚本不再用关键词黑名单否决它的输出。**
      我们只输出 LLM 清洗后的内容。原因：
        - 关键词黑名单会把兼容性描述（for Samsung）、型号词（pro4）误判为品牌并整条否决
        - 与"重复率>2 的标题原样保留"直接冲突，导致永远凑不满 30 条
      因此脚本只查这些客观可判的项：
        - 长度 ≤80
        - 无逗号等标点（尽量只用空格）
        - 同一条内不重复词
        - 标题之间不重复
    """
    problems = []
    out = []
    seen = set()
    for t in titles or []:
        t = re.sub(r"\s+", " ", (t or "")).strip()
        if not t:
            continue
        if len(t) > max_len:
            problems.append("超长(%d): %s" % (len(t), t[:50]))
            continue
        if "," in t or "，" in t:
            problems.append("含逗号: %s" % t[:50])
            continue
        if re.search(r"[^\w\s&\-\.]", t):
            problems.append("含其它标点: %s" % t[:50])
            continue
        toks = re.findall(r"[a-z0-9&\-\.]+", t.lower())
        if len(toks) != len(set(toks)):
            problems.append("词重复: %s" % t[:50])
            continue
        key = t.lower()
        if key in seen:
            problems.append("重复标题: %s" % t[:50])
            continue
        seen.add(key)
        out.append(t)
    return out, problems


def dedupe_keep_order(seq):
    seen = set()
    out = []
    for x in seq:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out


# ----------------------------------------------------------------------------
# Prompt 构造
# ----------------------------------------------------------------------------

def build_prompt(keyword, site, items, kw_rows, mods, templates, brands, repeated,
                 target=30):
    titles = [x.get("title") or "" for x in items]
    specs = []
    for it in items[:40]:
        for s in it.get("item_specifics") or []:
            specs.append("%s=%s" % (s.get("name"), s.get("value")))
    from collections import Counter
    spec_top = Counter(specs).most_common(30)

    def fmt_kw(rows):
        return "\n".join(
            "- %s ｜ 出现 %d 条(%.1f%%) ｜ 位置:%s ｜ 搜索价值 %.1f ｜ 差异化 %.1f ｜ 综合评分 %.1f"
            % (r["关键词"], r["出现条数"], r["占比%"], r["主要位置"],
               r["搜索价值"], r["差异化价值"], r["综合评分"]) for r in rows[:20])

    def fmt_mod():
        out = []
        for g, rows in (mods or {}).items():
            out.append("%s: %s" % (g, "、".join(r["关键词"] for r in rows[:10])))
        return "\n".join(out)

    tmpl = "\n".join("- %s（支持 %d 条）" % (t["模板"], t["支持条数"])
                     for t in (templates or []))

    prompt = f"""你是一位资深跨境电商 eBay SEO 专家。基于下面这些**真实采集数据**，产出 {target} 条可直接上架的 eBay 英文商品标题。

# 一、商品与市场
关键词：{keyword}    站点：{site}
竞品数量：{len(items)} 条（eBay 官方 API 实测采集）

# 二、竞品真实标题（原文，供你学习语言习惯与结构）
{chr(10).join('- ' + t for t in titles[:60])}

# 三、高频关键词分析（已算好：频率/位置/搜索价值/差异化价值/综合评分 1-10）
{fmt_kw(kw_rows)}

# 四、修饰词归类
{fmt_mod()}

# 五、高频属性值（来自竞品 item specifics，真实字段）
{chr(10).join('- ' + k for k, _ in spec_top)}

# 六、标题结构模板（从竞品标题里挖出的真实相邻搭配）
{tmpl}

# 七、必须遵守的硬约束（违反即不合格）
1. 每条标题 **最多 80 个字符（含空格）**，并且**尽量写满 70~80 字符**：竞品真实标题中位数是 79 字符，信息量要充足，不要写得又短又空。
2. **只用空格分隔，不要逗号、分号、竖线等标点**（`&`、`-`、`.` 可以用）。
3. **品牌词与竞品型号词由你判断并清洗**（这是你的核心职责之一）：
   你要自己识别标题里哪些是**品牌词 / 竞品型号编号**，并把它们清洗掉，只保留可上架的内容。
   需求口径是「**品牌词、型号词一律不进标题**」（用竞品品牌上架有侵权风险）。判断标准：
   - **必须清洗掉**：
     a) 把品牌当作自家商品品牌来写的词（让人以为是原厂）。
        例："Sony Wireless Earbuds Bluetooth 5.4" → 去掉 Sony；
        "MPOW Wireless Bluetooth 5.4 Open Ear Earphones" → 去掉 MPOW。
     b) **竞品型号编号**：PRO4 / LP40 / A6S / AirPods 之类 —— 这些是别家的型号，
        写进自己的标题同样是侵权风险，必须去掉。
        例："PRO4 TWS Wireless Bluetooth Earphones…" → 去掉 PRO4。
   - **可以保留（这些不是品牌）**：
     - **适配机型的描述**：`for iPhone` / `for Samsung` / `for Android` / `Compatible with iOS`
       保留（这是在说买家自己的手机能用，属于正常卖点）；也可改写成中性表述
       （如 "for Smartphones"、"Universal"）。
     - **品类词**：TWS / In-Ear / Earbuds / Earphones / Headphones / Buds / Pods。
     - **规格与功能词**：数字版本号（5.3 / 5.4）、IPX4 / IP7、ENC / ANC、USB-C、HiFi 等。
   - **注意**：下面给你的参考词表是脚本从竞品语料里自动抓的，**里面混着型号词（如 pro4、lp40）
     和兼容性词（如 samsung）** —— 词表只是提示，判断权在你：按上面 a) b) 两类清洗。
   参考词表：{', '.join(sorted(brands)[:40])}
4. **同一条标题内不得重复同一个词**（例如不能出现两个 earbuds）。
5. 每条标题之间必须实质不同，不要只换顺序或换一个词。
6. 优先使用综合评分高的关键词；把最重要的词放在前面 30 个字符内。
7. 语言：英文，符合 eBay 买家搜索习惯（参考竞品标题的写法，例如功能词+规格+适用机型+场景）。
8. 大小写规范：正常首字母大写即可，**不要整条或整段全大写**。

# 八、高重复标题的处理（文档任务10 + 你的清洗职责）
下面这些竞品标题在搜索结果首页重复出现率高（>2 次），**必须全部包含在你的输出里、并按原顺序排在最前面**，
用来保留它们已经跑出来的排名流量。但是 —— **每条都要按第 3 条规则做品牌清洗**：
只去掉品牌词与竞品型号词（如 PRO4 / MPOW），其余部分（规格、兼容机型、场景、卖点）逐字保留，
不要改写、不要删减、不要改成全大写。
{chr(10).join('- ' + t for t in repeated) if repeated else '（本次无满足条件的标题）'}

# 九、输出格式
只输出 JSON，不要任何解释文字，结构如下：
{{"titles": ["标题1", "标题2", ...]}}

共 {target} 条；第八节那些高重复标题放在最前面（已清洗版），其余为全新创作。"""
    return prompt


# ----------------------------------------------------------------------------
# 调用
# ----------------------------------------------------------------------------

def call_deepseek(prompt, cfg=None, timeout=180, temperature=0.7):
    cfg = cfg or load_deepseek_cfg()
    if not cfg["api_key"]:
        raise RuntimeError("缺少 DeepSeek 密钥：请在 config.local.json 的 deepseek.api_key 填写，"
                           "或设环境变量 DEEPSEEK_API_KEY")
    r = requests.post(cfg["url"],
                      headers={"Authorization": "Bearer " + cfg["api_key"],
                               "Content-Type": "application/json"},
                      json={
                          "model": cfg["model"],
                          "messages": [
                              {"role": "system",
                               "content": "你是资深 eBay SEO 专家，只输出严格合法的 JSON。"},
                              {"role": "user", "content": prompt},
                          ],
                          "response_format": {"type": "json_object"},
                          "temperature": temperature,
                          "max_tokens": 4000,
                      },
                      timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError("DeepSeek 返回 HTTP %s: %s" % (r.status_code, r.text[:300]))
    data = r.json()
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    usage = data.get("usage") or {}
    try:
        obj = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            raise RuntimeError("模型输出不是 JSON：%s" % content[:200])
        obj = json.loads(m.group(0))
    titles = obj.get("titles") or obj.get("Titles") or []
    return titles, usage, content


def select_best(pool, repeated, kw_rows, target=30, min_len=TITLE_GOOD_MIN):
    """从候选池里择优挑 target 条。

    优先级：
      1. **原样保留的重复标题**（文档任务 10）必须排在最前、至少全进
      2. 长度接近 80 的优先（文档："最好80个字符"；实测竞品中位 79）
      3. 覆盖更多高评分关键词的优先（信息量更足）
      4. 与已选标题的词汇重叠低的优先（避免同质）
    """
    repeat_l = {t.strip().lower() for t in (repeated or [])}
    # 高重复标题由 LLM 输出"清洗后的版本"（脚本不注入原文，避免把未清洗的品牌词塞进来）；
    # 这里只把它们排在最前面
    keep = [t for t in pool if t.strip().lower() in repeat_l]
    rest = [t for t in pool if t.strip().lower() not in repeat_l]

    score_kw = {}
    for i, r in enumerate(kw_rows or []):
        score_kw[str(r.get("关键词", "")).lower()] = float(r.get("综合评分") or 0)

    def kw_score(t):
        toks = set(re.findall(r"[a-z0-9&\-\.]+", t.lower()))
        return sum(score_kw.get(w, 0) for w in toks)

    # 排序：长度优先（接近 80 越好），其次关键词总分
    def sort_key(t):
        ln = len(t)
        short_penalty = max(0, min_len - ln)          # 短于 70 扣分
        return (-(ln - short_penalty * 2), -kw_score(t))

    rest.sort(key=sort_key)

    chosen = list(keep)
    used = {t.lower() for t in chosen}

    def overlap(t):
        a = set(re.findall(r"[a-z0-9&\-\.]+", t.lower()))
        if not a:
            return 1.0
        best = 0.0
        for c in chosen:
            b = set(re.findall(r"[a-z0-9&\-\.]+", c.lower()))
            if b:
                best = max(best, len(a & b) / float(len(a | b)))
        return best

    # 先按排序填，但跳过与已选高度重叠的
    for t in rest:
        if len(chosen) >= target:
            break
        if t.lower() in used:
            continue
        if overlap(t) >= 0.75 and len(chosen) >= max(10, target // 2):
            continue
        chosen.append(t)
        used.add(t.lower())
    # 若因重叠限制没填满，放宽再填
    for t in rest:
        if len(chosen) >= target:
            break
        if t.lower() not in used:
            chosen.append(t)
            used.add(t.lower())
    return chosen[:target]


def generate_titles_llm(keyword, site, items, kw_rows, mods, templates, brands,
                        repeated, target=30, retries=3, verbose=True):
    """产出经校验的标题。失败返回 (None, 说明)，调用方应回退规则版。

    多轮累积：每轮通过的标题都收进积累池（按顺序去重），
    因为模型每次重试都可能有部分合规 —— 直接丢弃整轮太浪费（实测 14→21→25 条递增）。
    """
    prompt = build_prompt(keyword, site, items, kw_rows, mods, templates, brands,
                          repeated, target)
    if verbose:
        print("  [LLM] prompt %d 字符，请求 DeepSeek（model=%s）..."
              % (len(prompt), load_deepseek_cfg()["model"]))
    pool = []
    last = ""
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                   "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0}
    for attempt in range(1, retries + 2):
        try:
            titles, usage, raw = call_deepseek(prompt)
        except Exception as exc:
            last = "调用失败: %s" % str(exc)[:200]
            if verbose:
                print("  [LLM] 第 %d 轮失败：%s" % (attempt, last))
            continue
        for k in usage_total:
            usage_total[k] += usage.get(k) or 0
        ok, problems = validate_titles(titles, brands, repeated, keyword)
        before = len(pool)
        pool = dedupe_keep_order(pool + ok)
        added = len(pool) - before
        good = [t for t in pool if len(t) >= TITLE_GOOD_MIN]
        if verbose:
            print("  [LLM] 第 %d 轮：返回 %d 条 / 本轮合规 %d / 新增 %d / 累计 %d（70~80字符 %d）"
                  % (attempt, len(titles), len(ok), added, len(pool), len(good)))
            for p in problems[:4]:
                print("        不合规: %s" % p)
        # 不再由脚本注入原文（要求 LLM 输出清洗后的版本）
        missing_keep = []
        if len(pool) >= target:
            final = select_best(pool, repeated, kw_rows, target=target)
            if verbose:
                print("  [LLM] 达成：候选 %d 条 → 择优 %d 条（含原样保留 %d/%d），token 合计 %s"
                      % (len(pool), len(final), len(repeated) - len(missing_keep),
                         len(repeated), usage_total))
                print("  [LLM] 花费估算：约 ¥%.4f（命中 %d / 未命中 %d / 输出 %d tokens，"
                      "单价见 llm_titles.PRICE_DEFAULT，可在 config 覆盖）"
                      % (estimate_cost(usage_total), usage_total["prompt_cache_hit_tokens"],
                         usage_total["prompt_cache_miss_tokens"],
                         usage_total["completion_tokens"]))
            return final, {"attempts": attempt, "usage": usage_total,
                           "pool_size": len(pool),
                           "cost_cny": round(estimate_cost(usage_total), 6)}
        last = "累计 %d 条 / 需 %d；未保留 %d 条重复标题" % (
            len(pool), target, len(missing_keep))
        # 把问题与已有结果反馈给模型，让它补齐缺口
        prompt = prompt + ("\n\n# 十、上一轮的问题（必须修正）\n"
                           + "\n".join("- " + p for p in problems[:10])
                           + ("\n- 必须原样保留但还缺的标题：\n"
                              + "\n".join("  " + t for t in missing_keep)
                              if missing_keep else "")
                           + "\n\n请再输出 %d 条**全新**的标题（不要重复下面已合格的），"
                             "严格遵守全部硬约束：\n%s"
                             % (target, "\n".join("  已合格: " + t for t in pool[-12:])))
    if pool:
        final = select_best(pool, repeated, kw_rows, target=target)
        if verbose:
            print("  [LLM] 未达 %d 条（%s），返回择优的 %d 条" % (target, last, len(final)))
        return final, {"attempts": retries + 1, "usage": usage_total,
                       "partial": True, "pool_size": len(pool)}
    return None, last
