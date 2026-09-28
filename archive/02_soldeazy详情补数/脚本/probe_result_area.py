# -*- coding: utf-8 -*-
"""定位 dsheet_list 的结果区结构：是不是 ajax 加载、结果表格在哪。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "输出", "探查",
                                  "search_item_177632191323.html"))
html = open(P, encoding="utf-8", errors="replace").read()
print("文件: %s (%d 字符)\n" % (os.path.basename(P), len(html)))


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# 1) 所有 table 的概览
print("=" * 78)
print("① 页面里所有 <table> 概览")
print("=" * 78)
for i, m in enumerate(re.finditer(r"<table[^>]*>.*?</table>", html, re.S | re.I), 1):
    seg = m.group(0)
    attrs = re.search(r"<table([^>]*)>", seg).group(1)[:120]
    rows = len(re.findall(r"<tr\b", seg, re.I))
    ths = [strip(x)[:12] for x in re.findall(r"<th\b[^>]*>(.*?)</th>", seg, re.S | re.I)]
    print("  #%d rows=%-4d attrs=%s" % (i, rows, attrs))
    if ths:
        print("       th: %s" % ths[:16])

# 2) 结果区容器 id/class
print()
print("=" * 78)
print("② 结果区容器候选（含 dsheet/list/result/grid 的 id/class）")
print("=" * 78)
for m in sorted(set(re.findall(r"""id=['"]([^'"]*(?:dsheet|result|grid|list_table|table_)[^'"]*)['"]""",
                              html, re.I))):
    print("  id=%s" % m)
for m in sorted(set(re.findall(r"""class=['"]([^'"]*(?:result|grid|datatable|dsheet_list)[^'"]*)['"]""",
                              html, re.I)))[:20]:
    print("  class=%s" % m[:90])

# 3) ajax 提交/加载结果的 JS
print()
print("=" * 78)
print("③ 搜索提交 / ajax 加载结果的 JS 片段")
print("=" * 78)
for kw in ("form_search", "datasheet_ajax", ".submit(", "btn_search", "ajax"):
    print("\n  --- 关键词: %s ---" % kw)
    n = 0
    for m in re.finditer(re.escape(kw), html):
        i = m.start()
        seg = html[max(0, i - 200):i + 260]
        if "<script" in seg or "function" in seg or "$(" in seg or "url" in seg:
            print("    …%s…" % strip(seg)[:230])
            n += 1
        if n >= 2:
            break

# 4) 内联脚本里 与结果渲染相关
print()
print("=" * 78)
print("④ 内联脚本中 form_search 的绑定")
print("=" * 78)
for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I):
    body = m.group(1)
    if "form_search" in body or "btn_search" in body:
        print("  --- script 片段 (%d 字符) ---" % len(body))
        for mm in re.finditer(r".{120}(?:form_search|btn_search).{200}", body, re.S):
            print("    %s" % strip(mm.group(0))[:280])
            print()
            break

# 5) 结果行是否有 物品ID 列
print()
print("=" * 78)
print("⑤ 页面里出现 12~13 位数字的位置统计")
print("=" * 78)
ids = re.findall(r"\b(\d{12,13})\b", html)
print("  12~13 位数字出现 %d 次，去重 %d 个" % (len(ids), len(set(ids))))
print("  样例: %s" % list(dict.fromkeys(ids))[:10])
