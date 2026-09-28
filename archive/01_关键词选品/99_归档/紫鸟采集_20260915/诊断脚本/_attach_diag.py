# -*- coding: utf-8 -*-
"""对还开着的紫鸟窗口（--keep 留下的）做只读接管诊断：不导航、不改页面，只观察。

用法:  python attach_diag.py 58899
"""
import sys
import time

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "58899"

print("接管 CDP http://127.0.0.1:%s" % PORT)
with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%s" % PORT)
    print("contexts =", len(browser.contexts))
    ctx = browser.contexts[0]
    print("pages    =", len(ctx.pages))
    for i, p in enumerate(ctx.pages):
        print("  page[%d] url = %s" % (i, p.url[:160]))
        try:
            print("           title = %s" % (p.title() or "")[:100])
        except Exception as exc:
            print("           title 读取失败: %s" % str(exc)[:80])

    page = ctx.pages[0]
    print("\n--- 只读观察（不导航）---")
    try:
        print("url          :", page.url[:200])
    except Exception as exc:
        print("url 读取失败:", exc)
    for expr, label in [("document.readyState", "readyState"),
                        ("document.title", "title"),
                        ("location.href", "location.href"),
                        ("document.body ? document.body.innerText.slice(0,300) : '(no body)'", "body 文本前300")]:
        try:
            print("%-14s: %s" % (label, str(page.evaluate(expr))[:300]))
        except Exception as exc:
            print("%-14s: 失败 -> %s" % (label, str(exc)[:120]))
    try:
        print("body 长度     :", page.evaluate("document.body ? document.body.innerHTML.length : 0"))
    except Exception as exc:
        print("body 长度失败 :", str(exc)[:120])

    print("\n--- 再试一次导航（超时 30s，wait_until=commit）---")
    for target in ["https://www.ebay.co.uk/sch/i.html?_nkw=wireless+earbuds&_ipg=60"]:
        t0 = time.time()
        try:
            page.goto(target, wait_until="commit", timeout=30000)
            print("  commit 成功，耗时 %.1fs，url=%s" % (time.time() - t0, page.url[:160]))
        except Exception as exc:
            print("  commit 失败，耗时 %.1fs: %s" % (time.time() - t0, str(exc)[:200]))
            continue
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            print("  domcontentloaded 到了")
        except Exception as exc:
            print("  domcontentloaded 没等到: %s" % str(exc)[:160])
        print("  readyState =", page.evaluate("document.readyState"))
        try:
            print("  li.s-item  =", page.locator("li.s-item").count())
            print("  li.s-card  =", page.locator("li.s-card").count())
        except Exception as exc:
            print("  计数失败: %s" % str(exc)[:120])
    print("\n诊断结束（未清理进程）")
