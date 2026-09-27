# -*- coding: utf-8 -*-
"""在活着的紫鸟会话上验证两件事：
  A) 页面内嵌 JSON 的 listings 数组（含 promoted / leafCat）能否稳定取到并与卡片一一对应
  B) s-card 各字段的真实选择器（多卡采样，找出稳定的一套）
只读，不改页面数据。
"""
import json
import os
import re
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else "58899"
DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "输出", "_dom")
DUMP = os.path.normpath(DUMP)
os.makedirs(DUMP, exist_ok=True)

JS_LISTINGS = r"""
() => {
  const html = document.documentElement.innerHTML;
  const key = '"listings":[';
  const i = html.indexOf(key);
  if (i < 0) return {found: false, reason: 'key not found'};
  let j = i + key.length - 1;           // 指向 '['
  let depth = 0, inStr = false, esc = false, end = -1;
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
    if (ch === ']' || ch === '}') {
      depth--;
      if (depth === 0) { end = k + 1; break; }
    }
  }
  if (end < 0) return {found: false, reason: 'unbalanced'};
  const raw = html.slice(j, end);
  try {
    const arr = JSON.parse(raw);
    return {found: true, count: arr.length, sample: arr.slice(0, 3), keys: Object.keys(arr[0] || {})};
  } catch (e) {
    return {found: false, reason: 'parse: ' + e.message, rawHead: raw.slice(0, 200)};
  }
}
"""

JS_CARD = r"""
(i) => {
  const c = document.querySelectorAll('li.s-card')[i];
  if (!c) return null;
  const q = (sel) => { const el = c.querySelector(sel); return el ? (el.innerText || '').replace(/\s+/g, ' ').trim() : ''; };
  const qa = (sel) => Array.from(c.querySelectorAll(sel)).map((e) => (e.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
  let href = '';
  const a = c.querySelector("a[href*='/itm/']") || c.querySelector('a.s-card__link');
  if (a) href = a.getAttribute('href') || '';
  const m = href.match(/\/itm\/(\d+)/);
  return {
    cls: c.getAttribute('class') || '',
    title: q('.s-card__title'),
    subtitle: q('.s-card__subtitle'),
    priceAll: qa('.s-card__price'),
    attrRows: qa('.s-card__attribute-row'),
    footer: q('.s-card__footer'),
    href: href.slice(0, 160),
    itemId: m ? m[1] : '',
    text: (c.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300),
    hasEtrs: c.querySelectorAll('[class*=etrs], [class*=ad-badge]').length,
    badgeTexts: Array.from(c.querySelectorAll('span,div')).map(e => (e.innerText||'').trim()).filter(t => /sponsored|promoted|advert/i.test(t)).slice(0,3)
  };
}
"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%s" % PORT)
        page = browser.contexts[0].pages[0]
        print("url = %s" % page.url[:140])

        print("\n[A] 页面内嵌 listings JSON")
        data = page.evaluate(JS_LISTINGS)
        print("  found = %s" % data.get("found"))
        if data.get("found"):
            print("  条数  = %s" % data.get("count"))
            print("  字段  = %s" % data.get("keys"))
            print("  前3条 = %s" % json.dumps(data.get("sample"), ensure_ascii=False))
            arr = page.evaluate("""() => {
                const html = document.documentElement.innerHTML;
                const key = '"listings":[';
                const i = html.indexOf(key);
                if (i < 0) return [];
                let j = i + key.length - 1, depth = 0, inStr = false, esc = false, end = -1;
                for (let k = j; k < html.length; k++) {
                  const ch = html[k];
                  if (inStr) { if (esc) esc = false; else if (ch === '\\\\') esc = true; else if (ch === '"') inStr = false; continue; }
                  if (ch === '"') { inStr = true; continue; }
                  if (ch === '[' || ch === '{') depth++;
                  else if (ch === ']' || ch === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
                }
                try { return JSON.parse(html.slice(j, end)); } catch (e) { return []; }
            }""")
            promoted = sum(1 for x in arr if x.get("promoted"))
            print("  promoted=true 条数 = %d / %d" % (promoted, len(arr)))
            cats = {}
            for x in arr:
                cats[x.get("leafCat")] = cats.get(x.get("leafCat"), 0) + 1
            top = sorted(cats.items(), key=lambda kv: -kv[1])[:6]
            print("  leafCat 分布 top: %s" % top)
        else:
            print("  失败原因: %s" % data.get("reason"))
            print("  rawHead: %s" % str(data.get("rawHead"))[:200])

        print("\n[B] s-card 多卡采样（第 1/3/5/10 张）")
        n = page.locator("li.s-card").count()
        print("  卡片总数 = %d" % n)
        cards = {}
        for i in [0, 2, 4, 9]:
            if i >= n:
                continue
            c = page.evaluate(JS_CARD, i)
            cards[i] = c
            print("  --- 索引 %d ---" % i)
            print("     cls      = %s" % c["cls"])
            print("     itemId   = %s" % c["itemId"])
            print("     title    = %s" % c["title"][:90])
            print("     subtitle = %s" % c["subtitle"][:50])
            print("     priceAll = %s" % c["priceAll"])
            print("     attrRows = %s" % c["attrRows"][:4])
            print("     footer   = %s" % c["footer"][:80])
            print("     etrs数   = %s  badge=%s" % (c["hasEtrs"], c["badgeTexts"]))

        # 卡片顺序 vs listings 顺序 是否一一对应
        if data.get("found") and cards:
            arr = page.evaluate("""() => {
                const html = document.documentElement.innerHTML;
                const key = '"listings":[';
                const i = html.indexOf(key);
                if (i < 0) return [];
                let j = i + key.length - 1, depth = 0, inStr = false, esc = false, end = -1;
                for (let k = j; k < html.length; k++) {
                  const ch = html[k];
                  if (inStr) { if (esc) esc = false; else if (ch === '\\\\') esc = true; else if (ch === '"') inStr = false; continue; }
                  if (ch === '"') { inStr = true; continue; }
                  if (ch === '[' || ch === '{') depth++;
                  else if (ch === ']' || ch === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
                }
                try { return JSON.parse(html.slice(j, end)); } catch (e) { return []; }
            }""")
            print("\n[C] 卡片 itemId vs listings 顺序对齐检查")
            for i, c in cards.items():
                lid = arr[i].get("itemId") if i < len(arr) else None
                print("  索引 %-3d 卡片itemId=%-14s listings[%d].itemId=%-14s promoted=%s 匹配=%s"
                      % (i, c["itemId"], i, lid, arr[i].get("promoted") if i < len(arr) else None,
                         str(c["itemId"]) == str(lid)))

        print("\n结论: listings 可作为 promoted/leafCat 的数据源（需按 itemId 与卡片 join）")


if __name__ == "__main__":
    main()
