# -*- coding: utf-8 -*-
"""探 res_flag / res_message 的取值谱系：区分『对方链接受保护』『无效』『真失败』。

每个 item id 只用一个商店（EB=151），失败信息原样落盘。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
AJAX = "/app/soldeazy/datasheet_ajax"
SHOP = "151"   # EB

# 测试用的 item id 谱系
CASES = [
    ("已知可成功", "177632191323"),
    ("竞品-另一条", "406803296693"),
    ("竞品-第三条", "276643769322"),
    ("明显的假ID", "123456789012"),
    ("空ID片段", ""),
]

c = SoldeazyClient()
hdrs = {"X-Requested-With": "XMLHttpRequest",
        "accept": "application/json, text/javascript, */*; q=0.01",
        "referer": "https://stiger.soldeazy.com/app/soldeazy/datasheet/dsheet_list"}

rows = []
for label, item_id in CASES:
    if not item_id:
        print("\n[跳过空 ID]")
        continue
    payload = {"mode": "create_datasheet_from_listing_spy", "channel_type": "EBAY",
               "item_ids": item_id, "shop_idx": SHOP, "template_idx": "", "profile_idx": ""}
    t0 = time.time()
    try:
        r = c.post(AJAX, data=payload, headers=hdrs)
    except SessionExpired as exc:
        print("[会话过期] %s" % exc)
        sys.exit(3)
    body = r.text
    print("\n" + "=" * 74)
    print("用例: %-12s item_id=%s   (%.1fs)" % (label, item_id, time.time() - t0))
    print("=" * 74)
    print("原始返回: %s" % body[:500])
    try:
        data = r.json()
    except Exception:
        print("  !! 不是 JSON")
        continue
    if isinstance(data, list):
        for row in data:
            print("  res_flag=%s | res_rowid=%s | res_message=%s"
                  % (row.get("res_flag"), row.get("res_rowid"), str(row.get("res_message"))[:160]))
            print("  全部键: %s" % list(row.keys()))
            rows.append({"label": label, "item_id": item_id, **row})
    else:
        print("  %s" % json.dumps(data, ensure_ascii=False)[:300])
    p = os.path.join(OUT, "flag_probe_%s.json" % item_id)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)

print("\n\n" + "=" * 74)
print("汇总：res_flag → 含义（据本次观测）")
print("=" * 74)
seen = {}
for r in rows:
    seen.setdefault(str(r.get("res_flag")), []).append(
        (r["label"], str(r.get("res_message"))[:90], bool(r.get("res_rowid"))))
for flag, lst in sorted(seen.items()):
    print("\n  res_flag=%s  （%d 例）" % (flag, len(lst)))
    for label, msg, has_row in lst:
        print("     %-12s rowid=%-5s %s" % (label, has_row, msg))
