# -*- coding: utf-8 -*-
"""从已 dump 的 dsheet_list.html 里精确提取：搜索表单字段 + 物品ID 相关搜索能力。

不联网、不开浏览器。用法:
    python probe_search_form.py
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.normpath(os.path.join(HERE, "..", "输出", "探查", "dsheet_list.html"))

html = open(HTML, encoding="utf-8", errors="replace").read()
print("HTML: %s (%d 字符)\n" % (os.path.basename(HTML), len(html)))


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- 1. form_search 整段 ----------
print("=" * 78)
print("① form_search 整段（截断到 4000 字符）")
print("=" * 78)
m = re.search(r"<form[^>]*id=['\"]form_search['\"].*?</form>", html, re.S | re.I)
if not m:
    print("  没找到 form_search")
else:
    seg = m.group(0)
    print("  长度 %d" % len(seg))
    print(seg[:4000])

# ---------- 2. form_search 内的控件明细 ----------
print()
print("=" * 78)
print("② form_search 内的 name 清单")
print("=" * 78)
if m:
    seg = m.group(0)
    names = re.findall(r"<(?:input|select|textarea)\b[^>]*name=['\"]([^'\"]+)['\"]", seg, re.I)
    from collections import Counter
    for n, c in Counter(names).most_common():
        print("   %-34s x%d" % (n, c))

# ---------- 3. 物品ID 相关 ----------
print()
print("=" * 78)
print("③ 物品ID / item id 搜索线索")
print("=" * 78)
for kw in ("物品ID", "item_id", "itemid", "ItemID", "ebay_item", "listing_spy_item_ids",
           "txt_item", "search_item"):
    idxs = [mm.start() for mm in re.finditer(re.escape(kw), html, re.I)]
    print("   %-22s 出现 %d 次" % (kw, len(idxs)))
    for i in idxs[:2]:
        ctx = strip_tags(html[max(0, i - 220):i + 220])
        print("       …%s…" % ctx[:200])

# ---------- 4. 表头列与可能的字段名映射 ----------
print()
print("=" * 78)
print("④ 表头（th）与 data 属性")
print("=" * 78)
table = re.search(r"<table[^>]*id=['\"][^'\"]*['\"][^>]*>.*?</table>", html, re.S | re.I)
if table:
    ths = [strip_tags(t) for t in re.findall(r"<th\b[^>]*>(.*?)</th>", table.group(0), re.S | re.I)]
    print("  th: %s" % [t for t in ths if t])
    for k in ("class", "id", "data-"):
        attrs = re.findall(r"<th\b[^>]*%s=['\"]([^'\"]+)['\"]" % k, table.group(0), re.I)
        if attrs:
            print("  th 的 %s: %s" % (k, attrs[:20]))

# ---------- 5. 行内是否有物品ID数值 ----------
print()
print("=" * 78)
print("⑤ 表格数据行里的 eBay 物品 ID（12~13 位数字）")
print("=" * 78)
ids = re.findall(r"\b(\d{12,13})\b", html)
from collections import Counter
uniq = Counter(ids)
print("  抓到 %d 个数字串（去重 %d 个），前 10: %s" % (len(ids), len(uniq), uniq.most_common(10)))
# 找这些 ID 附近的上下文，判断它属于哪列
for i, (v, c) in enumerate(uniq.most_common(3)):
    pos = html.find(v)
    print("   %s 上下文: …%s…" % (v, strip_tags(html[max(0, pos - 260):pos + 120])[:230]))

# ---------- 6. 搜索相关的 JS 函数 ----------
print()
print("=" * 78)
print("⑥ 搜索/提交相关 JS（内联脚本里）")
print("=" * 78)
for m2 in re.finditer(r"function\s+(\w*(?:search|Search|filter|submit)\w*)\s*\([^)]*\)", html):
    print("   function %s" % m2.group(1))
for m2 in re.finditer(r"""['"]#?form_search['"]""", html):
    i = m2.start()
    print("   …%s…" % strip_tags(html[max(0, i - 200):i + 200])[:190])
