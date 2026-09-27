# -*- coding: utf-8 -*-
"""探针：搜索页每张卡的标题原始文本 / 归一化后文本 / 命中哪条跳过规则。

只看不改。用法: python _diag_skip.py
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
    DEAD_PATTERNS, PLACEHOLDER_TITLES, _card_text, _card_title, clean_listing_title,
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

    site = get_site(SITE)
    page.goto(search_url(SITE, KW, page=1, per_page=240),
              wait_until="domcontentloaded", timeout=180000)
    time.sleep(3)
    cards = page.locator("li.s-card")
    n = cards.count()
    print("li.s-card = %d\n" % n)

    print("=== 前 12 张卡的判定过程 ===")
    for i in range(min(12, n)):
        card = cards.nth(i)
        raw = ""
        try:
            raw = (card.locator(".s-card__title").first.inner_text() or "")
        except Exception as exc:
            raw = "<取不到: %s>" % str(exc)[:40]
        cleaned = clean_listing_title(raw)
        cont = ""
        try:
            cont = (card.inner_text() or "").lower()
        except Exception:
            pass
        hit_ph = (not cleaned) or cleaned.lower() in {t.lower() for t in PLACEHOLDER_TITLES}
        hit_dead = any(p in cont for p in DEAD_PATTERNS) or any(p in cleaned.lower() for p in DEAD_PATTERNS)
        which = [p for p in DEAD_PATTERNS if p in cont or p in cleaned.lower()]
        print("\n#%d" % (i + 1))
        print("   原始(.s-card__title) = %r" % raw[:150])
        print("   归一化后            = %r" % cleaned[:150])
        print("   占位卡命中=%s  下架命中=%s %s" % (hit_ph, hit_dead, which))
        print("   卡内文本(前120)      = %r" % cont[:120])
        if i == 4:
            # 再对比其它选择器，看是不是选到了错的节点
            for sel in ["[role=heading]", "h3", ".s-card__title"]:
                try:
                    v = (card.locator(sel).first.inner_text() or "") if card.locator(sel).count() else "<无>"
                except Exception as exc:
                    v = "<异常 %s>" % str(exc)[:30]
                print("   选择器 %-16s = %r" % (sel, v[:100]))

    print("\n=== 全页统计 ===")
    ph = dead = ok = 0
    for i in range(n):
        card = cards.nth(i)
        cleaned = _card_title(card)
        if not cleaned or cleaned.lower() in {t.lower() for t in PLACEHOLDER_TITLES}:
            ph += 1
            continue
        try:
            cont = (card.inner_text() or "").lower()
        except Exception:
            cont = ""
        if any(p in cont for p in DEAD_PATTERNS) or any(p in cleaned.lower() for p in DEAD_PATTERNS):
            dead += 1
            continue
        ok += 1
    print("占位=%d 下架=%d 可用=%d 总计=%d" % (ph, dead, ok, n))

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
