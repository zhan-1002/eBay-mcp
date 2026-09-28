# -*- coding: utf-8 -*-
"""找 table_action=detail 的触发方式（决定怎么拿带值的详情页）。"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
P = sorted(glob.glob(os.path.join(OUT, "click_detail_*.html")))[-1]
html = open(P, encoding="utf-8", errors="replace").read()
print("文件: %s\n" % os.path.basename(P))

print("=" * 78)
print("① table_action 的所有取值")
print("=" * 78)
for m in sorted(set(re.findall(r"table_action['\"]?\s*[,:=]\s*['\"]?([a-zA-Z_]+)", html))):
    print("   %s" % m)
print("\n  在 JS 里出现的 table_action 赋值/比较:")
for m in re.finditer(r".{80}table_action.{120}", html):
    seg = re.sub(r"\s+", " ", m.group(0))
    if "$" in seg or "val(" in seg or "==" in seg:
        print("   …%s…" % seg[:200])

print()
print("=" * 78)
print("② 'detail' 在 JS 里的处理（table_action / action-btn）")
print("=" * 78)
n = 0
for m in re.finditer(r"detail", html):
    i = m.start()
    seg = re.sub(r"\s+", " ", html[max(0, i - 260):i + 300])
    if re.search(r"(table_action|\.val\(|hasClass|click|attr\()", seg):
        print("  …%s…" % seg[:280])
        print()
        n += 1
    if n >= 6:
        break

print("=" * 78)
print("③ 结果行里 功能选项 三链接的完整 onclick/绑定（edit 怎么走）")
print("=" * 78)
m = re.search(r"<a[^>]*class=['\"]action-btn edit['\"][^>]*>", html)
print("  edit 标签: %s" % (m.group(0) if m else "未找到"))
# 找 edit 的绑
for mm in re.finditer(r"""(?:hasClass\(['"]edit['"]\)|\.action-btn\.edit|['"]\.edit['"])""", html):
    i = mm.start()
    print("  …%s…" % re.sub(r"\s+", " ", html[max(0, i - 300):i + 400])[:420])

print()
print("=" * 78)
print("④ dsheet_item_specific 的渲染 JS（值从哪来）")
print("=" * 78)
n = 0
for m in re.finditer(r"dsheet_item_specific", html):
    i = m.start()
    seg = re.sub(r"\s+", " ", html[max(0, i - 300):i + 300])
    if "$" in seg or "val(" in seg or "function" in seg:
        print("  …%s…" % seg[:320])
        print()
        n += 1
    if n >= 5:
        break

print("=" * 78)
print("⑤ 页面里是否有已填好的 item specifics 数据（JSON 形式）")
print("=" * 78)
for pat in (r"item_specific[a-z_]*\s*[:=]\s*[\[{]", r'"itemSpecific', r"specifics\s*[:=]"):
    for m in re.finditer(pat, html, re.I):
        i = m.start()
        print("  …%s…" % re.sub(r"\s+", " ", html[max(0, i - 120):i + 400])[:400])
        break
