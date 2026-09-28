# -*- coding: utf-8 -*-
"""查 listing_spy 创建流程是否可自定义数据表名称 / 标签（只读，不创建）。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
html = open(os.path.join(OUT, "dsheet_list_live.html"), encoding="utf-8", errors="replace").read()
print("页面: dsheet_list_live.html (%d 字符)\n" % len(html))

print("=" * 84)
print("① 创建流程的 ajax data 里都有哪些参数（listing_spy 相关）")
print("=" * 84)
i = html.find('"mode" : "create_datasheet_from_listing_spy"')
if i > 0:
    seg = html[i - 900:i + 1400]
    print(seg)
else:
    print("  没找到该调用")

print("\n" + "=" * 84)
print("② 弹层里与『文件名 / 标签』相关的输入控件")
print("=" * 84)
m = re.search(r'id=["\']divShopInitPrompt["\'].*', html, re.S)
seg = m.group(0)[:300000] if m else html
for mm in re.finditer(r"<(?:input|select|textarea)\b[^>]*(?:filename|custom_label|label|name)[^>]*>",
                      seg, re.I):
    t = mm.group(0)
    if re.search(r"(?i)(filename|custom_label|txttag|dsheet_custom)", t):
        print("  %s" % t[:240])

print("\n  弹层里所有 name（含 label 字样的）:")
names = sorted(set(re.findall(r"<(?:input|select|textarea)[^>]*name=['\"]([^'\"]+)['\"]", seg, re.I)))
for n in names:
    if re.search(r"(?i)(filename|label|tag|custom)", n):
        print("     %s" % n)

print("\n" + "=" * 84)
print("③ 表单里的 txtfilename（上载文件名称）出现在哪 —— 是筛选还是可填")
print("=" * 84)
for mm in re.finditer(r"txtfilename", html):
    i2 = mm.start()
    print("  …%s…" % re.sub(r"\s+", " ", html[max(0, i2 - 200):i2 + 260])[:420])
    print()

print("=" * 84)
print("④ 是否有『另存/重命名/标签』功能（改名入口）")
print("=" * 84)
for kw in ("重命名", "改名", "rename", "标签", "tag", "custom_label", "批次"):
    hits = [x.start() for x in re.finditer(re.escape(kw), html, re.I)]
    print("  %-14s %d 次" % (kw, len(hits)))
    if hits and kw in ("rename", "重命名", "custom_label"):
        i3 = hits[0]
        print("     例: …%s…" % re.sub(r"\s+", " ", html[max(0, i3 - 160):i3 + 220])[:300])
