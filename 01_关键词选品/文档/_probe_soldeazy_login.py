# -*- coding: utf-8 -*-
"""看 Soldeazy 登录页的表单结构（只读，不提交）。"""
import re

import requests

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/151.0.0.0 Safari/537.36"})
url = "https://stiger.soldeazy.com/app/soldeazy/login"
r = s.get(url, timeout=25, verify=False)
print("HTTP %s | 长度 %d" % (r.status_code, len(r.text)))
print("Set-Cookie: %s" % list(s.cookies.keys()))

print("\n=== <form> 标签 ===")
for m in re.finditer(r"<form\b[^>]*>", r.text, re.I):
    print("  " + m.group(0)[:250])

print("\n=== input 标签（含 name/id/type/placeholder）===")
for m in re.finditer(r"<input\b[^>]*>", r.text, re.I):
    tag = m.group(0)
    fields = {}
    for k in ("name", "id", "type", "placeholder", "value", "class"):
        mm = re.search(r'%s="([^"]*)"' % k, tag)
        if mm:
            fields[k] = mm.group(1)[:60]
    print("  %s" % fields)

print("\n=== 可能的登录接口 / ajax 路径 ===")
for m in re.finditer(r"""['"]([^'"]*(?:login|Login|signin|auth)[^'"]*)['"]""", r.text):
    u = m.group(1)
    if u.startswith(("http", "/")):
        print("  %s" % u[:120])

print("\n=== 页面里的 <script src> ===")
for m in re.finditer(r'<script[^>]*src="([^"]+)"', r.text, re.I):
    print("  %s" % m.group(1)[:130])

print("\n=== 是否有验证码元素 ===")
for kw in ("captcha", "verify", "code", "验证码"):
    print("  %-10s 出现 %d 次" % (kw, len(re.findall(kw, r.text, re.I))))

print("\n=== 页面文本片段（前 400 字符的可见文字）===")
txt = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S | re.I)
txt = re.sub(r"<style.*?</style>", " ", txt, flags=re.S | re.I)
txt = re.sub(r"<[^>]+>", " ", txt)
txt = re.sub(r"\s+", " ", txt).strip()
print("  %s" % txt[:400])
