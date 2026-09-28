# -*- coding: utf-8 -*-
"""读一条新建数据表的详情，看 listing_spy 到底把哪些字段抓下来了。

用无头浏览器（值由 JS 渲染），读 dsheet_item_specific_N 等字段的真实值。
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
SESSION_FILE = os.path.join(PROJ, "输出", "_session", "soldeazy_session.json")
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
ROW = sys.argv[1] if len(sys.argv) > 1 else "4551545"
BASE = "https://stiger.soldeazy.com"

state = json.load(open(SESSION_FILE, encoding="utf-8"))

READ_JS = r"""
() => {
  const out = {specs: [], others: {}, tabs: [], title: ''};
  // item specifics 槽位
  for (let i = 1; i <= 45; i++) {
    const nameEl = document.querySelector('.dsheet_item_specific_name[name="dsheet_item_specific_' + i + '_name"], #dsheet_item_specific_' + i + '_name');
    const valEl = document.querySelector('input[name="dsheet_item_specific_' + i + '"], #dsheet_item_specific_' + i);
    const n = nameEl ? (nameEl.value || nameEl.innerText || '') : '';
    const v = valEl ? (valEl.value || '') : '';
    if (n || v) out.specs.push({idx: i, name: n.trim(), value: String(v).trim()});
  }
  // 其它关键字段
  const pick = (sel) => { const el = document.querySelector(sel); return el ? (el.value || el.innerText || '') : null; };
  out.others = {
    title: pick('#dsheet_title, input[name="dsheet_title"]'),
    subtitle: pick('input[name="dsheet_subtitle"]'),
    sku: pick('input[name="dsheet_sku"], #dsheet_sku'),
    price: pick('input[name="dsheet_price"], #dsheet_price'),
    ebay_category: pick('input[name="dsheet_ebcategory"], #dsheet_ebcategory'),
    ebay_category_name: pick('#dsheet_ebcategory_name, [name="dsheet_ebcategory_name"]'),
    shop_initial: pick('#dsheet_shop_initial_hidden, input[name="dsheet_shop_initial"]'),
    site: pick('#dsheet_sitecode, select[name="dsheet_sitecode"]'),
    format: pick('#dsheet_format_hidden, input[name="dsheet_format"]'),
    condition: pick('select[name="dsheet_condition"], #dsheet_condition'),
    desc_len: (document.querySelector('textarea[name="dsheet_desc"], #dsheet_desc') || {}).value ?
              document.querySelector('textarea[name="dsheet_desc"], #dsheet_desc').value.length : 0,
  };
  // 页面里所有 item_specific 输入框（含空的）
  out.specInputs = Array.from(document.querySelectorAll('input[name^="dsheet_item_specific_"]')).length;
  out.pageText = (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 500);
  return out;
}
"""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN", user_agent=state.get("user_agent"))
        for ck in state.get("cookies") or []:
            c = {"name": ck.get("name"), "value": ck.get("value"),
                 "domain": ck.get("domain"), "path": ck.get("path") or "/"}
            if ck.get("expires"):
                c["expires"] = ck["expires"]
            try:
                ctx.add_cookies([c])
            except Exception:
                pass
        page = ctx.new_page()

        print("[1] 打开列表页 → 搜 rowid=%s" % ROW)
        page.goto(BASE + "/app/soldeazy/datasheet", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        page.fill("input[name=txtdsheetrowid]", ROW)
        page.click("#btn_search")
        time.sleep(4)
        print("    结果行数: %s" % page.evaluate("() => document.querySelectorAll('#tbl_dSheet tbody tr').length"))

        print("[2] 点 detail 打开详情")
        try:
            page.click("a.dsrid.detail", timeout=15000)
        except Exception as exc:
            print("    点击失败: %s" % str(exc)[:100])
        time.sleep(5)
        print("    当前 URL: %s" % page.url[:120])

        print("[3] 读取详情字段")
        try:
            info = page.evaluate(READ_JS)
        except Exception as exc:
            print("    读取失败: %s" % str(exc)[:150])
            info = None

        if info:
            print("\n=== item specifics（%d 项）===" % len(info["specs"]))
            for s in info["specs"]:
                print("   %2d. %-30s = %s" % (s["idx"], s["name"][:30], str(s["value"])[:60]))
            print("\n  item_specific 输入框总数: %s" % info.get("specInputs"))
            print("\n=== 其它字段 ===")
            for k, v in (info.get("others") or {}).items():
                print("   %-22s = %s" % (k, str(v)[:90]))
            print("\n=== 页面文本(前 400) ===")
            print("   %s" % info.get("pageText", "")[:400])

        stamp = time.strftime("%Y%m%d_%H%M%S")
        p = os.path.join(OUT, "detail_row_%s_%s.html" % (ROW, stamp))
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(page.content())
        print("\n  HTML 已存: %s" % os.path.basename(p))
        browser.close()


if __name__ == "__main__":
    main()
