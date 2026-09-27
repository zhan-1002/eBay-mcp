# -*- coding: utf-8 -*-
"""采样 eBay 新版 li.s-card 的真实字段选择器。只读，不改页面数据（只跑选择器查询）。

用法: python probe_scard.py [debuggingPort]
"""
import json
import os
import re
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else "58899"
DUMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "输出", "_dom")
DUMP_DIR = os.path.normpath(DUMP_DIR)
os.makedirs(DUMP_DIR, exist_ok=True)

CANDIDATES = {
    "title": [".s-card__title", ".su-styled-text.primary", "[role=heading]", "h3", ".s-item__title"],
    "price": [".s-card__price", ".s-item__price", "[class*=price]", ".su-styled-text"],
    "link": ["a.su-link", "a[href*='/itm/']", "a.s-card__link", "a"],
    "ad_badge": ["[class*=etrs]", "span.s-item__etrs", ".s-card__ad-badge", "[aria-label*=Sponsored i]",
                 ".su-card-container__ad-badge", "[class*=ad-badge]"],
    "subtitle": [".s-card__subtitle", ".s-item__subtitle", ".s-card__caption"],
    "location": [".s-card__location", ".s-item__location", "[class*=location]"],
    "seller": [".s-card__seller", ".s-item__seller-info", "[class*=seller]"],
    "condition": [".s-card__condition", ".s-item__condition", "[class*=condition]"],
    "sold": [".s-card__quantity-sold", ".s-item__quantitySold", "[class*=quantity]", "[class*=sold]"],
    "shipping": [".s-card__shipping", ".s-item__shipping", "[class*=shipping]", "[class*=logistics]"],
}

JS_CLASS_TALLY = r"""
() => {
  const cards = document.querySelectorAll('li.s-card');
  const counter = {};
  cards.forEach((c) => {
    c.querySelectorAll('*').forEach((el) => {
      const cls = (el.getAttribute('class') || '');
      cls.split(/\s+/).forEach((t) => { if (t) counter[t] = (counter[t] || 0) + 1; });
    });
  });
  return {cardCount: cards.length, tally: counter};
}
"""

JS_STRUCT = r"""
(i) => {
  const c = document.querySelectorAll('li.s-card')[i];
  if (!c) return null;
  const walk = (el, depth) => {
    const out = [];
    for (const ch of el.children) {
      const cls = (ch.getAttribute('class') || '');
      const txt = (ch.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 70);
      out.push({d: depth, tag: ch.tagName.toLowerCase(), cls: cls.slice(0, 110), txt: txt});
      if (depth < 4) out.push(...walk(ch, depth + 1));
    }
    return out;
  };
  return {
    cls: c.getAttribute('class') || '',
    text: (c.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 400),
    html: c.outerHTML.slice(0, 4000),
    tree: walk(c, 0).slice(0, 60)
  };
}
"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%s" % PORT)
        page = browser.contexts[0].pages[0]
        print("当前 url = %s" % page.url[:150])
        if "sch/i.html" not in page.url:
            print("不在搜索页，导航到 uk 搜索页 ...")
            page.goto("https://www.ebay.co.uk/sch/i.html?_nkw=wireless+earbuds&_ipg=60",
                      wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

        n = page.locator("li.s-card").count()
        print("li.s-card 命中 = %d" % n)

        print("\n[1] 候选字段选择器（在第 1 张卡片内计数）")
        card = page.locator("li.s-card").first
        for field, sels in CANDIDATES.items():
            print("  %s:" % field)
            for sel in sels:
                try:
                    cnt = card.locator(sel).count()
                except Exception as exc:
                    print("     %-30s 异常 %s" % (sel, str(exc)[:50]))
                    continue
                if cnt == 0:
                    continue
                txt = ""
                try:
                    txt = (card.locator(sel).first.inner_text() or "").replace("\n", " ")[:70]
                except Exception:
                    pass
                if not txt:
                    try:
                        txt = (card.locator(sel).first.get_attribute("href") or "")[:70]
                    except Exception:
                        pass
                print("     %-30s 数=%-3d 文本=%s" % (sel, cnt, txt))

        print("\n[2] 整页卡片内类名统计（top 45，用来看真实类名）")
        data = page.evaluate(JS_CLASS_TALLY)
        tally = sorted(data["tally"].items(), key=lambda kv: -kv[1])
        for tok, cnt in tally[:45]:
            print("   %-46s %d" % (tok, cnt))

        print("\n[3] 第 1 张卡片的 DOM 树（前 60 个节点）")
        s0 = page.evaluate(JS_STRUCT, 0)
        if s0:
            print("  card class = %s" % s0["cls"])
            print("  卡内文本   = %s" % s0["text"])
            for node in s0["tree"]:
                print("   %s<%s class=%s> %s" % ("  " * node["d"], node["tag"], node["cls"], node["txt"]))

        print("\n[4] 前 5 张卡片的关键文本（标题/价格/广告线索）")
        for i in range(min(5, n)):
            s = page.evaluate(JS_STRUCT, i)
            if not s:
                continue
            print("  --- #%d ---" % (i + 1))
            print("     %s" % s["text"][:240])

        stamp = time.strftime("%Y%m%d_%H%M%S")
        hp = os.path.join(DUMP_DIR, "cards_%s.html" % stamp)
        with open(hp, "w", encoding="utf-8") as f:
            f.write(page.content())
        print("\n  HTML dump: %s" % hp)
        sp = os.path.join(DUMP_DIR, "cards_%s.png" % stamp)
        try:
            page.screenshot(path=sp)
            print("  截图: %s" % sp)
        except Exception as exc:
            print("  截图失败: %s" % exc)

        print("\n完成（未清理进程）")


if __name__ == "__main__":
    main()
