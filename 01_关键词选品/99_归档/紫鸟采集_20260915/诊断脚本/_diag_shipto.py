# -*- coding: utf-8 -*-
"""验证：set_ship_to 是否导致页面/上下文失效（浏览器被关闭）。"""
import sys
import time
import traceback

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

from ziniao_runtime import (  # noqa: E402
    exit_ziniao, get_browser_list, kill_ziniao, match_store, open_store,
    start_ziniao, wait_for_server,
)
from collect_ziniao import SHIP_DIALOG_SELECTORS, DIALOG_CONTAINER_SELECTORS  # noqa: E402
from sites import get_site, search_url  # noqa: E402

STORE, SITE, KW = "haihu_8075", "uk", "wireless earbuds"


def probe_page(tag, page):
    """打印页面/上下文健康状况。"""
    out = []
    try:
        out.append("url=%s" % page.url[:60])
    except Exception as exc:
        out.append("url 失败(%s)" % str(exc)[:40])
    try:
        out.append("closed=%s" % page.is_closed())
    except Exception as exc:
        out.append("is_closed 失败(%s)" % str(exc)[:40])
    try:
        ctx = page.context
        out.append("pages=%d" % len(ctx.pages))
    except Exception as exc:
        out.append("pages 失败(%s)" % str(exc)[:40])
    print("   [%s] %s" % (tag, " | ".join(out)))


def try_eval(page, expr, tag):
    try:
        v = page.evaluate(expr)
        print("   [%s] evaluate OK -> %r" % (tag, str(v)[:70]))
        return True
    except Exception as exc:
        print("   [%s] evaluate 失败 -> %s" % (tag, str(exc)[:100]))
        return False


api_port = None
try:
    kill_ziniao()
    api_port = start_ziniao()
    assert wait_for_server(api_port), "服务未就绪"
    stores = get_browser_list(api_port)
    zn = match_store(stores, STORE)
    info = {s.get("browserName"): s for s in stores}[zn]
    dport = open_store(api_port, info.get("browserOauth", "")).get("debuggingPort")
    print("店铺=%s port=%s" % (zn, dport))
    time.sleep(10)

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    for attempt in range(1, 6):
        try:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % dport)
            break
        except Exception as exc:
            print("CDP 第%d次失败 %s" % (attempt, str(exc)[:60]))
            time.sleep(5)
    ctx = browser.contexts[0]
    page = ctx.pages[0]
    print("上下文数=%d 页面数=%d" % (len(browser.contexts), len(ctx.pages)))

    site = get_site(SITE)
    print("\n[1] 导航首页")
    page.goto(site["host"], wait_until="domcontentloaded", timeout=180000)
    time.sleep(3)
    probe_page("首页后", page)

    print("\n[2] 逐个试配送入口选择器（只 count/可见性，不点击）")
    for sel in SHIP_DIALOG_SELECTORS:
        try:
            loc = page.locator(sel)
            c = loc.count()
            vis = False
            if c:
                try:
                    vis = loc.first.is_visible()
                except Exception:
                    pass
            print("   %-40s count=%-3d visible=%s" % (sel, c, vis))
        except Exception as exc:
            print("   %-40s 异常 %s" % (sel, str(exc)[:50]))
    print("   弹层容器:")
    for sel in DIALOG_CONTAINER_SELECTORS:
        try:
            print("   %-40s count=%d" % (sel, page.locator(sel).count()))
        except Exception as exc:
            print("   %-40s 异常 %s" % (sel, str(exc)[:50]))

    print("\n[3] 调用 set_ship_to（现实现）")
    from collect_ziniao import set_ship_to
    try:
        rv = set_ship_to(page, SITE)
        print("   返回: %r" % (rv,))
    except Exception as exc:
        print("   异常: %s" % str(exc)[:200])
        print(traceback.format_exc()[-800:])
    probe_page("set_ship_to 后", page)

    print("\n[4] 页面还能用吗")
    try_eval(page, "1+1", "算术")
    try_eval(page, "document.title", "标题")

    print("\n[5] 试着导航搜索页")
    try:
        page.goto(search_url(SITE, KW, page=1, per_page=240),
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        print("   OK url=%s" % page.url[-50:])
        print("   li.s-card = %d" % page.locator("li.s-card").count())
    except Exception as exc:
        print("   失败: %s" % str(exc)[:160])

    print("\n[6] 上下文里现在有几个页面")
    try:
        print("   pages=%d urls=%s" % (len(ctx.pages), [p.url[:40] for p in ctx.pages]))
    except Exception as exc:
        print("   读取失败: %s" % str(exc)[:80])

    try:
        browser.close()
    except Exception:
        pass
finally:
    if api_port:
        try:
            exit_ziniao(api_port)
        except Exception:
            pass
        kill_ziniao()
