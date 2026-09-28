# -*- coding: utf-8 -*-
"""Soldeazy 登录 + 保存会话。

账号密码放本地 config.json（本目录或 02 模块根），不进代码、不进版本库：
    {"soldeazy": {"username": "...", "password": "..."}}
也支持环境变量 SOLDEAZY_USERNAME / SOLDEAZY_PASSWORD。

用法:
    python soldeazy_login.py            # 读 config 自动登录（默认）
    python soldeazy_login.py --manual   # 开有头浏览器，人工登录（无 config 时用）
    python soldeazy_login.py --check    # 只检查现有会话是否有效
"""

import argparse
import json
import os
import re
import sys
import time

BASE = "https://stiger.soldeazy.com"
LOGIN_URL = BASE + "/app/soldeazy/login"
TARGET_URL = BASE + "/app/soldeazy/datasheet/dsheet_list?default_search_profile"

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
SESSION_DIR = os.path.join(PROJ, "输出", "_session")
SESSION_FILE = os.path.join(SESSION_DIR, "soldeazy_session.json")
CONFIG_CANDIDATES = [
    os.path.join(HERE, "config.json"),
    os.path.normpath(os.path.join(HERE, "..", "config.json")),
    os.path.join(PROJ, "config.local.json"),
]


def load_creds():
    """读取账号密码：config.json 优先，其次环境变量。"""
    for path in CONFIG_CANDIDATES:
        if not os.path.isfile(path):
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as exc:
            print("  [警告] %s 解析失败: %s" % (path, exc))
            continue
        z = data.get("soldeazy") or {}
        u = z.get("username") or z.get("email") or ""
        p = z.get("password") or ""
        if u and p:
            print("  凭据来源: %s（username=%s，password 长度 %d）"
                  % (path, u, len(p)))
            return u, p
    u = os.environ.get("SOLDEAZY_USERNAME") or ""
    p = os.environ.get("SOLDEAZY_PASSWORD") or ""
    if u and p:
        print("  凭据来源: 环境变量（username=%s，password 长度 %d）" % (u, len(p)))
        return u, p
    return "", ""


def looks_logged_in(page):
    """登录成功的判定：URL 不再指向 login，且页面上没有密码输入框。"""
    url = (page.url or "").lower()
    if "/login" in url:
        return False
    try:
        if page.locator("input[type=password]").count() > 0:
            return False
    except Exception:
        pass
    return True


def save_session(context, page):
    os.makedirs(SESSION_DIR, exist_ok=True)
    cookies = context.cookies()
    state = {
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": page.url,
        "cookies": cookies,
        "user_agent": page.evaluate("navigator.userAgent"),
    }
    with open(SESSION_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("  已保存会话: %s" % SESSION_FILE)
    print("  cookie 名: %s" % [c.get("name") for c in cookies])
    return state


def auto_login(username, password, headless=True, timeout_sec=180):
    """脚本自动登录：填表 → 提交 → 等跳转 → 保存会话。

    登录表单（真机 dump）: form[action=/app/soldeazy/login/signin] method=POST
      input[name=login_user] / input[name=login_pass]
      input[name=login_browser_timezone] (hidden)
    渲染后的页面上没有 captcha 控件（captcha 只存在于未使用的 CSS 里）。
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        print("[1] 打开登录页: %s" % LOGIN_URL)
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        print("[2] 填表（只填 login_user / login_pass）")
        page.fill("input[name=login_user]", username)
        page.fill("input[name=login_pass]", password)
        try:
            page.fill("input[name=login_browser_timezone]",
                      page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone") or "Asia/Shanghai")
        except Exception:
            pass

        print("[3] 提交")
        try:
            with page.expect_navigation(timeout=45000):
                page.click("button.el-button--primary")
        except Exception as exc:
            print("  提交通知超时/异常: %s" % str(exc)[:110])
        time.sleep(4)

        print("[4] 等待登录跳转")
        deadline = time.time() + timeout_sec
        ok = False
        while time.time() < deadline:
            try:
                if page.is_closed():
                    print("  浏览器被关闭")
                    return None
            except Exception:
                pass
            if looks_logged_in(page):
                ok = True
                break
            # 页面上是否有报错弹窗 / 提示文字
            try:
                body = (page.inner_text("body") or "")
            except Exception:
                body = ""
            if re.search(r"(?i)(验证码|captcha|错误|失败|invalid|incorrect|wrong)", body):
                print("  页面提示: %s" % re.sub(r"\s+", " ", body)[:220])
                if re.search(r"(?i)(验证码|captcha)", body):
                    print("  !! 服务端要求验证码 —— 需要改走人工登录（--manual）")
                    return None
            time.sleep(2)

        if not ok:
            try:
                print("  当前 URL: %s" % page.url[:130])
                print("  页面文本: %s" % re.sub(r"\s+", " ", page.inner_text("body") or "")[:250])
            except Exception:
                pass
            print("\n登录未成功（超时）")
            try:
                browser.close()
            except Exception:
                pass
            return None

        print("  登录成功，当前 URL: %s" % page.url[:120])
        print("[5] 打开目标页确认访问权")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            print("  目标页 URL: %s" % page.url[:130])
            print("  目标页 title: %s" % (page.title() or "")[:80])
        except Exception as exc:
            print("  打开目标页失败(不致命): %s" % str(exc)[:110])

        state = save_session(ctx, page)
        try:
            browser.close()
        except Exception:
            pass
        return state


def manual_login(timeout_sec=300):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)
        print("\n请在窗口里手动登录，脚本每 2 秒检测一次（最多 %d 秒）" % timeout_sec)
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                if page.is_closed():
                    print("窗口被关闭")
                    return None
                if looks_logged_in(page):
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            print("超时未检测到登录成功")
            try:
                browser.close()
            except Exception:
                pass
            return None
        time.sleep(2)
        print("  检测到登录成功: %s" % page.url[:120])
        state = save_session(ctx, page)
        try:
            browser.close()
        except Exception:
            pass
        return state


def check_session():
    if not os.path.isfile(SESSION_FILE):
        print("没有会话文件: %s" % SESSION_FILE)
        return False
    import requests

    state = json.load(open(SESSION_FILE, encoding="utf-8"))
    s = requests.Session()
    for c in state.get("cookies") or []:
        try:
            s.cookies.set(c.get("name"), c.get("value"),
                          domain=c.get("domain"), path=c.get("path") or "/")
        except Exception:
            pass
    if state.get("user_agent"):
        s.headers.update({"User-Agent": state["user_agent"]})
    print("会话保存于: %s" % state.get("saved_at"))
    try:
        r = s.get(TARGET_URL, timeout=25, verify=False, allow_redirects=True)
    except Exception as exc:
        print("请求失败: %s" % str(exc)[:120])
        return False
    print("请求 dsheet_list -> HTTP %s | 最终 URL: %s" % (r.status_code, r.url[:120]))
    body_len = len(r.text)
    kicked = "/login" in (r.url or "")
    print("是否被踢回登录页: %s | 页面长度 %d" % (kicked, body_len))
    return not kicked


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查现有会话是否有效")
    ap.add_argument("--manual", action="store_true", help="开有头浏览器人工登录")
    ap.add_argument("--headful", action="store_true", help="自动登录也显示窗口（便于观察）")
    args = ap.parse_args(argv)

    if args.check:
        ok = check_session()
        print("\n结论: 会话%s" % ("有效" if ok else "无效或已过期，请重跑登录"))
        return 0 if ok else 1

    if args.manual:
        state = manual_login()
        ok = bool(state) and check_session()
        print("\n结论: %s" % ("人工登录成功且会话可用" if ok else "未完成"))
        return 0 if ok else 1

    print("[0] 读取凭据")
    u, p = load_creds()
    if not u or not p:
        print("  没有找到凭据。请在本目录建 config.json：")
        print('    {"soldeazy": {"username": "你的用户名", "password": "你的密码"}}')
        print("  或设环境变量 SOLDEAZY_USERNAME / SOLDEAZY_PASSWORD；")
        print("  或改用 --manual 人工登录。")
        return 2

    state = auto_login(u, p, headless=not args.headful)
    if not state:
        print("\n自动登录未成功。若服务端要验证码，请用 --manual。")
        return 1
    ok = check_session()
    print("\n结论: %s" % ("自动登录成功且会话可用" if ok else "会话已保存但校验失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
