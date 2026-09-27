# -*- coding: utf-8 -*-
"""找『从刊登下载器创建数据表』的提交方式，以及是否存在只读预览接口。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
html = open(os.path.join(OUT, "dsheet_list.html"), encoding="utf-8", errors="replace").read()


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


print("=" * 78)
print("① tab_create_from_listing_spy 整段（截取 6000 字符）")
print("=" * 78)
m = re.search(r"id=[\"']tab_create_from_listing_spy[\"'].*?(?=<div class=\"tab_section|<div class='tab_section|</fieldset>\s*</div>\s*<div class)",
              html, re.S | re.I)
if m:
    seg = m.group(0)
    print("段长 %d" % len(seg))
    # 只打印非协议文本部分
    for mm in re.finditer(r"<(input|select|textarea|button|a)\b[^>]*>", seg, re.I):
        print("  %s" % mm.group(0)[:230])
else:
    print("  没切出该段")

print()
print("=" * 78)
print("② 该段里的按钮/提交入口")
print("=" * 78)
for mm in re.finditer(r"listing_spy", html):
    i = mm.start()
    seg = html[max(0, i - 700):i + 900]
    for b in re.finditer(r"<(a|button|input)\b[^>]*(?:submit|spy_init|do_agree|汇入|建立|确定|新增)[^>]*>", seg, re.I):
        print("  %s" % b.group(0)[:230])

print()
print("=" * 78)
print("③ listing_spy 相关的 JS 提交/接口调用")
print("=" * 78)
n = 0
for mm in re.finditer(r"\$\.[a-z]+\(|ajax|\.submit\(|window\.open|location", html):
    i = mm.start()
    seg = re.sub(r"\s+", " ", html[max(0, i - 400):i + 600])
    if "listing_spy" in seg:
        print("  …%s…" % seg[:480])
        print()
        n += 1
    if n >= 8:
        break

print("=" * 78)
print("④ 候选：只读的『预览/查询刊登』接口")
print("=" * 78)
cands = set()
for pat in (r"""['"](/app/soldeazy/[A-Za-z0-9_/]*spy[A-Za-z0-9_/]*)['"]""",
            r"""['"](/app/soldeazy/[A-Za-z0-9_/]*preview[A-Za-z0-9_/]*)['"]""",
            r"""['"](/app/soldeazy/[A-Za-z0-9_/]*(?:get|fetch|query)[A-Za-z0-9_/]*)['"]"""):
    for mm in re.finditer(pat, html, re.I):
        cands.add(mm.group(1))
for u in sorted(cands):
    print("  %s" % u)

print()
print("=" * 78)
print("⑤ 弹层里所有表单元素 name（新增数据表弹层）")
print("=" * 78)
m2 = re.search(r"id=[\"']divShopInitPrompt[\"'].*", html, re.S)
if m2:
    seg = m2.group(0)[:200000]
    names = []
    for mm in re.finditer(r"<(?:input|select|textarea)\b[^>]*name=['\"]([^'\"]+)['\"][^>]*>", seg, re.I):
        nm = mm.group(1)
        if nm not in names:
            names.append(nm)
    print("  共 %d 个：" % len(names))
    for i in range(0, len(names), 4):
        print("    %s" % names[i:i + 4])
