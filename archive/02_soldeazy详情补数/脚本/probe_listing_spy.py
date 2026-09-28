# -*- coding: utf-8 -*-
"""挖『新增数据表』的入口与『从刊登器下载数据』功能（listing_spy / createBySku）。"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
P = os.path.join(OUT, "dsheet_list.html")
html = open(P, encoding="utf-8", errors="replace").read()
print("文件: %s (%d 字符)\n" % (os.path.basename(P), len(html)))


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


print("=" * 78)
print("① 『新增数据表』入口标签")
print("=" * 78)
for m in re.finditer(r"新增数据表", html):
    i = m.start()
    print("  …%s…" % html[max(0, i - 400):i + 200].replace("\n", " ")[:560])
    print()

print("=" * 78)
print("② createBySku 相关（含其表单/弹层）")
print("=" * 78)
for m in re.finditer(r"createBySku", html):
    i = m.start()
    print("  …%s…" % re.sub(r"\s+", " ", html[max(0, i - 300):i + 400])[:600])
    print()

print("=" * 78)
print("③ listing_spy 的 UI 与提交逻辑（去重前 12 处）")
print("=" * 78)
seen = set()
n = 0
for m in re.finditer(r"listing_spy", html, re.I):
    i = m.start()
    seg = re.sub(r"\s+", " ", html[max(0, i - 260):i + 320])
    if seg in seen:
        continue
    seen.add(seg)
    print("  …%s…" % seg[:480])
    print()
    n += 1
    if n >= 12:
        break

print("=" * 78)
print("④ 与『下载/抓取 eB 数据』相关的按钮文案")
print("=" * 78)
for kw in ("下载数据", "下载", "抓取", "获取数据", "汇入", "导入", "从 eBay", "从eBay",
           "同步", "载入", "spy"):
    cnt = len(re.findall(re.escape(kw), html, re.I))
    if cnt:
        print("  %-12s %d 次" % (kw, cnt))

print()
print("=" * 78)
print("⑤ listing_spy 的表单/接口 URL")
print("=" * 78)
for m in sorted(set(re.findall(r"""['"](/[A-Za-z0-9_/\-]*(?:listing_spy|spy|datasheet_ajax)[A-Za-z0-9_/\-]*)['"]""",
                              html, re.I))):
    print("  %s" % m)
for m in sorted(set(re.findall(r"""url\s*:\s*['"]([^'"]*(?:spy|datasheet)[^'"]*)['"]""", html, re.I))):
    print("  url: %s" % m[:120])
