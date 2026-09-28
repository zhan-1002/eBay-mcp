# -*- coding: utf-8 -*-
"""在搜索结果页里定位 tbl_dSheet 结果表并解析行。"""
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


print("=== tbl_dSheet 出现次数: %d ===" % len(re.findall(r"tbl_dSheet", html)))
for m in re.finditer(r"<table[^>]*tbl_dSheet[^>]*>", html, re.I):
    print("  标签: %s" % m.group(0)[:200])

m = re.search(r"<table[^>]*tbl_dSheet[^>]*>.*?</table>", html, re.S | re.I)
if not m:
    print("\n没找到 tbl_dSheet 的完整 table 标签（可能由 ajax 注入）")
    # 找它的容器
    for mm in re.finditer(r"tbl_dSheet", html):
        i = mm.start()
        if "<table" in html[i:i + 300]:
            print("  附近: %s" % html[i:i + 400].replace("\n", " ")[:400])
else:
    tbl = m.group(0)
    print("\n结果表长度: %d" % len(tbl))
    ths = [strip(x) for x in re.findall(r"<th\b[^>]*>(.*?)</th>", tbl, re.S | re.I)]
    print("表头: %s" % [t for t in ths if t])
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbl, re.S | re.I)
    print("行数: %d" % len(rows))
    for r in rows[:5]:
        tds = [strip(x) for x in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", r, re.S | re.I)]
        if any(tds):
            print("  ROW: %s" % [t[:26] for t in tds][:15])

print("\n=== 结果计数提示（总共：/ Total record selected:）===")
for m2 in re.finditer(r"(总共[：:][^<]{0,40}|Total record selected[^<]{0,40})", html, re.I):
    print("  %s" % strip(m2.group(0))[:80])

print("\n=== 页面里『物品编号』相关行（结果可能用卡片而非表格）===")
for m2 in re.finditer(r"物品编号", html):
    i = m2.start()
    ctx = strip(html[max(0, i - 200):i + 400])
    if "177632191323" in ctx:
        print("  …%s…" % ctx[:300])
        print()

print("=== 检查是否返回了『查看数据表』链接（说明搜到记录）===")
links = re.findall(r"href=['\"]([^'\"]*(?:datasheet|dsheet)[^'\"]*)['\"]", html, re.I)
print("  数据表相关链接 %d 个，样例: %s" % (len(links), links[:8]))

print("\n=== selected / 勾选框（结果行标志）===")
print("  name=table_row_id[...] 数量: %d" % len(re.findall(r"table_row_id\[", html)))
print("  出现 'dsheet_row_id' 次数: %d" % len(re.findall(r"dsheet_row_id", html)))
