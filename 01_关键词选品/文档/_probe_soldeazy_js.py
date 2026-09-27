# -*- coding: utf-8 -*-
"""深挖 Soldeazy 登录页：JS bundle 里的登录字段名、是否要 captcha、登录接口形态。"""
import re

import requests

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/151.0.0.0 Safari/537.36"})
r = s.get("https://stiger.soldeazy.com/app/soldeazy/login", timeout=25, verify=False)
html = r.text

print("=== 页面里 captcha 上下文 ===")
for m in re.finditer(r".{140}captcha.{140}", html, re.I | re.S):
    print("  ...%s..." % re.sub(r"\s+", " ", m.group(0)))
    print()

print("=== 页面内嵌的 JS 变量（含 login / user / pass 的）===")
for m in re.finditer(r"(?:var|let|const)\s+(\w*(?:login|user|pass|email|account)\w*)\s*=\s*([^;\n]{0,90})",
                     html, re.I):
    print("  %s = %s" % (m.group(1), m.group(2)[:90]))

print("\n=== 内嵌 JSON / data 属性里的登录相关 ===")
for m in re.finditer(r'data-\w+="[^"]{0,120}"', html):
    t = m.group(0)
    if re.search(r"(?i)login|user|csrf|token", t):
        print("  %s" % t[:160])

print("\n=== 抓 bundle 找登录字段（vendors/signup/runtime）===")
for js in ("/app/bundle/dist/signup.js", "/app/js/general_js.js"):
    try:
        jr = s.get("https://stiger.soldeazy.com" + js, timeout=25, verify=False)
    except Exception as exc:
        print("  %s 拉取失败 %s" % (js, exc))
        continue
    js_text = jr.text
    print("\n  --- %s (HTTP %s, %d 字节) ---" % (js, jr.status_code, len(js_text)))
    for pat, label in ((r"""['"](?:email|username|user_name|account|password|passwd)['"]""", "字段名"),
                       (r"/ssl/soldeazy/login", "登录接口"),
                       (r"captcha|verify_code|checkcode", "验证码")):
        hits = sorted(set(m.group(0) for m in re.finditer(pat, js_text, re.I)))[:8]
        if hits:
            print("     %s: %s" % (label, hits))
    # 找表单提交附近的代码
    for m in re.finditer(r".{100}(?:/ssl/soldeazy/login).{200}", js_text, re.S):
        print("     提交上下文: %s" % re.sub(r"\s+", " ", m.group(0))[:300])
        break
