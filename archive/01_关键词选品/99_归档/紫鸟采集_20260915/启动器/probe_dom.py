# -*- coding: utf-8 -*-
"""第二步探针：打开 haihu_8075 -> 按站点点配送地 -> 搜第 1 页 -> 采样真实 DOM 结构。

目的：不再猜选择器。只抓第 1 页、只做只读采样，不写任何项目文件。
产出：
  - 屏幕采样：真实 URL / 命中条数 / 标题与价格选择器 / 广告位元素线索
  - 完整 HTML dump 到 输出\_dom\ 下，供后续定选择器
  - 截图一张

用法:
  python probe_dom.py --store haihu_8075 --site uk --keyword "wireless earbuds"
  python probe_dom.py --keep        （保留浏览器窗口，便于你亲眼看）
"""

import argparse
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "脚本"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from ziniao_runtime import (  # noqa: E402
    close_browser, exit_ziniao, get_browser_list, kill_ziniao, match_store,
    open_store, start_ziniao, wait_for_server,
)
from collect_ziniao import set_ship_to  # noqa: E402
from sites import get_site, search_url  # noqa: E402

HERE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE_DIR, "..", ".."))
DOM_DIR = os.path.join(PROJ, "输出", "_dom")

CARD_SELECTORS = [
    "li.s-item",
    "li.s-card",
    ".srp-results li",
    "ul.srp-results > li",
    "div.s-card",
    "[data-viewport]",
    ".s-item",
    ".s-card",
]


def probe_presence(page, selectors):
    rows = []
    for sel in selectors:
        try:
            n = page.locator(sel).count()
        except Exception as exc:
            rows.append((sel, -1, "count 异常: %s" % str(exc)[:60]))
            continue
        first_cls = ""
        if n > 0:
            try:
                first_cls = (page.locator(sel).first.get_attribute("class") or "")[:160]
            except Exception:
                pass
        rows.append((sel, n, first_cls))
    return rows


def sample_first_card(page, card_selector):
    """对第一个卡片做字段级采样，返回 (class, {字段: (命中数, 文本/属性))。"""
    try:
        card = page.locator(card_selector).first
        if card.count() == 0:
            return "", {}
    except Exception:
        return "", {}
    cls = ""
    try:
        cls = card.get_attribute("class") or ""
    except Exception:
        pass
    fields = {
        "title": [".s-item__title", ".s-card__title", "[role=heading]", "h3", ".su-styled-text"],
        "price": [".s-item__price", ".s-card__price", ".s-item__detail--primary"],
        "link": ["a.s-item__link", "a.su-link", "a[href*='/itm/']"],
        "ad_badge": ["[class*=etrs]", "span.s-item__etrs", "[class*=ad]", "[aria-label*=Sponsored i]"],
        "subtitle": [".s-item__subtitle", ".s-card__subtitle", ".s-item__caption"],
        "location": [".s-item__location", ".s-item__itemLocation", "[class*=location]"],
        "seller": [".s-item__seller-info", "[class*=seller]"],
    }
    out = {}
    for name, sels in fields.items():
        hit = None
        for sel in sels:
            try:
                c = card.locator(sel).count()
            except Exception:
                continue
            if c > 0:
                txt = ""
                try:
                    txt = (card.locator(sel).first.inner_text() or "").replace("\n", " ")[:90]
                except Exception:
                    pass
                if not txt:
                    try:
                        txt = (card.locator(sel).first.get_attribute("href") or "")[:90]
                    except Exception:
                        pass
                hit = (sel, c, txt)
                break
        out[name] = hit
    return cls, out


def tally_classes(html):
    """统计 HTML 里出现的 s-* 类名，用来判断是新版还是旧版卡片。"""
    names = re.findall(r'class="([^"]{0,400})"', html)
    counter = {}
    for blob in names:
        for tok in blob.split():
            if tok.startswith(("s-item", "s-card", "srp-", "su-")):
                counter[tok] = counter.get(tok, 0) + 1
    return sorted(counter.items(), key=lambda kv: -kv[1])[:40]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="haihu_8075")
    ap.add_argument("--site", default="uk")
    ap.add_argument("--keyword", default="wireless earbuds")
    ap.add_argument("--keep", action="store_true", help="保留浏览器窗口，结束时不清场")
    ap.add_argument("--no-location", action="store_true", help="跳过配送地设置")
    ap.add_argument("--detail", default="", help="只探一个详情页：给商品 URL")
    args = ap.parse_args(argv)

    site = get_site(args.site)
    os.makedirs(DOM_DIR, exist_ok=True)
    print("=" * 72)
    print("第二步探针  store=%s site=%s keyword=%s" % (args.store, args.site, args.keyword))
    print("=" * 72)

    api_port = None
    browser = None
    oauth = ""
    ok = False
    try:
        print("[1] 关旧进程 / 启紫鸟 / 等就绪")
        kill_ziniao()
        api_port = start_ziniao()
        if not wait_for_server(api_port):
            print("  服务未就绪")
            return 3

        stores = get_browser_list(api_port)
        zn = match_store(stores, args.store)
        if not zn:
            print("  店铺未命中: %s" % args.store)
            return 4
        store_info = {s.get("browserName"): s for s in stores}[zn]
        oauth = store_info.get("browserOauth", "")
        print("  命中: %s (platform=%s)" % (zn, store_info.get("platform_name")))

        print("[2] 打开店铺")
        res = open_store(api_port, oauth)
        dport = res.get("debuggingPort")
        print("  debuggingPort = %s" % dport)
        if not dport:
            return 5
        time.sleep(10)

        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % dport)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("  已接管页面, 当前 URL: %s" % page.url[:120])
        time.sleep(3)

        print("[3] 打开站点首页 %s" % site["host"])
        page.goto(site["host"], wait_until="domcontentloaded", timeout=180000)
        time.sleep(3)

        if args.detail:
            print("[3b] 详情页探针: %s" % args.detail[:120])
            page.goto(args.detail, wait_until="domcontentloaded", timeout=180000)
            time.sleep(4)
            print("  落地 URL: %s" % page.url[:160])
            print("  标题: %s" % (page.title() or "")[:120])
            containers = [
                "#viTabs_0_is", ".vim.x-about-this-item", '[data-testid="ux-layout-section-evo"]',
                ".ux-layout-section-evo", '[class*="about-this-item"]', ".ux-labels-values",
                ".ux-layout-section--features", "#viTabs_0_is .ux-labels-values", "dl", "table",
            ]
            print("\n  容器命中数:")
            for s in containers:
                try:
                    print("    %-42s %d" % (s, page.locator(s).count()))
                except Exception as exc:
                    print("    %-42s 异常 %s" % (s, str(exc)[:40]))

            print("\n  dl/dt/dd 成对（最多 3 组，每组前 12 行）:")
            js_dl = r"""
            () => {
              const out = [];
              document.querySelectorAll('dl').forEach((dl) => {
                const dts = dl.querySelectorAll('dt'), dds = dl.querySelectorAll('dd');
                if (dts.length && dts.length === dds.length) {
                  const rows = [];
                  dts.forEach((dt, i) => rows.push([
                    dt.innerText.replace(/\s+/g,' ').trim().slice(0,40),
                    dds[i].innerText.replace(/\s+/g,' ').trim().slice(0,70)]));
                  out.push(rows.slice(0, 12));
                }
              });
              return out.slice(0, 3);
            }
            """
            try:
                for tbl in page.evaluate(js_dl):
                    print("    --- 共 %d 行 ---" % len(tbl))
                    for name, value in tbl:
                        print("       %-26s = %s" % (name, value))
            except Exception as exc:
                print("    dl 探测失败: %s" % str(exc)[:80])

            print("\n  内嵌 state 键命中:")
            html = page.content()
            for key in ['"itemSpecifics"', 'localizedAspects', '"aspects"', "aboutThisItem",
                        '"specifics"', 'ITEM_SPECIFICS']:
                i = html.find(key)
                print("    %-20s 位置 %s" % (key, i))
                if i > 0:
                    print("       …%s…" % html[i:i + 260].replace("\n", " "))

            print("\n  页面 a11y 成对（排除物流类）:")
            js_aria = r"""
            () => {
              const noise = /postage|delivery|return|location|collect|seller|payment|quantity|watch/i;
              const out = [];
              document.querySelectorAll('[aria-label]').forEach((el) => {
                const t = (el.innerText || '').trim();
                if (t && /^[A-Za-z][A-Za-z \/&-]{2,24}:/.test(t) && t.length < 120) {
                  const i2 = t.indexOf(':'); const name = t.slice(0, i2).trim();
                  if (!noise.test(name)) out.push([name, t.slice(i2 + 1).trim().slice(0, 60)]);
                }
              });
              return out.slice(0, 30);
            }
            """
            try:
                for name, value in page.evaluate(js_aria):
                    print("    %-26s = %s" % (name[:26], value))
            except Exception as exc:
                print("    aria 探测失败: %s" % str(exc)[:80])

            stamp0 = time.strftime("%Y%m%d_%H%M%S")
            dp = os.path.join(DOM_DIR, "detail_%s.html" % stamp0)
            with open(dp, "w", encoding="utf-8") as f:
                f.write(html)
            print("\n  详情页 HTML dump: %s" % dp)
            ok = True
            if args.keep:
                print("\n--keep: 窗口保留，按回车继续清理...")
                try:
                    input()
                except Exception:
                    time.sleep(30)
            return 0

        if args.no_location:
            print("[4] 跳过配送地设置")
        else:
            print("[4] 设置配送地（现有实现，注意它可能假报成功）")
            try:
                rv = set_ship_to(page, args.site)
                print("  set_ship_to 返回: %s" % rv)
            except Exception as exc:
                print("  set_ship_to 异常: %s" % exc)
            print("  设置后 URL: %s" % page.url[:160])

        url = search_url(args.site, args.keyword, page=1, per_page=240)
        print("[5] 搜索第 1 页: %s" % url)
        page.goto(url, wait_until="domcontentloaded", timeout=180000)
        time.sleep(4)
        print("  落地 URL: %s" % page.url[:200])
        print("  标题: %s" % (page.title() or "")[:120])

        print("\n[6] 卡片选择器命中情况")
        rows = probe_presence(page, CARD_SELECTORS)
        best = None
        for sel, n, cls in rows:
            print("  %-26s 命中=%-5s class=%s" % (sel, n, cls[:70]))
            if n > 0 and best is None:
                best = sel
        if not best:
            print("  !! 所有候选卡片选择器都是 0 条 —— 就是报告里的 P0-3")
        print("  主用选择器: %s" % best)

        if best:
            print("\n[7] 第一个卡片的字段采样")
            cls, fields = sample_first_card(page, best)
            print("  卡片 class: %s" % cls)
            for name, hit in fields.items():
                if hit is None:
                    print("    %-9s : 未命中" % name)
                else:
                    print("    %-9s : sel=%-24s 数=%-3s 文本=%s" % (name, hit[0], hit[1], hit[2]))

            print("\n[8] 前 3 条抽样（标题 / 价格原文）")
            for i in range(min(3, page.locator(best).count())):
                card = page.locator(best).nth(i)
                t = p = ""
                for sel in (".s-item__title", ".s-card__title", "[role=heading]", "h3"):
                    try:
                        if card.locator(sel).count() > 0:
                            t = (card.locator(sel).first.inner_text() or "").replace("\n", " ")[:80]
                            break
                    except Exception:
                        pass
                for sel in (".s-item__price", ".s-card__price", ".s-item__detail--primary"):
                    try:
                        if card.locator(sel).count() > 0:
                            p = (card.locator(sel).first.inner_text() or "").replace("\n", " ")[:60]
                            break
                    except Exception:
                        pass
                print("    %d) 价=%-22s 标题=%s" % (i + 1, p, t))

        print("\n[9] 结果计数线索")
        for sel in [".srp-controls__count-heading", "h1.srp-controls__count-heading",
                    ".srp-save-null-search__heading", "[class*=count-heading]"]:
            try:
                if page.locator(sel).count() > 0:
                    print("  %-42s -> %s" % (sel, (page.locator(sel).first.inner_text() or "").replace("\n", " ")[:90]))
            except Exception:
                pass

        print("\n[10] 页面 HTML 类名统计（判断新版/旧版结构）")
        html = page.content()
        for tok, cnt in tally_classes(html):
            print("  %-34s %d" % (tok, cnt))

        stamp = time.strftime("%Y%m%d_%H%M%S")
        tag = "%s_%s_%s" % (re.sub(r"\W+", "_", args.keyword)[:24], args.site, stamp)
        html_path = os.path.join(DOM_DIR, "search1_%s.html" % tag)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print("\n  HTML dump: %s (%d 字符)" % (html_path, len(html)))
        try:
            shot = os.path.join(DOM_DIR, "search1_%s.png" % tag)
            page.screenshot(path=shot, full_page=False)
            print("  截图: %s" % shot)
        except Exception as exc:
            print("  截图失败: %s" % exc)

        ok = True
        print("\n" + "=" * 72)
        print("结论: 第 1 页真实结构已采样完成（见上）")
        print("=" * 72)
        if args.keep:
            print("\n--keep: 窗口保留，按回车继续清理...")
            try:
                input()
            except Exception:
                time.sleep(60)
        return 0

    except KeyboardInterrupt:
        print("\n用户中断")
        return 130
    except Exception as exc:
        print("\n异常: %s" % exc)
        print(traceback.format_exc())
        return 1
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        if api_port:
            if ok and not args.keep:
                try:
                    exit_ziniao(api_port)
                except Exception:
                    pass
                print("[清理] 已清场")
            elif args.keep:
                print("[清理] --keep 生效，保留紫鸟窗口")
            else:
                print("[清理] 未成功，保留进程便于看现场")


if __name__ == "__main__":
    sys.exit(main())
