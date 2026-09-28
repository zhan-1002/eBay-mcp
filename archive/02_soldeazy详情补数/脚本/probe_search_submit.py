# -*- coding: utf-8 -*-
"""找 dsheet_list 的搜索按钮/提交方式，以及必需的表单参数。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "输出", "探查",
                                  "search_item_177632191323.html"))
html = open(P, encoding="utf-8", errors="replace").read()


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


print("=" * 78)
print("① 搜索按钮相关（btn_search / filter-btn / leftmenu-btn 的实际标签）")
print("=" * 78)
for m in re.finditer(r"<[^>]*(?:btn_search|search-btn|filter-btn|leftmenu-btn)[^>]*>", html, re.I):
    print("  %s" % m.group(0)[:220])

print("\n=== 按钮附近的文本 ===")
for m in re.finditer(r"btn_search", html, re.I):
    i = m.start()
    seg = html[max(0, i - 300):i + 300]
    if "<input" in seg or "<button" in seg or "<a " in seg:
        print("  …%s…" % seg.replace("\n", " ")[:320])
        print()

print("=" * 78)
print("② txtitemid 字段的完整标签")
print("=" * 78)
for m in re.finditer(r"<input[^>]*name=['\"]txtitemid['\"][^>]*>", html, re.I):
    print("  %s" % m.group(0)[:300])
    i = m.start()
    print("  上下文: …%s…" % strip(html[max(0, i - 400):i + 400])[:300])

print()
print("=" * 78)
print("③ 结果表 dsheet_list / tbl_dSheet 的结构")
print("=" * 78)
for key in ("tbl_dSheet", "id='dsheet_list'", 'id="dsheet_list"', "table_row_id"):
    for m in re.finditer(re.escape(key), html):
        i = m.start()
        print("\n  --- %s @ %d ---" % (key, i))
        print("  %s" % html[max(0, i - 300):i + 500].replace("\n", " ")[:700])
        break

print()
print("=" * 78)
print("④ 页面里的 “共/笔/条” 计数提示（判断是否 0 结果）")
print("=" * 78)
for m in re.finditer(r"[^<>]{0,60}(共|笔|条数|total|Total)[^<>]{0,60}", html):
    t = strip(m.group(0))
    if any(k in t for k in ("共", "笔", "条数", "total", "Total")) and len(t) < 120:
        print("  %s" % t[:110])

print()
print("=" * 78)
print("⑤ 结果行模板：找 table_row_id 输入框（结果行标志）")
print("=" * 78)
hits = re.findall(r"<input[^>]*name=['\"]table_row_id[^'\"\[]*['\"][^>]*>", html, re.I)
print("  table_row_id 输入框数: %d" % len(hits))
for h in hits[:3]:
    print("   %s" % h[:180])
