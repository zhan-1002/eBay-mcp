# -*- coding: utf-8 -*-
"""看 Soldeazy 登录页渲染后的真实表单结构（表单字段 / captcha / 提交接口）。

用 playwright 打开登录页并等 JS 渲染完，只 dump 结构，**不填任何内容、不提交**。
"""
import json
import os
import re
import sys
import time

URL = "https://stiger.soldeazy.com/app/soldeazy/login"
OUT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "..", "输出", "探查"))
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-CN")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)          # 等 JS 渲染出表单

        print("最终 URL: %s" % page.url[:130])
        print("title: %s" % (page.title() or "")[:80])

        info = page.evaluate(r"""
        () => {
          const out = {forms: [], inputs: [], imgs: [], buttons: [], text: ''};
          document.querySelectorAll('form').forEach(f => {
            out.forms.push({action: f.getAttribute('action') || '', method: f.getAttribute('method') || '',
                            id: f.id || '', cls: (f.className||'').slice(0,60)});
          });
          document.querySelectorAll('input,select,textarea').forEach(el => {
            out.inputs.push({tag: el.tagName.toLowerCase(), type: el.type || '',
                             name: el.name || '', id: el.id || '',
                             placeholder: el.placeholder || '',
                             cls: (el.className||'').slice(0,50),
                             visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)});
          });
          document.querySelectorAll('img').forEach(el => {
            out.imgs.push({src: (el.getAttribute('src')||'').slice(0,110), id: el.id||'',
                           cls: (el.className||'').slice(0,50),
                           alt: (el.getAttribute('alt')||'').slice(0,40)});
          });
          document.querySelectorAll('button,a.btn,input[type=submit],a[onclick]').forEach(el => {
            const t = (el.innerText||'').replace(/\s+/g,' ').trim().slice(0,40);
            if (t) out.buttons.push({tag: el.tagName.toLowerCase(), text: t,
                                     id: el.id||'', cls: (el.className||'').slice(0,50)});
          });
          out.text = (document.body.innerText||'').replace(/\s+/g,' ').trim().slice(0, 400);
          return out;
        }
        """)

        print("\n=== form ===")
        for f in info["forms"]:
            print("  %s" % f)
        print("\n=== 输入控件 ===")
        for i in info["inputs"]:
            print("  %s" % i)
        print("\n=== 按钮 / 链接 ===")
        for b in info["buttons"][:15]:
            print("  %s" % b)
        print("\n=== 图片（captcha 候选）===")
        for im in info["imgs"][:15]:
            print("  %s" % im)
        print("\n=== 可见文本 ===")
        print("  %s" % info["text"])

        html = page.content()
        p = os.path.join(OUT_DIR, "login_rendered.html")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        print("\n渲染后 HTML 已存: %s (%d 字符)" % (p, len(html)))

        print("\n=== HTML 里 captcha 相关片段 ===")
        for m in re.finditer(r".{100}captcha.{140}", html, re.I | re.S):
            print("  ...%s..." % re.sub(r"\s+", " ", m.group(0))[:260])
        print("\n=== HTML 里 login 相关 url / ajax ===")
        for m in sorted(set(re.findall(r"""['"](/[a-zA-Z0-9_/\-]*(?:login|Login)[a-zA-Z0-9_/\-]*)['"]""", html))):
            print("  %s" % m)
        browser.close()


if __name__ == "__main__":
    main()
