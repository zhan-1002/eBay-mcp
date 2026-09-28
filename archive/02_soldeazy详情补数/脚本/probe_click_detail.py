# -*- coding: utf-8 -*-
"""用无头浏览器 + 已保存会话，点一次 a.detail，抓出详情的真实 URL 与字段。

只点一次、只读，不提交任何修改类操作。
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
BASE = "https://stiger.soldeazy.com"
LIST = BASE + "/app/soldeazy/datasheet"
ROW = "4153428"


def main():
    from playwright.sync_api import sync_playwright

    if not os.path.isfile(SESSION_FILE):
        print("没有会话文件，先跑 soldeazy_login.py")
        return 2
    state = json.load(open(SESSION_FILE, encoding="utf-8"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN", user_agent=state.get("user_agent"))
        # 注入已保存 cookie
        for ck in state.get("cookies") or []:
            c = {"name": ck.get("name"), "value": ck.get("value"),
                 "domain": ck.get("domain"), "path": ck.get("path") or "/"}
            if ck.get("expires"):
                c["expires"] = ck["expires"]
            try:
                ctx.add_cookies([c])
            except Exception as exc:
                print("  cookie 注入失败 %s: %s" % (c.get("name"), str(exc)[:60]))

        page = ctx.new_page()
        captured = []
        page.on("request", lambda r: captured.append((r.method, r.url, r.post_data)))
        page.on("framenavigated", lambda f: captured.append(("NAV", f.url, None)))

        print("[1] 打开列表页并搜索 row=%s" % ROW)
        page.goto(LIST, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        # 填 row id 并搜索
        try:
            page.fill("input[name=txtdsheetrowid]", ROW)
        except Exception as exc:
            print("  填 row id 失败: %s" % str(exc)[:80])
        try:
            page.click("#btn_search")
        except Exception:
            try:
                page.click("input[name=btn_search]")
            except Exception as exc:
                print("  点搜索失败: %s" % str(exc)[:80])
        time.sleep(4)
        print("  搜索后 URL: %s" % page.url[:120])
        print("  tbl_dSheet 行数: %s" % page.evaluate(
            "() => document.querySelectorAll('#tbl_dSheet tbody tr').length"))
        print("  a.dsrid.detail 数量: %s" % page.evaluate(
            "() => document.querySelectorAll('a.dsrid.detail').length"))

        print("\n[2] 点 a.dsrid.detail（只读动作）")
        before = len(captured)
        try:
            with page.expect_navigation(timeout=15000):
                page.click("a.dsrid.detail")
            print("  → 触发了页面导航")
        except Exception:
            print("  → 没有整页导航，可能是弹层/ajax")
        time.sleep(4)
        print("  点击后 URL: %s" % page.url[:140])

        # 弹出的 iframe / 新窗口
        print("  当前 frame 数: %d" % len(page.frames))
        for i, f in enumerate(page.frames):
            print("    frame[%d] url=%s" % (i, f.url[:120]))
        print("  上下文页面数: %d" % len(ctx.pages))
        for i, p in enumerate(ctx.pages):
            print("    page[%d] url=%s" % (i, p.url[:120]))

        # 点击后新产生的请求
        print("\n[3] 点击后新增请求（最多 25 条）")
        for meth, url, post in captured[before:before + 25]:
            print("   %-6s %s" % (meth, url[:150]))
            if post:
                print("          body: %s" % str(post)[:200])

        print("\n[4] 目标页可见文本（前 600 字）")
        try:
            txt = re.sub(r"\s+", " ", page.inner_text("body"))
            print("   %s" % txt[:600])
        except Exception as exc:
            print("   读取失败: %s" % str(exc)[:80])

        for key in ("Brand", "品牌", "MPN", "EAN", "Colour", "Color", "Model", "型号",
                    "Connectivity", "描述", "Description", "类别", "Category"):
            try:
                n = page.locator("text=%s" % key).count()
            except Exception:
                n = -1
            if n > 0:
                print("   页面含 %-14s %d 处" % (key, n))

        stamp = time.strftime("%Y%m%d_%H%M%S")
        hp = os.path.join(OUT, "click_detail_%s.html" % stamp)
        with open(hp, "w", encoding="utf-8", newline="\n") as f:
            f.write(page.content())
        print("\n  HTML 已存: %s" % os.path.basename(hp))

        print("\n[5] 全部请求汇总（去重，前 30）")
        seen = set()
        for meth, url, post in captured:
            k = (meth, url.split("?")[0])
            if k in seen:
                continue
            seen.add(k)
            print("   %-6s %s" % (meth, url[:140]))
            if len(seen) >= 30:
                break

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
