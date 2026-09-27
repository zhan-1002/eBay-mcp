# -*- coding: utf-8 -*-
"""找 dsheet 详情（Detail）的加载方式：ajax 接口 or 独立页面。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "输出", "探查", "search_rowid_uk.html"))
html = open(P, encoding="utf-8", errors="replace").read()
print("文件: %s (%d 字符)\n" % (os.path.basename(P), len(html)))

print("=" * 78)
print("① dsrid / detail / ds-preview 的事件绑定")
print("=" * 78)
for kw in ("dsrid", "ds-preview", "action-btn detail", ".detail"):
    print("\n--- %s ---" % kw)
    n = 0
    for m in re.finditer(re.escape(kw), html):
        i = m.start()
        seg = html[max(0, i - 260):i + 300]
        # 只打印像 JS 绑定的片段
        if any(k in seg for k in ("click", "on(", "ajax", "post(", "get(", "function", "url")):
            s = re.sub(r"\s+", " ", seg)
            print("   …%s…" % s[:300])
            n += 1
        if n >= 4:
            break
    if n == 0:
        print("   （未找到明显绑定）")

print()
print("=" * 78)
print("② 与 dsheet 详情相关的 ajax URL 全集")
print("=" * 78)
urls = set()
for m in re.finditer(r"""['"](/app/soldeazy/[A-Za-z0-9_/\-]{2,80})['"]""", html):
    urls.add(m.group(1))
for m in re.finditer(r"""url\s*:\s*['"]([^'"]{3,120})['"]""", html):
    urls.add(m.group(1))
for u in sorted(urls):
    if any(k in u.lower() for k in ("detail", "dsheet", "datasheet", "row", "view")):
        print("   %s" % u)

print()
print("=" * 78)
print("③ 是否有『详情』容器 / 隐藏区块（可能在 HTML 里已存在，点开才显示）")
print("=" * 78)
for m in re.finditer(r"""id=['"]([^'"]*(?:detail|view_dsheet|dsheet_view|row_detail)[^'"]*)['"]""",
                     html, re.I):
    print("   id=%s" % m.group(1))
for m in re.finditer(r"""class=['"]([^'"]*(?:detail|detail-wrap|dsheet-detail)[^'"]*)['"]""",
                     html, re.I):
    c = m.group(1)
    if len(c) < 120:
        print("   class=%s" % c)

print()
print("=" * 78)
print("④ 内联脚本里包含 dsheetrowid / detail 的函数")
print("=" * 78)
for m in re.finditer(r"function\s+(\w*(?:detail|Detail|dsheet|row)\w*)\s*\(", html):
    print("   function %s" % m.group(1))
for m in re.finditer(r"\$\('#(\w*(?:detail|dsheet)\w*)'\)\.(\w+)\(", html, re.I):
    print("   $('#%s').%s(" % (m.group(1), m.group(2)))
