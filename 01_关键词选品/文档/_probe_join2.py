# -*- coding: utf-8 -*-
"""清点搜索页能拿到什么、拿不到什么：真实条目数 + 内嵌 listings 的完整字段。"""
import json
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else "58899"

JS = r"""
() => {
  const cards = Array.from(document.querySelectorAll('li.s-card'));
  const rows = cards.map((c) => {
    const q = (sel) => { const e = c.querySelector(sel); return e ? (e.innerText || '').replace(/\s+/g, ' ').trim() : ''; };
    const a = c.querySelector("a[href*='/itm/']");
    const href = a ? (a.getAttribute('href') || '') : '';
    const m = href.match(/\/itm\/(\d+)/);
    return {title: q('.s-card__title'), price: q('.s-card__price'), subtitle: q('.s-card__subtitle'),
            attr: Array.from(c.querySelectorAll('.s-card__attribute-row')).map(e => (e.innerText||'').replace(/\s+/g,' ').trim()),
            image: (c.querySelector('img') ? (c.querySelector('img').getAttribute('src') || '') : '').slice(0, 60),
            id: m ? m[1] : ''};
  });
  const html = document.documentElement.innerHTML;
  const key = '"listings":[';
  const i = html.indexOf(key);
  let arr = [];
  if (i >= 0) {
    let j = i + key.length - 1, depth = 0, inStr = false, esc = false, end = -1;
    for (let k = j; k < html.length; k++) {
      const ch = html[k];
      if (inStr) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === '"') inStr = false; continue; }
      if (ch === '"') { inStr = true; continue; }
      if (ch === '[' || ch === '{') depth++;
      else if (ch === ']' || ch === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
    }
    try { arr = JSON.parse(html.slice(j, end)); } catch (e) { arr = []; }
  }
  return {cards: rows, listings: arr, url: location.href};
}
"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%s" % PORT)
        page = browser.contexts[0].pages[0]
        d = page.evaluate(JS)
        cards, listings = d["cards"], d["listings"]
        print("url = %s" % d["url"][:140])
        print("卡片数 = %d ; 内嵌 listings = %d" % (len(cards), len(listings)))

        ph = [i + 1 for i, c in enumerate(cards) if c["title"].strip().lower() in ("shop on ebay", "")]
        print("占位卡（Shop on eBay）位置 = %s" % ph)
        real = [c for c in cards if c["title"].strip().lower() not in ("shop on ebay", "") ]
        print("真实条目 = %d" % len(real))
        print("卡片没取到 itemId 的 = %d" % sum(1 for c in cards if not c["id"]))

        ids_cards = [c["id"] for c in cards if c["id"]]
        by_id = {str(x.get("itemId")): x for x in listings}
        print("\njoin: 卡片id %d 个 / listings %d 个 / 交集 %d"
              % (len(set(ids_cards)), len(by_id), len(set(ids_cards) & set(by_id))))
        agg = [k for k in by_id if k not in set(ids_cards)]
        print("聚合卡（只在 listings 里：同款多卖家）数 = %d" % len(agg))

        if listings:
            print("\nlistings 每条的全部字段 = %s" % list(listings[0].keys()))
            print("前 4 条原文:")
            for x in listings[:4]:
                print("   %s" % json.dumps(x, ensure_ascii=False))

        pr = [x for x in listings if x.get("promoted")]
        print("\npromoted=true = %d / %d" % (len(pr), len(listings)))
        cats = {}
        for x in listings:
            cats[x.get("leafCat")] = cats.get(x.get("leafCat"), 0) + 1
        print("leafCat 分布 top8: %s" % sorted(cats.items(), key=lambda kv: -kv[1])[:8])

        print("\n前 5 条真实卡片（卡片 DOM 上到底带什么）:")
        for c in real[:5]:
            info = by_id.get(c["id"], {})
            print("  id=%s promoted=%s leafCat=%s" % (c["id"], info.get("promoted"), info.get("leafCat")))
            print("     title = %s" % c["title"][:80])
            print("     price = %s | subtitle(成色) = %s" % (c["price"][:18], c["subtitle"][:26]))
            print("     attrRows = %s" % c["attr"][:4])


if __name__ == "__main__":
    main()
