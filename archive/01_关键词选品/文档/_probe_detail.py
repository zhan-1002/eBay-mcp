# -*- coding: utf-8 -*-
"""探商品详情页：item specifics 到底在哪（哪套选择器 / 是否有内嵌 JSON）。

为了不依赖紫鸟会话，直接用一个独立 chromium 打开一个真实商品页来定选择器。
用法: python _probe_detail.py [item_url]
"""
import json
import os
import re
import sys
import time

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://www.ebay.co.uk/itm/226445714488")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "输出", "_dom")
OUT = os.path.normpath(OUT)
os.makedirs(OUT, exist_ok=True)

DETECT_JS = r"""
() => {
  const res = {
    containers: {},
    tables: [],
    preloadedKeys: [],
    specKeys: [],
    ariaPairs: []
  };
  const sel = [
    '#viTabs_0_is', '.vim.x-about-this-item', '[data-testid="ux-layout-section-evo"]',
    '.ux-layout-section-evo', '[class*="about-this-item"]',
    '.ux-labels-values', '.ux-layout-section--features', '#viTabs_0_is .ux-labels-values'
  ];
  sel.forEach((s) => { try { res.containers[s] = document.querySelectorAll(s).length; } catch (e) {} });

  // 新版 item specifics 常见为 dl/dt/dd
  document.querySelectorAll('dl').forEach((dl) => {
    const dts = dl.querySelectorAll('dt'), dds = dl.querySelectorAll('dd');
    if (dts.length && dts.length === dds.length) {
      const rows = [];
      dts.forEach((dt, i) => rows.push([dt.innerText.replace(/\s+/g,' ').trim(), dds[i].innerText.replace(/\s+/g,' ').trim()]));
      if (rows.length) res.tables.push(rows.slice(0, 12));
    }
  });

  // 内嵌 state 里找 specifics 相关键
  const html = document.documentElement.innerHTML;
  ['"itemSpecifics"', 'localizedAspects', '"aspects"', 'aboutThisItem', 'ITEM_SPECIFICS', '"specifics"'].forEach((k) => {
    let i = html.indexOf(k);
    if (i >= 0) res.specKeys.push(k + '@' + i);
  });
  // 页面 js 变量名
  try {
    Object.keys(window).forEach((k) => {
      if (/preload|__.*state|dataLayer|__NEXT|initial/i.test(k)) res.preloadedKeys.push(k);
    });
  } catch (e) {}

  // aria 成对：排除物流/退货类噪音，看剩下什么
  const noise = /postage|delivery|return|location|collect|condition|seller|payment/i;
  document.querySelectorAll('[aria-label]').forEach((el) => {
    const t = (el.innerText || '').trim();
    if (t && /^[A-Za-z][A-Za-z \/&-]{2,24}:/.test(t) && t.length < 120) {
      const i2 = t.indexOf(':');
      const name = t.slice(0, i2).trim();
      if (!noise.test(name)) res.ariaPairs.push([name, t.slice(i2 + 1).trim().slice(0, 60)]);
    }
  });
  res.ariaPairs = res.ariaPairs.slice(0, 25);
  return res;
}
"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(locale="en-GB")
        print("打开: %s" % URL)
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        time.sleep(4)
        print("title = %s" % (page.title() or "")[:100])
        d = page.evaluate(DETECT_JS)
        print("\n容器命中数:")
        for k, v in d["containers"].items():
            print("   %-42s %d" % (k, v))
        print("\ndl/dt/dd 成对表（前 3 个）:")
        for tbl in d["tables"][:3]:
            print("   --- 共 %d 行 ---" % len(tbl))
            for name, value in tbl:
                print("      %-24s = %s" % (name[:24], value[:60]))
        print("\n内嵌 state 里的 specifics 相关键: %s" % (d["specKeys"] or "无"))
        print("window 上的预加载变量: %s" % (d["preloadedKeys"][:10] or "无"))
        print("\n非物流类 aria 成对（前 25）:")
        for name, value in d["ariaPairs"]:
            print("   %-24s = %s" % (name[:24], value[:60]))

        hp = os.path.join(OUT, "detail_%s.html" % time.strftime("%Y%m%d_%H%M%S"))
        with open(hp, "w", encoding="utf-8") as f:
            f.write(page.content())
        print("\nHTML dump: %s" % hp)

        # 再直接从 HTML 里挖 specifics 数据块
        html = page.content()
        for key in ['"itemSpecifics"', 'localizedAspects', '"aspects"']:
            i = html.find(key)
            print("\n%s -> 位置 %s" % (key, i))
            if i > 0:
                print("   …%s…" % html[i:i + 400].replace("\n", " "))
        browser.close()


if __name__ == "__main__":
    main()
