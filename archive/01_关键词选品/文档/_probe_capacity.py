# -*- coding: utf-8 -*-
"""量采集容量：_ipg 上限、单页条数、翻页深度、每页耗时、是否出现验证墙。

只读测量，不改项目文件。用法: python probe_capacity.py [debuggingPort]
"""
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else "58899"
KW = "wireless earbuds"
HOST = "https://www.ebay.co.uk"


def count(page):
    out = {}
    for sel in ["li.s-card", "li.s-item", "ul.srp-results li"]:
        try:
            out[sel] = page.locator(sel).count()
        except Exception:
            out[sel] = -1
    return out


def first_items(page, n=3):
    rows = []
    try:
        total = page.locator("li.s-card").count()
    except Exception:
        return rows
    for i in range(min(n, total)):
        try:
            t = page.locator("li.s-card").nth(i).locator(".s-card__title").first.inner_text().strip()
        except Exception:
            t = ""
        try:
            p = page.locator("li.s-card").nth(i).locator(".s-card__price").first.inner_text().strip()
        except Exception:
            p = ""
        rows.append("#%d %s | %s" % (i + 1, p[:14], t[:60]))
    return rows


def heading(page):
    for sel in [".srp-controls__count-heading", "h1.srp-controls__count-heading", "[class*=count-heading]"]:
        try:
            if page.locator(sel).count() > 0:
                return (page.locator(sel).first.inner_text() or "").replace("\n", " ").strip()[:80]
        except Exception:
            pass
    return ""


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%s" % PORT)
        page = browser.contexts[0].pages[0]
        print("起始 url = %s\n" % page.url[:150])

        print("### 测试 1: _ipg 参数是否被尊重（单页最多给多少条）")
        for ipg in [60, 120, 240]:
            url = "%s/sch/i.html?_nkw=%s&_ipg=%d&_stpos=SW1A1AA&_fcid=3&rt=nc" % (
                HOST, KW.replace(" ", "+"), ipg)
            t0 = time.time()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print("  _ipg=%-4d 导航异常 %.1fs: %s" % (ipg, time.time() - t0, str(exc)[:90]))
                continue
            time.sleep(2)
            c = count(page)
            print("  _ipg=%-4d 耗时%5.1fs  落地=%s" % (ipg, time.time() - t0, page.url[:110]))
            print("             命中 %s  计数头='%s'" % (c, heading(page)))
            for row in first_items(page, 2):
                print("             %s" % row)

        print("\n### 测试 2: 翻页深度（_ipg=240，逐页量条数与耗时）")
        base = "%s/sch/i.html?_nkw=%s&_ipg=240&_stpos=SW1A1AA&_fcid=3&rt=nc" % (HOST, KW.replace(" ", "+"))
        total = 0
        for pgn in range(1, 8):
            url = base + "&_pgn=%d" % pgn
            t0 = time.time()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print("  第%d页 导航失败 %.1fs: %s" % (pgn, time.time() - t0, str(exc)[:90]))
                break
            time.sleep(2)
            c = count(page)
            n_card = c.get("li.s-card", 0)
            total += max(0, n_card)
            html_len = page.evaluate("document.documentElement.innerHTML.length")
            wall = any(s in (page.content()[:4000] if False else "") for s in [])
            print("  第%d页 耗时%5.1fs  li.s-card=%-4d 累计=%-4d html=%dKB  落地=%s"
                  % (pgn, time.time() - t0, n_card, total, html_len // 1024, page.url[-60:]))
            if n_card == 0:
                print("     -> 0 条，翻页到此为止")
                break
            try:
                if page.locator("a.pagination__next").count() == 0:
                    print("     -> 没有下一页链接")
                    break
            except Exception:
                pass

        print("\n### 测试 3: 每页条数是否稳定（同一页重复量，看是否有懒加载）")
        try:
            page.goto(base + "&_pgn=1", wait_until="domcontentloaded", timeout=60000)
            for wait_s in [0, 3, 8]:
                time.sleep(wait_s if wait_s == 0 else 3)
                print("  等待%-2ds 后 li.s-card = %d" % (wait_s, page.locator("li.s-card").count()))
        except Exception as exc:
            print("  失败: %s" % str(exc)[:100])

        print("\n完成（未清理进程）")


if __name__ == "__main__":
    main()
