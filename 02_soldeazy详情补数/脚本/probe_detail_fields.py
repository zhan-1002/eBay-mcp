# -*- coding: utf-8 -*-
"""看 dsheet 结果页/详情里有哪些可回填字段（重点找 Brand / Model / EAN / 类别 / 描述）。"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


P = os.path.join(OUT, "search_rowid_uk.html")
html = open(P, encoding="utf-8", errors="replace").read()
print("文件: %s (%d 字符)\n" % (os.path.basename(P), len(html)))

# 1) 结果表真实行数
m = re.search(r"<table[^>]*tbl_dSheet[^>]*>.*?</table>", html, re.S | re.I)
if m:
    tbl = m.group(0)
    trs = re.findall(r"<tr\b[^>]*>", tbl, re.I)
    print("=== 结果表 tbl_dSheet ===")
    print("  <tr> 标签数: %d | 表长 %d" % (len(trs), len(tbl)))
    # 逐行打印单元格
    for i, r in enumerate(re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbl, re.S | re.I), 1):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", r, re.S | re.I)
        vals = [strip(c)[:38] for c in cells]
        if any(vals):
            print("  行%-2d %s" % (i, vals[:16]))

# 2) 找详情字段名（我要回填的目标字段）
print("\n=== 关键字段在页面里出现的位置 ===")
TARGETS = ["Brand", "品牌", "Model", "型号", "EAN", "UPC", "MPN", "Colour", "Color",
           "颜色", "Type", "类型", "Connectivity", "物品描述", "描述", "eBay类目",
           "类别", "Category", "标题", "Title", "SKU", "物品编号", "Item ID"]
for t in TARGETS:
    hits = [mm.start() for mm in re.finditer(re.escape(t), html)]
    if hits:
        sample = strip(html[max(0, hits[0] - 120):hits[0] + 160])
        print("  %-14s %3d 次  | 例: %s" % (t, len(hits), sample[:130]))
    else:
        print("  %-14s   0 次" % t)

# 3) 详情/编辑入口链接（点进去才有完整字段）
print("\n=== 行内操作链接（edit / preview 等）===")
for mm in re.finditer(r"""(?:onclick|href)=['"]([^'"]{0,160}(?:edit|preview|detail|view)[^'"]{0,160})['"]""",
                     html, re.I):
    u = mm.group(1)
    if any(k in u.lower() for k in ("dsheet", "datasheet", "edit", "preview")):
        print("  %s" % u[:170])

# 4) 表单里可提交的字段（编辑页会用到）
print("\n=== 页面内 form action ===")
for mm in sorted(set(re.findall(r"<form[^>]*action=['\"]([^'\"]+)['\"]", html, re.I))):
    print("  %s" % mm)

# 5) 各 dump 文件一览（便于后续对比）
print("\n=== 已保存的探查文件 ===")
for f in sorted(glob.glob(os.path.join(OUT, "*.html"))):
    print("  %-34s %8.0f KB" % (os.path.basename(f), os.path.getsize(f) / 1024))
