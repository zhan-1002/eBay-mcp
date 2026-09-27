# -*- coding: utf-8 -*-
"""诊断：详情页 specifics 为什么只落库 1 条。

只抓前 3 条详情，全程打印，并把每条抓到的原始结果落盘比对。
"""
import json
import os
import sys
import time

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

from ziniao_runtime import (  # noqa: E402
    exit_ziniao, get_browser_list, kill_ziniao, match_store, open_store,
    start_ziniao, wait_for_server,
)
from collect_ziniao import EXTRACT_JS, fetch_item_detail  # noqa: E402
from sites import get_site, search_url  # noqa: E402

STORE = "haihu_8075"
SITE = "uk"
KW = "wireless earbuds"
DUMP = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\_dom"
os.makedirs(DUMP, exist_ok=True)


def main():
    api_port = None
    try:
        kill_ziniao()
        api_port = start_ziniao()
        assert wait_for_server(api_port), "服务未就绪"
        stores = get_browser_list(api_port)
        zn = match_store(stores, STORE)
        info = {s.get("browserName"): s for s in stores}[zn]
        print("命中店铺: %s" % zn)
        res = open_store(api_port, info.get("browserOauth", ""))
        dport = res.get("debuggingPort")
        print("debuggingPort=%s" % dport)
        time.sleep(10)

        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % dport)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        site = get_site(SITE)
        page.goto(search_url(SITE, KW, page=1, per_page=240),
                  wait_until="domcontentloaded", timeout=180000)
        time.sleep(3)

        # 用列表页直接取前 3 条的 url / id
        cards = page.locator("li.s-card")
        n = cards.count()
        print("卡片数 %d" % n)
        targets = []
        for i in range(n):
            card = cards.nth(i)
            t = ""
            try:
                t = (card.locator(".s-card__title").first.inner_text() or "").strip()
            except Exception:
                pass
            if not t or t.lower() in ("shop on ebay",):
                continue
            href = ""
            try:
                href = card.locator("a[href*='/itm/']").first.get_attribute("href") or ""
            except Exception:
                pass
            targets.append({"position": len(targets) + 1, "title": t, "item_url": href,
                            "leaf_category_ids": []})
            if len(targets) >= 3:
                break

        print("\n将逐条抓详情，逐条打印内部状态：\n")
        for it in targets:
            print("=" * 74)
            print("目标 #%s %s" % (it["position"], it["title"][:60]))
            print("  url = %s" % it["item_url"][:110])
            try:
                page.goto(it["item_url"], wait_until="domcontentloaded", timeout=120000)
            except Exception as exc:
                print("  !! goto 异常: %s" % str(exc)[:150])
                continue
            time.sleep(3.5)
            print("  落地 url = %s" % page.url[:110])
            print("  页面标题 = %s" % (page.title() or "")[:80])
            try:
                data = page.evaluate(EXTRACT_JS)
            except Exception as exc:
                print("  !! evaluate 异常: %s" % str(exc)[:150])
                continue
            print("  evaluate 返回: specifics=%d crumbs=%d primaryCatId=%r primaryCatName=%r"
                  % (len(data.get("specifics") or []), len(data.get("crumbs") or []),
                     data.get("primaryCategoryId"), data.get("primaryCategoryName")))
            for s in (data.get("specifics") or [])[:8]:
                print("      %-24s = %s" % (s["name"][:24], s["value"][:52]))
            for c in (data.get("crumbs") or [])[:6]:
                print("      crumb: id=%r name=%r" % (c.get("id"), c.get("name")))

            # 现场量容器
            for sel in ["#viTabs_0_is", "#viTabs_0_is dl", "dl", ".ux-labels-values",
                        "#viTabs_0_is .ux-labels-values"]:
                try:
                    print("      容器 %-30s = %d" % (sel, page.locator(sel).count()))
                except Exception as exc:
                    print("      容器 %-30s 异常 %s" % (sel, str(exc)[:40]))

            # 走正式函数，看它最后写进 item 的是什么
            before = dict(it)
            fetch_item_detail(page, it, site["host"])
            print("  fetch_item_detail 后: specifics=%d leaf=%s name=%r cats=%d"
                  % (len(it.get("item_specifics") or []), it.get("leaf_category_ids"),
                     it.get("leaf_category_name"), len(it.get("categories") or [])))
            print("  item 被修改的键: %s" % [k for k in it if before.get(k) != it.get(k)])

            hp = os.path.join(DUMP, "diag_detail_%d.html" % it["position"])
            with open(hp, "w", encoding="utf-8") as f:
                f.write(page.content())
            print("  HTML: %s" % hp)
            time.sleep(1)

        print("\n最终 targets 状态：")
        print(json.dumps([{k: v for k, v in t.items() if k != "item_url"} for t in targets],
                         ensure_ascii=False, indent=2)[:1500])
    finally:
        if api_port:
            try:
                exit_ziniao(api_port)
            except Exception:
                pass
            kill_ziniao()


if __name__ == "__main__":
    main()
