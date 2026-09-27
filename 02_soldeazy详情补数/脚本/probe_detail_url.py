# -*- coding: utf-8 -*-
"""打印详情 fancybox 的完整绑定代码，拿到真实的详情 URL 与行号选择器。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "输出", "探查", "search_rowid_uk.html"))
html = open(P, encoding="utf-8", errors="replace").read()

i = html.find('$("body").on("click",".dsheet_row_action, a.ds-preview"')
print("=== 绑定代码原文（从起始处 3000 字符）===")
seg = html[i:i + 3000]
print(seg)

print("\n\n=== 所有 fancybox iframe href ===")
for m in re.finditer(r'href\s*:\s*[\'"]([^\'"]*soldeazy[^\'"]*)[\'"]', html):
    print("  %s" % m.group(1)[:200])
for m in re.finditer(r'\$\.fancybox\(\{[^}]{0,400}\}', html, re.S):
    print("\n  fancybox: %s" % re.sub(r"\s+", " ", m.group(0))[:400])

print("\n\n=== 所有 a 标签的 class 组合（找触发详情的那个）===")
from collections import Counter
cls = Counter()
for m in re.finditer(r"<a\b[^>]*class=['\"]([^'\"]+)['\"][^>]*>", html):
    cls[m.group(1)] += 1
for c, n in cls.most_common(25):
    print("   %-52s x%d" % (c[:52], n))

print("\n\n=== 绑定里涉及的所有选择器 ===")
for m in re.finditer(r'\$\("body"\)\.on\("click","([^"]+)"', html):
    print("   %s" % m.group(1))
