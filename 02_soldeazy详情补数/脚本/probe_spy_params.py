# -*- coding: utf-8 -*-
"""解析 create_datasheet_from_listing_spy 的完整参数与返回处理（判断是否只读可行）。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
html = open(os.path.join(OUT, "dsheet_list.html"), encoding="utf-8", errors="replace").read()

i = html.find('"mode" : "create_datasheet_from_listing_spy"')
print("=== create_datasheet_from_listing_spy 调用原文（前后 2600 字符）===")
print(re.sub(r"\n\s*\n", "\n", html[max(0, i - 1200):i + 2600]))

print("\n\n=== datasheet_ajax 的其它 mode 取值 ===")
modes = sorted(set(re.findall(r'"mode"\s*:\s*"([a-zA-Z_]+)"', html)))
for m in modes:
    print("   %s" % m)

print("\n\n=== 是否有 preview / 不落库 的 mode ===")
for kw in ("preview", "check_", "verify", "get_listing", "listing_info", "fetch"):
    for m in re.finditer(r'"mode"\s*:\s*"([a-zA-Z_]*%s[a-zA-Z_]*)"' % kw, html, re.I):
        print("   %s" % m.group(1))
