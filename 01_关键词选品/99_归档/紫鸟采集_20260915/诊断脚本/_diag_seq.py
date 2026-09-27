# -*- coding: utf-8 -*-
"""严格复刻 collect_on_page 的调用序列，一步步验证 item_specifics 是否稳定落地。

与真跑的差别只有：短超时（60s 而不是 180s），每条日志立即 flush 落盘。
"""
import sys
import time

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

from ziniao_runtime import (  # noqa: E402
    exit_ziniao, get_browser_list, kill_ziniao, match_store, open_store,
    start_ziniao, wait_for_server,
)
from collect_ziniao import (  # noqa: E402
    _dig_listings_array, fetch_item_detail, parse_listing_page, set_ship_to,
)
from sites import get_site, search_url  # noqa: E402

LOG = open(r"C:\Users\admin\Desktop\新建文件夹\_diag_seq.log", "w", encoding="utf-8")


def say(msg):
    print(msg, flush=True)
    LOG.write(msg + "\n")
    LOG.flush()


STORE, SITE, KW = "haihu_8075", "uk", "wireless earbuds"
api_port = None
try:
    kill_ziniao()
    api_port = start_ziniao()
    assert wait_for_server(api_port), "服务未就绪"
    stores = get_browser_list(api_port)
    zn = match_store(stores, STORE)
    info = {s.get("browserName"): s for s in stores}[zn]
    dport = open_store(api_port, info.get("browserOauth", "")).get("debuggingPort")
    say("店铺=%s port=%s" % (zn, dport))
    time.sleep(10)

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    for attempt in range(1, 6):
        try:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % dport)
            break
        except Exception as exc:
            say("CDP 第%d次失败 %s" % (attempt, str(exc)[:60]))
            time.sleep(5)
    page = browser.contexts[0].pages[0]
    site = get_site(SITE)

    def alive(tag):
        try:
            return "%s: closed=%s url=%s" % (tag, page.is_closed(), page.url[:60])
        except Exception as exc:
            return "%s: 读取失败 %s" % (tag, str(exc)[:60])

    say("\n[1] 首页")
    page.goto(site["host"], wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    say("   " + alive("首页后"))

    say("\n[2] set_ship_to")
    say("   返回 %r" % (set_ship_to(page, SITE),))
    say("   " + alive("set_ship_to后"))

    say("\n[3] 搜索 1 页")
    page.goto(search_url(SITE, KW, page=1, per_page=240),
              wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    say("   " + alive("搜索后"))
    listings = _dig_listings_array(page)
    items = parse_listing_page(page, start_pos=1, need=120, listings=listings)
    say("   解析出 %d 条" % len(items))

    say("\n[4] 逐条抓详情（前 3 条，复刻真跑调用）")
    for it in items[:3]:
        say("   --- #%s %s" % (it["position"], (it["title"] or "")[:50]))
        say("       " + alive("进入前"))
        t0 = time.time()
        try:
            fetch_item_detail(page, it, site["host"])
        except Exception as exc:
            say("       fetch_item_detail 抛异常: %s" % str(exc)[:150])
        say("       耗时 %.1fs -> specifics=%d 类目=%s"
            % (time.time() - t0, len(it.get("item_specifics") or []), it.get("leaf_category_ids")))
        say("       " + alive("出来后"))

    say("\n[5] 回到搜索页再验证")
    try:
        page.goto(search_url(SITE, KW, page=1, per_page=240),
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        say("   li.s-card = %d" % page.locator("li.s-card").count())
    except Exception as exc:
        say("   失败: %s" % str(exc)[:160])

    say("\n汇总: 有 specifics 的 = %s" % [i["position"] for i in items[:3] if i.get("item_specifics")])
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
    LOG.close()
