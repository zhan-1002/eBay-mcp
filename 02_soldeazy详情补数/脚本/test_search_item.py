# -*- coding: utf-8 -*-
"""实测：用 txtitemid 按 eBay 物品 ID 搜 dsheet_list，看返回什么、有哪些字段。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
os.makedirs(OUT_DIR, exist_ok=True)

# 从 01 模块的采集结果里取几个真实 item id
COLLECTED = sorted(__import__("glob").glob(
    r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_*.json"))[-1]
d = json.load(open(COLLECTED, encoding="utf-8"))
items = d["items"][:5]
print("采集源: %s" % os.path.basename(COLLECTED))
print("取前 %d 条 item id 做测试: %s" % (len(items), [i["item_id"] for i in items]))

c = SoldeazyClient()

for it in items[:2]:
    iid = it["item_id"]
    print("\n" + "=" * 78)
    print("按物品ID搜索: %s  (标题: %s)" % (iid, it["title"][:46]))
    print("=" * 78)
    data = {
        "mode": "dsheet_list",
        "second_mode": "dsheet_list",
        "txtitemid": iid,
        "btn_search": "Search",
        "page": "1",
        "limit": "50",
    }
    try:
        html = c.post("/app/soldeazy/datasheet", data=data).text
    except SessionExpired as exc:
        print("[会话过期] %s" % exc)
        sys.exit(3)

    print("返回长度: %d 字符" % len(html))
    p = os.path.join(OUT_DIR, "search_item_%s.html" % iid)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("已存: %s" % os.path.basename(p))

    # 解析结果表
    t = re.search(r"<table[^>]*>.*?</table>", html, re.S | re.I)
    if not t:
        print("  没解析到表格")
        continue
    tbl = t.group(0)

    def strip(s):
        s = re.sub(r"<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    ths = [strip(x) for x in re.findall(r"<th\b[^>]*>(.*?)</th>", tbl, re.S | re.I)]
    print("\n表头(%d): %s" % (len(ths), [x for x in ths if x]))

    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbl, re.S | re.I)
    print("数据行数: %d" % len(rows))
    for r in rows[:6]:
        tds = [strip(x) for x in re.findall(r"<td\b[^>]*>(.*?)</td>", r, re.S | re.I)]
        if any(tds):
            print("  ROW: %s" % [x[:30] for x in tds][:14])

    # 结果条数提示
    for pat in (r"(\d+)\s*(?:笔|条|results?|records?)", r"共\s*(\d+)"):
        mm = re.search(pat, strip(html), re.I)
        if mm:
            print("  条数提示: %s" % mm.group(0)[:40])
            break
    if iid in html:
        print("  ✅ 返回页面里出现了该物品ID")
    else:
        print("  ⚠ 返回页面里没有该物品ID")
