# -*- coding: utf-8 -*-
"""紫鸟开自己的店，按站点点配送地址，搜前 120 条，进前 10 条拿 specifics / 类目。"""

import re
import time
from urllib.parse import urljoin

from sites import get_site, search_url

SKIP_TITLES = {"shop on ebay"}   # 兼容旧引用；实际占位卡判定见 PLACEHOLDER_TITLES

EXTRACT_JS = r"""
() => {
  const specifics = [];
  const seen = new Set();
  // 物流/交易类噪音，不是商品属性（真机实测这些会混进 aria/文本启发式里）
  const NOISE = /^(postage|delivery|shipping|returns?|collection|location|located in|payment|seller|quantity|watch|condition|item number|price|bids?|time left|sold|click & collect|see details)/i;
  const push = (name, value) => {
    name = (name || '').replace(/\s+/g, ' ').replace(/[:：]\s*$/, '').trim();
    value = (value || '').replace(/\s+/g, ' ').trim();
    if (!name || !value) return;
    if (NOISE.test(name)) return;
    if (name.length > 40 || value.length > 300) return;
    if (/^n\/?a$/i.test(value)) return;
    const key = name + '|' + value;
    if (seen.has(key)) return;
    seen.add(key);
    specifics.push({name, value});
  };

  // 路径1（真机 2026-09-14 实测命中）：#viTabs_0_is / About this item 里的 dl>dt+dd
  ['#viTabs_0_is dl', '.vim.x-about-this-item dl', '.ux-layout-section-evo dl',
   '[data-testid="ux-layout-section-evo"] dl', 'dl'].forEach((sel) => {
    document.querySelectorAll(sel).forEach((dl) => {
      const dts = dl.querySelectorAll('dt');
      const dds = dl.querySelectorAll('dd');
      if (dts.length && dts.length === dds.length) {
        dts.forEach((dt, i) => push(dt.innerText, dds[i].innerText));
      }
    });
  });

  // 路径2：旧版 ux-labels-values 结构（#viTabs_0_is 内为 0，保留给其它站点/版本）
  document.querySelectorAll('#viTabs_0_is .ux-labels-values, .ux-layout-section--features .ux-labels-values')
    .forEach((row) => {
      const labelEl = row.querySelector('.ux-labels-values__labels-content, .ux-labels-values__labels');
      const valueEl = row.querySelector('.ux-labels-values__values-content, .ux-labels-values__values');
      push((labelEl && labelEl.innerText) || '', (valueEl && valueEl.innerText) || '');
    });

  const crumbs = [];
  document.querySelectorAll(
    'nav[aria-label="breadcrumb"] a, nav.breadcrumbs a, .seo-breadcrumb-text, a.ux-breadcrumbs__link, .breadcrumbs a, .x-breadcrumb a'
  ).forEach((a) => {
    const text = (a.innerText || '').replace(/\s+/g, ' ').trim();
    if (!text) return;
    const href = a.getAttribute('href') || '';
    // 真机实测：2026 版面包屑是 /b/bn_7000259660 这种 bn_ 形态，不是数字 ID；
    // 仍保留数字 ID 的匹配以兼容老版页面与其它站点。
    const m = href.match(/_sacat=(\d+)/) || href.match(/\/b\/[^/]+\/(\d+)/) || href.match(/\/sch\/(\d+)/)
           || href.match(/\/b\/bn_(\d+)/);
    crumbs.push({name: text, id: m ? m[1] : '', href: href.slice(0, 120)});
  });

  const html = document.documentElement.innerHTML;
  const mSacat = html.match(/[?&]_sacat=(\d+)/);
  const m2 = html.match(/"secondaryCategoryId"\s*:\s*"?(\d+)"?/);
  const m1 = html.match(/"categoryId"\s*:\s*"(\d+)"/);
  const crumbIds = crumbs.map(c => c.id).filter(Boolean);
  const crumbName = (crumbs.length && crumbs[crumbs.length - 1].name) || '';
  return {
    specifics,
    crumbs,
    primaryCategoryId: (m1 && m1[1]) || crumbIds[crumbIds.length - 1] || (mSacat && mSacat[1]) || '',
    primaryCategoryName: crumbName,
    secondaryCategoryId: (m2 && m2[1]) || ''
  };
}
"""


def _click_first(page, selectors, timeout=2500):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            if not loc.is_visible():
                continue
            loc.click(timeout=timeout)
            return sel
        except Exception:
            continue
    return None


SHIP_DIALOG_SELECTORS = [
    "#gh-shipto-click",
    "button:has-text('Ship to')",
    "button:has-text('Deliver to')",
    "button:has-text('Liefern nach')",
    "button:has-text('Livrer')",
    "button:has-text('Enviar a')",
    "button:has-text('Spedisci a')",
    "[aria-label*='Ship to']",
    "[aria-label*='Deliver to']",
    "button.gh-flyout__target",
]

# 弹层容器（只在这些容器里找国家/邮编控件，绝不碰全局搜索框）
DIALOG_CONTAINER_SELECTORS = [
    "#gh-shipto-dialog",
    "[role='dialog']",
    ".gh-flyout",
    "[class*='shipto']",
    "[class*='ship-to']",
]

SEARCH_INPUT_SELECTORS = [
    "#gh-ac",
    "input[name='_nkw']",
    "input[type='search']",
]


def _dialog_scope(page):
    """返回配送弹层的定位器；找不到容器时返回 None（此时宁可什么都不填）。"""
    for sel in DIALOG_CONTAINER_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def _dialog_text(scope):
    try:
        return re.sub(r"\s+", " ", (scope.inner_text() or ""))
    except Exception:
        return ""


def set_ship_to(page, site_code):
    """在「Ship to」弹层里写站点国家/邮编。

    返回 dict（空 dict = 没设上，调用方应依赖 URL 的 _stpos/_fcid 兜底）。
    与原实现的区别（原实现有两个真问题）：
      1. 原实现最后一个邮编兜底选择器是 input[type='text']，会命中页面全局搜索框，
         把邮编填进搜索框并提交，把页面带跑到 "搜 SW1A1AA 商品"（实测已复现）；
      2. 原实现无条件 return True，「配送弹层已点」是假信号。
    现在：只在弹层容器内找控件；不点任何提交型按钮；返回值如实反映结果。
    """
    site = get_site(site_code)
    print("  设置配送地: %s %s" % (site["country"], site["zip"]))

    before_url = page.url
    before_ac = ""
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                before_ac = page.locator(sel).first.input_value()
                break
        except Exception:
            continue

    clicked = _click_first(page, SHIP_DIALOG_SELECTORS)
    if not clicked:
        print("  未找到配送入口 -> 交给搜索 URL 的 _stpos/_fcid 兜底")
        return {}
    print("  已点开配送入口: %s" % clicked)
    time.sleep(1.5)

    scope = _dialog_scope(page)
    if scope is None:
        print("  没识别到弹层容器 -> 不填任何输入框（避免误填搜索框），交给 URL 兜底")
        return {}

    dialog_text = _dialog_text(scope)
    country_ok = any(lbl.lower() in dialog_text.lower() for lbl in site["country_labels"])
    print("  弹层文本片段: %s" % dialog_text[:110])

    # 国家：只在弹层内的 select 上操作
    for label in site["country_labels"]:
        try:
            sel = scope.locator("select")
            if sel.count() > 0:
                sel.first.select_option(label=label)
                country_ok = True
                print("  弹层内已选国家: %s" % label)
                break
        except Exception:
            continue

    # 邮编：只在弹层容器内找输入框
    zip_filled = ""
    for sel in [
        "input[autocomplete='postal-code']",
        "input[name*='zip']",
        "input[id*='zip']",
        "input[placeholder*='ZIP']",
        "input[placeholder*='Post']",
        "input[type='text']",
    ]:
        try:
            loc = scope.locator(sel)
            if loc.count() == 0 or not loc.first.is_visible():
                continue
            loc.first.fill(site["zip"], timeout=2500)
            zip_filled = site["zip"]
            break
        except Exception:
            continue

    # 只做非提交式收敛：按 Enter，不点 submit 按钮（避免误触搜索）
    if zip_filled:
        try:
            scope.locator("input[autocomplete='postal-code'], input[type='text']").first.press("Enter", timeout=2000)
        except Exception:
            pass
    time.sleep(1.5)

    after_ac = ""
    for sel in SEARCH_INPUT_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                after_ac = page.locator(sel).first.input_value()
                break
        except Exception:
            continue

    drifted = (page.url != before_url) or (after_ac and after_ac != before_ac)
    if drifted:
        print("  !! 检测到页面被带跑（url 或搜索框内容变化），撤回并只用 URL 参数")
        try:
            page.goto(before_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        return {}

    result = {
        "entry": clicked,
        "country_ok": bool(country_ok),
        "zip_filled": zip_filled,
        "postcode_text": site["zip"] if zip_filled else "",
        "dialog_snippet": dialog_text[:160],
    }
    print("  配送弹层结果: country_ok=%s zip_filled=%s（失败则靠 _stpos/_fcid 兜底）"
          % (result["country_ok"], bool(zip_filled)))
    return result


LISTING_JSON_KEY = '"listings":['

# 2026-09-14 真机实测（ebay.co.uk 搜索页）：li.s-item = 0 条，li.s-card = 242 条。
# 旧实现只用 li.s-item，在真实页面上恒为 0 条。
CARD_SELECTOR_CANDIDATES = [
    "li.s-card",
    "li.s-item",
    ".srp-results li.s-card",
    ".srp-results li",
]

CARD_FIELD_SELECTORS = {
    "title": [".s-card__title", ".s-item__title", "[role=heading]", "h3"],
    "price": [".s-card__price", ".s-item__price", ".s-card__attribute-row"],
    "link": ["a.s-card__link[href*='/itm/']", "a[href*='/itm/']", "a.s-card__link", "a.s-item__link"],
    "subtitle": [".s-card__subtitle", ".s-item__subtitle", ".s-item__condition"],
    "ad_badge": ["[class*=etrs]", "[class*=ad-badge]", "[class*=ad_badge]", "[aria-label*=Sponsored i]"],
    # 真机实测：商品图在 i.ebayimg.com，占位卡用 ir.ebaystatic.com（要排除）
    "image": ["img.s-card__image[src*='ebayimg.com']", "img[src*='ebayimg.com']",
              ".s-card__image img[src*='ebayimg.com']", "img.s-card__image"],
}

# 非商品图的域名（占位卡、图标等）
IMAGE_SKIP_HOSTS = ("ir.ebaystatic.com", "ebayadservices.com", "rover.ebay.com")

AD_TEXT_KEYS = ("sponsored", "anzeige", "annonce", "anuncio", "推广", "广告")

PLACEHOLDER_TITLES = {"shop on ebay", "shop on eBay", ""}

# 已下架/失效条目（真机在 uk 搜索页见到："This listing was ended by the seller because
# the item is no longer available."），这些不该占用 120 条配额
DEAD_PATTERNS = (
    "this listing was ended",
    "listing ended",
    "no longer available",
    "item is out of stock",
)


def _dig_listings_array(page):
    """取搜索页内嵌 JSON 的 listings 数组（含 promoted / leafCat）。

    真机实测：ebay.co.uk 搜索页 HTML 里存在 "listings":[{"itemId":...,"promoted":true,
    "rank":0,"leafCat":112529}, ...]，与页面卡片 242/242 一一对应。
    这是广告位与末级类目 ID 的权威来源，不必猜正则、不必额外开详情页。
    """
    js = r"""
    () => {
      const html = document.documentElement.innerHTML;
      const key = '"listings":[';
      const i = html.indexOf(key);
      if (i < 0) return null;
      let j = i + key.length - 1, depth = 0, inStr = false, esc = false, end = -1;
      for (let k = j; k < html.length; k++) {
        const ch = html[k];
        if (inStr) {
          if (esc) { esc = false; }
          else if (ch === '\\') { esc = true; }
          else if (ch === '"') { inStr = false; }
          continue;
        }
        if (ch === '"') { inStr = true; continue; }
        if (ch === '[' || ch === '{') { depth++; continue; }
        if (ch === ']' || ch === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
      }
      if (end < 0) return null;
      try { return JSON.parse(html.slice(j, end)); } catch (e) { return null; }
    }
    """
    try:
        data = page.evaluate(js)
    except Exception as exc:
        print("  listings 提取失败: %s" % str(exc)[:100])
        return []
    if not isinstance(data, list):
        print("  listings 未在页面中找到（广告位/类目将退化为 DOM 判断）")
        return []
    print("  内嵌 listings 条数: %d" % len(data))
    return data


def _pick_card_selector(page):
    for sel in CARD_SELECTOR_CANDIDATES:
        try:
            n = page.locator(sel).count()
        except Exception:
            continue
        if n > 0:
            return sel, n
    return None, 0


# eBay 卡片里插在标题后的无障碍提示文本（真机实测每张卡都带）
A11Y_TAIL_PATTERNS = (
    "opens in a new window or tab",
    "opens in a new window",
    "opens in new window or tab",
    "opens in new window",
)


def clean_listing_title(title):
    """去掉标题尾部的 a11y 提示文本并压平空白。

    真机实测：.s-card__title 的 innerText 是
      "TWS Wireless Earbuds ... For Android & iPhone\nOpens in a new window or tab"
    不清理会污染 title 词频，并且拼出
      "wireless earbuds opens window tab" 这类垃圾推荐标题。
    """
    t = re.sub(r"\s+", " ", (title or "")).strip()
    changed = True
    while changed:
        changed = False
        low = t.lower()
        for pat in A11Y_TAIL_PATTERNS:
            if low.endswith(pat):
                t = t[: len(t) - len(pat)].strip(" -–—|·,")
                changed = True
                break
    return t


def _card_image(card):
    """取商品主图 URL 与 listing 图片总数。

    真机实测（ebay.co.uk 搜索页）：
      <img loading="eager" src="https://i.ebayimg.com/images/g/qocAAeSwLTxpwuAM/s-l500.webp"
           alt="... Image 1 of 4">
      <img loading="lazy"  src="https://i.ebayimg.com/images/g/zfQAAeSwzyppwuAM/s-l500.webp"
           alt="... Image 2 of 4">
    占位卡用的是 ir.ebaystatic.com，必须排除；alt 里的 "Image N of M" 顺带给出图片总数。
    """
    urls = []
    for sel in CARD_FIELD_SELECTORS["image"]:
        try:
            loc = card.locator(sel)
            n = loc.count()
        except Exception:
            continue
        for i in range(min(n, 5)):
            try:
                u = loc.nth(i).get_attribute("src") or ""
            except Exception:
                continue
            if not u or any(h in u for h in IMAGE_SKIP_HOSTS):
                continue
            if u not in urls:
                urls.append(u)
        if urls:
            break
    # alt 里的 "Image N of M"
    total = 0
    for sel in ("img.s-card__image", "img[src*='ebayimg.com']"):
        try:
            loc = card.locator(sel)
            if loc.count() == 0:
                continue
            alt = loc.first.get_attribute("alt") or ""
            m = re.search(r"(?i)image\s+\d+\s+of\s+(\d+)", alt)
            if m:
                total = int(m.group(1))
                break
        except Exception:
            continue
    if not total and urls:
        total = len(urls)
    return (urls[0] if urls else ""), total


def _card_text(card, field):
    for sel in CARD_FIELD_SELECTORS.get(field, []):
        try:
            loc = card.locator(sel)
            if loc.count() > 0:
                txt = (loc.first.inner_text() or "").strip()
                if txt:
                    return txt
        except Exception:
            continue
    return ""


def _card_title(card):
    """标题字段：取原始文本后清掉 a11y 尾巴。"""
    return clean_listing_title(_card_text(card, "title"))


def _card_href(card):
    for sel in CARD_FIELD_SELECTORS["link"]:
        try:
            loc = card.locator(sel)
            if loc.count() > 0:
                href = loc.first.get_attribute("href") or ""
                if href:
                    return href
        except Exception:
            continue
    return ""


def _num_from_text(token):
    """单个数字串 -> float，兼容英美 1,234.56 与欧陆 1.234,56 / 12,99。"""
    t = (token or "").strip()
    if not t:
        return None
    has_dot = "." in t
    has_comma = "," in t
    if has_dot and has_comma:
        if t.rfind(",") > t.rfind("."):      # 1.234,56 -> 欧陆
            t = t.replace(".", "").replace(",", ".")
        else:                                 # 1,234.56 -> 英美
            t = t.replace(",", "")
    elif has_comma:
        tail = t.split(",")[-1]
        if len(tail) == 3 and t.count(",") == 1 and len(t.split(",")[0]) <= 3:
            t = t.replace(",", "")            # 1,234 -> 千分位
        else:
            t = t.replace(",", ".")           # 12,99 -> 小数
    try:
        return float(t)
    except ValueError:
        return None


def parse_price_display(text):
    """价格原文 -> (min, max, currency, display)。

    真机实测两种形态都要处理：
      区间: "£21.97 to £22.97(£21.97/Unit)"   -> min 21.97 / max 22.97
      单价: "£13.99(£13.99/Unit)"              -> min=max=13.99
    旧实现只取第一个数字，区间会被当成下限，价格段分析系统性偏低；
    另外把 "," 一律删掉，会让欧陆站点 "12,99" 变成 1299。
    """
    display = (text or "").strip()
    if not display:
        return None, None, "", ""
    if re.fullmatch(r"(?i)\s*(free|gratis|kostenlos|gratuit)\s*", display):
        return None, None, "", display
    body = display.split("(")[0]
    body = re.sub(r"(?i)\b(to|bis|a|à)\b", " ", body)
    body = body.replace("–", "-").replace("—", "-")
    nums = re.findall(r"\d[\d.,]*", body)
    vals = []
    for n in nums:
        v = _num_from_text(n)
        if v is not None:
            vals.append(v)
    if not vals:
        return None, None, "", display
    if len(vals) == 1:
        return vals[0], vals[0], _card_currency(display), display
    lo, hi = min(vals), max(vals)
    if hi > lo * 50:          # 明显是把数量/年份当价格了
        hi = lo
    return lo, hi, _card_currency(display), display


def _card_currency(text):
    t = text or ""
    m = re.search(r"(US|AU|CA|HK)\s*\$", t)
    if m:
        return "%s $" % m.group(1)
    m = re.search(r"(GBP|EUR|USD|AUD|CAD|CHF)\b", t, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"(£|€|\$)", t)
    return m.group(1) if m else ""


def _card_sponsored(card, listing):
    """广告位判定：优先用内嵌 listings 的 promoted（权威），DOM 仅作兜底。

    旧实现把整张卡的 HTML 拼起来找 "sponsored"/"广告" 等词，会把模板里的
    文字也算进去（实测会虚高），所以这里不再扫 HTML 全文。
    """
    if isinstance(listing, dict) and "promoted" in listing:
        return bool(listing.get("promoted"))
    for sel in CARD_FIELD_SELECTORS["ad_badge"]:
        try:
            if card.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    txt = ""
    try:
        txt = (card.inner_text() or "")
    except Exception:
        pass
    return any(k in txt.lower() for k in AD_TEXT_KEYS)


def parse_listing_page(page, start_pos, need, listings=None):
    """解析搜索结果页。字段按 2026-09-14 真机实测结构取。

    listings: _dig_listings_array() 的结果，用于 promoted / leafCat（按 itemId join）。
    """
    if need <= 0:
        return []
    sel, count = _pick_card_selector(page)
    if not sel:
        print("  列表页没命中任何卡片选择器: %s" % CARD_SELECTOR_CANDIDATES)
        return []
    print("  卡片选择器 %s -> %d 张卡" % (sel, count))

    by_id = {}
    for x in listings or []:
        if isinstance(x, dict) and x.get("itemId") is not None:
            by_id[str(x["itemId"])] = x

    cards = page.locator(sel)
    results = []
    skipped_placeholder = 0
    skipped_dead = 0
    for i in range(count):
        if len(results) >= need:
            break
        card = cards.nth(i)
        title = _card_title(card)
        if not title or title.lower() in {t.lower() for t in PLACEHOLDER_TITLES}:
            skipped_placeholder += 1
            continue
        card_txt = ""
        try:
            card_txt = (card.inner_text() or "").lower()
        except Exception:
            pass
        if any(p in card_txt for p in DEAD_PATTERNS) or any(p in title.lower() for p in DEAD_PATTERNS):
            skipped_dead += 1
            continue

        price_display = _card_text(card, "price")
        price_min, price_max, currency, price_display = parse_price_display(price_display)

        item_url = _card_href(card)
        legacy_id = ""
        m = re.search(r"/itm/(?:[^/]+/)?(\d{9,15})", item_url or "")
        if m:
            legacy_id = m.group(1)
        listing = by_id.get(legacy_id) or {}

        leaf = []
        lid = listing.get("leafCat")
        if lid:
            leaf.append(str(lid))

        image_url, image_count = _card_image(card)

        results.append({
            "position": start_pos + len(results),
            "item_id": legacy_id if listing else "",
            "legacy_item_id": legacy_id,
            "title": title,
            "price": price_min,
            "price_max": price_max,
            "price_is_range": bool(price_min is not None and price_max is not None
                                   and price_max > price_min),
            "currency": currency,
            "price_display": price_display,
            "condition": _card_text(card, "subtitle"),
            "is_sponsored": _card_sponsored(card, listing),
            "promoted_source": ("listings" if listing else "dom"),
            "item_url": item_url,
            "image_url": image_url,
            "image_count": image_count,
            "leaf_category_ids": leaf,
            "categories": [],
            "has_secondary_category": False,
            "variant_id": listing.get("VarId") or listing.get("varId") or "",
            "search_rank": listing.get("rank"),
            "item_specifics": [],
            "source": "ziniao",
        })
    if skipped_placeholder:
        print("  跳过占位卡 %d 张" % skipped_placeholder)
    if skipped_dead:
        print("  跳过已下架/失效条目 %d 条" % skipped_dead)
    return results


def fetch_item_detail(page, item, host):
    url = item.get("item_url") or ""
    if not url:
        print("    [跳过] 没有 item_url")
        return
    if url.startswith("/"):
        url = urljoin(host + "/", url)
    print("  详情 #%s %s" % (item.get("position"), (item.get("title") or "")[:50]))
    try:
        if page.is_closed():
            print("    [失败] 页面已关闭，无法抓详情")
            return
    except Exception:
        pass
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=180000)
    except Exception as e:
        print("    打开失败: %s" % str(e)[:150])
        return
    time.sleep(3.5)
    data = None
    for attempt in (1, 2):
        try:
            data = page.evaluate(EXTRACT_JS)
        except Exception as e:
            print("    解析失败(第%d次): %s" % (attempt, str(e)[:120]))
            data = None
        if data and data.get("specifics"):
            break
        if attempt == 1:
            print("    specifics 为空，等待后再试一次")
            time.sleep(3)
    if not data:
        # 不允许"空着也不说"：以前这里静默 return，导致 JSON 里 10 条只落 1 条却毫无提示
        print("    [失败] 详情页没解析出数据，本条 item_specifics 留空")
        return
    item["item_specifics"] = data.get("specifics") or []
    leaf = [str(x) for x in (item.get("leaf_category_ids") or []) if x]
    primary = data.get("primaryCategoryId") or ""
    secondary = data.get("secondaryCategoryId") or ""
    for cid in (primary, secondary):
        if cid and str(cid) not in leaf:
            leaf.append(str(cid))
    if not item.get("leaf_category_name"):
        item["leaf_category_name"] = data.get("primaryCategoryName") or ""
    # 面包屑：名称路径一定要留下（真机实测 4 级纯名称，ID 是 bn_ 形态没有数字 ID），
    # 类目数字 ID 以搜索页 listings.leafCat 为准
    cats = []
    breadcrumb_names = []
    for c in data.get("crumbs") or []:
        nm = (c.get("name") or "").strip()
        low = nm.lower()
        if not nm or low in ("breadcrumb", "category"):
            continue
        # 面包屑最后一级常是 "See more xxx" 链接，不是类目名（实测污染过 leaf_category_name）
        if re.match(r"(?i)^see\s*more\b", nm) or len(nm) > 40:
            continue
        breadcrumb_names.append(nm)
        if c.get("id"):
            cats.append({"id": str(c["id"]), "name": nm})
    item["categories"] = cats
    item["breadcrumb"] = breadcrumb_names
    item["category_path"] = " > ".join(breadcrumb_names)
    if not item.get("leaf_category_name") and breadcrumb_names:
        item["leaf_category_name"] = breadcrumb_names[-1]
    item["leaf_category_ids"] = leaf
    item["has_secondary_category"] = len(leaf) > 1
    if not item.get("legacy_item_id"):
        m = re.search(r"/itm/(?:[^/]+/)?(\d{9,15})", page.url)
        if m:
            item["legacy_item_id"] = m.group(1)
    print("    specifics=%d 项, 类目ID=%s, 面包屑=%s"
          % (len(item["item_specifics"]), leaf, item.get("category_path") or "(无)"))


def collect_on_page(page, keyword, site_code, max_items=120, detail_n=10):
    site = get_site(site_code)
    print("  打开站点首页以设置配送...")
    try:
        page.goto(site["host"], wait_until="domcontentloaded", timeout=180000)
    except Exception as e:
        print("  首页导航失败（%s），5 秒后重试" % e)
        time.sleep(5)
        page.goto(site["host"], wait_until="domcontentloaded", timeout=180000)
    time.sleep(3)
    ship = set_ship_to(page, site_code)
    if not ship:
        print("  配送弹层未设成（靠搜索 URL 的 _stpos/_fcid 兜底）")
    if "sch/i.html" in page.url:
        print("  配送设置后页面被带跑到搜索页，先回首页再搜: %s" % page.url[:100])
        page.goto(site["host"], wait_until="domcontentloaded", timeout=180000)
        time.sleep(2)

    items = []
    page_no = 1
    while len(items) < max_items and page_no <= 4:
        need = max_items - len(items)
        if need <= 0:
            break
        url = search_url(site_code, keyword, page=page_no, per_page=240)
        print("  搜索页 %d (还需 %d 条): %s" % (page_no, need, url[:130]))
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=180000)
        except Exception as e:
            print("  搜索导航失败（%s），5 秒后重试" % e)
            time.sleep(5)
            page.goto(url, wait_until="domcontentloaded", timeout=180000)
        time.sleep(3)
        listings = _dig_listings_array(page)
        batch = parse_listing_page(page, start_pos=len(items) + 1, need=need, listings=listings)
        print("  本页有效 %d 条，累计 %d" % (len(batch), len(items) + len(batch)))
        if not batch:
            print("  本页 0 条，停止翻页")
            break
        items.extend(batch)
        page_no += 1

    items = items[:max_items]
    promo = sum(1 for it in items if it.get("is_sponsored"))
    cats = {}
    for it in items:
        for cid in it.get("leaf_category_ids") or []:
            cats[cid] = cats.get(cid, 0) + 1
    print("  采集汇总: %d 条, 广告位 %d 条, 末级类目分布 %s"
          % (len(items), promo, sorted(cats.items(), key=lambda kv: -kv[1])[:5]))

    detail_page = page
    if detail_n > 0 and items:
        # 详情页是可选的：item specifics 搜索页没有内嵌数据块，只能进详情页；
        # 但 item id / 链接已经齐全，下游也可以按 id 去别处取，不必为此访问商品页。
        print("  拉前 %d 条的 item specifics（进商品详情页，共 %d 次请求）"
              % (min(detail_n, len(items)), min(detail_n, len(items))))
        for it in items[:detail_n]:
            fetch_item_detail(detail_page, it, site["host"])
            time.sleep(0.8)
    else:
        print("  detail=0：不进商品详情页。item specifics 留空，"
              "下游可用 item_id / item_url 自行取数")
    return {"items": items, "dominant_category_id": "", "aspect_refinements": []}
