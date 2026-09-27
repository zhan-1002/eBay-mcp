# -*- coding: utf-8 -*-
"""清点搜索页上的真实条目 vs 占位卡；并核对内嵌 listings 与卡片能否按序 join。"""
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
    return {
      title: q('.s-card__title'),
      price: q('.s-card__price'),
      subtitle: q('.s-card__subtitle'),
      attr: Array.from(c.querySelectorAll('.s-card__attribute-row')).map(e => (e.innerText||'').replace(/\s+/g,' ').trim()),
      id: m ? m[1] : ''
    };
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
        cards = d["cards"]
        listings = d["listings"]
        print("url = %s" % d["url"][:150])
        print("卡片数 = %d ；内嵌 listings = %d" % (len(cards), len(listings)))

        ph = [i for i, c in enumerate(cards) if c["title"].strip().lower() in ("shop on ebay", "")]
        print("占位卡索引 = %s （各位置: %s）" % (ph, [i + 1 for i in ph]))
        real = [c for c in cards if c["title"].strip().lower() != "shop on ebay" and c["title"].strip()]
        print("真实条目 = %d" % len(real))
        print("有 itemId 的卡片 = %d ；没取到 id 的 = %d"
              % (sum(1 for c in cards if c["id"]), sum(1 for c in cards if not c["id"])))

        print("\n按 itemId join 检查（卡片 id vs listings itemId）:")
        ids_cards = [c["id"] for c in cards if c["id"]]
        ids_list = [str(x.get("itemId")) for x in listings]
        inter = len(set(ids_cards) & set(ids_list))
        print("  卡片 id 集合大小 = %d ；listings 集合大小 = %d ；交集 = %d" % (len(set(ids_cards)), len(set(ids_list)), inter))
        print("  前 5 个卡片 id  = %s" % ids_cards[:5])
        print("  前 5 个 listings = %s" % ids_list[:5])
        by_id = {str(x.get("itemId")): x for x in listings}
        miss = [i for i in ids_cards if i not in by_id]
        print("  卡片有、listings 没有的 id 数 = %d %s" % (len(miss), miss[:5]))

        print("\npromoted 标记统计（来自 listings）:")
        pr = [x for x in listings if x.get("promoted")]
        print("  promoted=true = %d / %d" % (len(pr), len(listings)))
        print("  前 6 条 promoted 的 rank = %s" % [x.get("rank") for x in listings[:6]])

        print("\nleafCat 分布:")
        cats = {}
        for x in listings:
            c = x.get("leafCat")
            cats[c] = cats.get(c, 0) + 1
        for cid, n in sorted(cats.items(), key=lambda kv: -kv[1])[:8]:
            print("  leafCat %-8s %d" % (cid, n))

        print("\n前 6 条真实卡片的字段（看卡片上到底带哪些信息）:")
        for c in real[:6]:
            info = by_id.get(c["id"], {})
            print("  id=%-14s promoted=%-5s leafCat=%-7s" % (c["id"], info.get("promoted"), info.get("leafCat")))
            print("     title   = %s" % c["title"][:85])
            print("     price   = %s | subtitle = %s" % (c["price"][:20], c["subtitle"][:30]))
            print("     attrRow = %s" % c["attr"][:4])


if __name__ == "__main__":
    main()
