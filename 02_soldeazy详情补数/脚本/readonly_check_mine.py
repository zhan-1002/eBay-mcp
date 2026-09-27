# -*- coding: utf-8 -*-
"""只读：实时查我创建的那批行，确认可锚定特征 & 页面提供的分组/标记手段。

不删除、不修改任何数据。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
MINE = ["4551545", "4551546", "4551547", "4551548", "4551549", "4551550", "4551551",
        "4551566", "4551567", "4551570", "4551571"]

c = SoldeazyClient()
BASE = {"mode": "dsheet_list", "second_mode": "dsheet_list", "btn_search": "搜索",
        "page": "1", "limit": "50"}


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_row(html):
    m = re.search(r"<table[^>]*tbl_dSheet[^>]*>.*?</table>", html, re.S | re.I)
    if not m:
        return None
    tbl = m.group(0)
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbl, re.S | re.I)
    for r in rows:
        if "table-row" not in r:
            continue
        out = {}
        hid = re.search(r"<input type='hidden' title='(\d+)'", r)
        out["rowid"] = hid.group(1) if hid else ""
        t = re.search(r"<b>([^<]+)</b>", r)
        out["title"] = t.group(1) if t else ""
        shop = re.search(r"<td align='center'>([A-Z]+)</td>", r)
        out["site"] = shop.group(1) if shop else ""
        psku = re.search(r"主货品标籤:</span><span class='sub-row sub-row-psku'>([^<]*)</span>", r)
        out["psku"] = psku.group(1) if psku else ""
        img = re.search(r"<a href='([^']+)' class='thumb-img-link'", r)
        out["img"] = (img.group(1)[:60] + "...") if img else ""
        # SKU 列与价格列
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)
        out["cells"] = [strip(x)[:40] for x in tds]
        return out
    return None


print("=" * 96)
print("逐个查我创建的行（只读）")
print("=" * 96)
for rowid in MINE:
    data = dict(BASE)
    data["txtdsheetrowid"] = rowid
    try:
        html = c.post("/app/soldeazy/datasheet", data=data).text
    except SessionExpired as exc:
        print("[会话过期] %s" % exc)
        sys.exit(3)
    row = parse_row(html)
    print("\n  rowid=%s" % rowid)
    if not row:
        print("     查不到（可能已被删除，或本次查询无结果）")
        continue
    print("     标题   : %s" % row["title"][:70])
    print("     站点   : %s" % row["site"])
    print("     主货品标籤: %s" % row["psku"])
    print("     单元格 : %s" % row["cells"][:12])

print()
print("=" * 96)
print("页面提供的『分组/筛选』手段（用于隔离，不依赖人工辨认）")
print("=" * 96)
html = c.dsheet_list_html()
print("  左侧筛选字段（name）:")
for m in sorted(set(re.findall(r"<(?:input|select|textarea)[^>]*name=['\"]([^'\"]+)['\"]", html))):
    if re.search(r"(?i)(filename|date|tag|label|user|staff|creator|shop|site|upload)", m):
        print("     %s" % m)
print("\n  是否提供『上载文件名称』筛选: %s" % ("txtfilename" in html))
print("  是否提供『修改日期』筛选    : %s" % ("listdate" in html))
print("  是否提供『标签』筛选        : %s" % ("txttag" in html))
