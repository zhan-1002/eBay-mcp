# -*- coding: utf-8 -*-
"""验证按行取详情：POST is_dsheet_row_id 后，在返回页里找该行的数据块。"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
ROW = "4153428"
c = SoldeazyClient()


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def analyze(tag, html):
    print("\n" + "=" * 78)
    print("### %s : 长度 %d" % (tag, len(html)))
    print("=" * 78)
    p = os.path.join(OUT, "detail_%s.html" % tag)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    # 结果表
    m = re.search(r"<table[^>]*tbl_dSheet[^>]*>.*?</table>", html, re.S | re.I)
    if m:
        tbl = m.group(0)
        trs = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbl, re.S | re.I)
        print("  tbl_dSheet 存在，tr 数=%d，表长=%d" % (len(trs), len(tbl)))
        # 打印整张表（含隐藏字段）
        print("  --- 结果表完整 HTML（前 3500 字符）---")
        print("  %s" % tbl[:3500])
    else:
        print("  tbl_dSheet 不存在（0 结果或未渲染）")

    # 隐藏的详情块
    print("\n  --- 含 '%s' 的所有片段（最多 4 处）---" % ROW)
    n = 0
    for mm in re.finditer(re.escape(ROW), html):
        i = mm.start()
        seg = html[max(0, i - 200):i + 900]
        if "tbl_dSheet" in seg or "dsrid" in seg or "detail" in seg:
            print("\n  …%s…" % re.sub(r"\s+", " ", seg)[:800])
            n += 1
            if n >= 4:
                break

    for key in ("Brand", "MPN", "EAN", "Colour", "Color", "Model", "物品描述", "Description"):
        cnt = len(re.findall(re.escape(key), html))
        if cnt:
            print("  含 %-12s %d 次" % (key, cnt))


# 1) 专用参数
data = {"mode": "dsheet_list", "second_mode": "dsheet_list", "is_dsheet_row_id": "1",
        "txtdsheetrowid": ROW, "btn_search": "搜索", "page": "1", "limit": "50"}
r = c.post("/app/soldeazy/datasheet", data=data)
analyze("rowid_param", r.text)

# 2) 用 eb_hist_drid 那种方式（按 SKU）看是否出现详情块
data2 = {"mode": "dsheet_list", "second_mode": "dsheet_list", "is_dsheet_row_id": "1",
         "txtproductcode": "QPCT0005", "btn_search": "搜索", "page": "1", "limit": "50"}
r2 = c.post("/app/soldeazy/datasheet", data=data2)
analyze("sku_param", r2.text)
