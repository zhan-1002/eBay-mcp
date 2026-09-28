# -*- coding: utf-8 -*-
"""用『自己账号的 dsheet Row ID』验证搜索能出结果，并把结果表结构摸清。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
BASE_POST = {"mode": "dsheet_list", "second_mode": "dsheet_list",
             "btn_search": "搜索", "page": "1", "limit": "50"}


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def report(html, tag):
    """打印关键信号：结果表是否存在、行数、计数提示。"""
    has_tbl = bool(re.search(r"<table[^>]*tbl_dSheet", html, re.I))
    row_inputs = len(re.findall(r"table_row_id\[", html))
    print("  长度=%d | tbl_dSheet 表存在=%s | 结果行 table_row_id[]=%d"
          % (len(html), has_tbl, row_inputs))
    for m in re.finditer(r"总共[：:][^<]{0,60}", html):
        t = strip(m.group(0))
        if t and set(t) - set("总共： "):
            print("  计数提示: %s" % t[:80])
    if has_tbl:
        m = re.search(r"<table[^>]*tbl_dSheet[^>]*>.*?</table>", html, re.S | re.I)
        tbl = m.group(0)
        ths = [strip(x) for x in re.findall(r"<th\b[^>]*>(.*?)</th>", tbl, re.S | re.I)]
        print("  表头: %s" % [t for t in ths if t])
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbl, re.S | re.I)
        print("  tr 行数: %d" % len(rows))
        for r in rows[:4]:
            tds = [strip(x) for x in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", r, re.S | re.I)]
            if any(tds):
                print("    %s" % [t[:24] for t in tds][:14])
    p = os.path.join(OUT_DIR, "search_%s.html" % tag)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("  已存: %s" % os.path.basename(p))


c = SoldeazyClient()
cases = [
    ("rowid_uk", {"txtdsheetrowid": "4153428"}),
    ("rowid_de", {"txtdsheetrowid": "4235748"}),
    ("sku_uk", {"txtproductcode": "QPCT0005"}),
    ("empty_ref", {}),
]
for tag, extra in cases:
    print("\n" + "=" * 78)
    print("POST 搜索: %s  %s" % (tag, extra))
    print("=" * 78)
    data = dict(BASE_POST)
    data.update(extra)
    try:
        r = c.post("/app/soldeazy/datasheet", data=data)
    except SessionExpired as exc:
        print("[会话过期] %s" % exc)
        sys.exit(3)
    report(r.text, tag)
