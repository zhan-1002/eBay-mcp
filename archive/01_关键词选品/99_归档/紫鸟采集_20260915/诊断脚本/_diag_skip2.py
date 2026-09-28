# -*- coding: utf-8 -*-
"""精确统计每张卡的跳过原因（不采集数据）。"""
import sys
import time
from collections import Counter

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

from ziniao_runtime import (  # noqa: E402
    exit_ziniao, get_browser_list, kill_ziniao, match_store, open_store,
    start_ziniao, wait_for_server,
)
from collect_ziniao import (  # noqa: E402
    CARD_SELECTOR_CANDIDATES, DEAD_PATTERNS, PLACEHOLDER_TITLES, _card_title,
    _dig_listings_array, parse_listing_page,
)
from sites import get_site, search_url  # noqa: E402

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
    page = browser.contexts[0].pages[0]

    for pgn in (1, 2):
        url = search_url(SITE, KW, page=pgn, per_page=240)
        page.goto(url, wait_until="domcontentloaded", timeout=180000)
        time.sleep(3)
        sel, count = None, 0
        for s in CARD_SELECTOR_CANDIDATES:
            c = page.locator(s).count()
            if c:
                sel, count = s, c
                break
        print("\n" + "=" * 70)
        print("第 %d 页 | 选择器=%s 卡片=%d | 落地=%s" % (pgn, sel, count, page.url[-40:]))
        print("=" * 70)

        reason = Counter()
        samples = {}
        cards = page.locator(sel)
        for i in range(count):
            card = cards.nth(i)
            title = _card_title(card)
            if not title:
                reason["空标题"] += 1
                samples.setdefault("空标题", (i + 1, ""))
                continue
            if title.lower() in {t.lower() for t in PLACEHOLDER_TITLES}:
                reason["占位卡"] += 1
                continue
            try:
                txt = (card.inner_text() or "").lower()
            except Exception:
                txt = ""
            hit = [p for p in DEAD_PATTERNS if p in txt or p in title.lower()]
            if hit:
                reason["下架:" + hit[0]] += 1
                samples.setdefault("下架:" + hit[0], (i + 1, txt[:130]))
                continue
            reason["可用"] += 1

        for k, v in reason.most_common():
            print("   %-34s %d" % (k, v))
            if k in samples:
                pos, txt = samples[k]
                print("        例: 第%d张 -> %r" % (pos, txt))

        listings = _dig_listings_array(page)
        batch = parse_listing_page(page, start_pos=1, need=5, listings=listings)
        print("   parse_listing_page(need=5) 实际返回 %d 条" % len(batch))
        for b in batch:
            print("      #%s promoted=%-5s cat=%-8s %s" % (b["position"], b["is_sponsored"],
                                                          b["leaf_category_ids"], b["title"][:52]))

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
