# -*- coding: utf-8 -*-
"""试跑：换不同 shop_idx，找出哪个商店的 eBay token 有效。"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
AJAX = "/app/soldeazy/datasheet_ajax"
ITEM_ID = sys.argv[1] if len(sys.argv) > 1 else "177632191323"

# 候选商店：实测里出现过 EB(151)=UK 那张数据表、LLY(4337)=DE 那张；
# 再补几个看起来是主力店的
CANDIDATES = [
    ("151", "EB  (实测有 UK 数据表)"),
    ("4337", "LLY (实测有 DE 数据表)"),
    ("137", "MO"),
    ("152", "EL"),
    ("187", "BOBO"),
    ("195", "BSD"),
    ("164", "GO"),
    ("167", "SB"),
]

c = SoldeazyClient()
hdrs = {"X-Requested-With": "XMLHttpRequest",
        "accept": "application/json, text/javascript, */*; q=0.01",
        "referer": "https://stiger.soldeazy.com/app/soldeazy/datasheet/dsheet_list"}

print("item_id = %s" % ITEM_ID)
results = {}
for idx, label in CANDIDATES:
    payload = {"mode": "create_datasheet_from_listing_spy", "channel_type": "EBAY",
               "item_ids": ITEM_ID, "shop_idx": idx, "template_idx": "", "profile_idx": ""}
    try:
        r = c.post(AJAX, data=payload, headers=hdrs)
    except SessionExpired as exc:
        print("[会话过期] %s" % exc)
        sys.exit(3)
    body = r.text
    try:
        data = r.json()
    except Exception:
        data = None
    msg = ""
    flag = ""
    rowid = ""
    if isinstance(data, list) and data:
        msg = str(data[0].get("res_message") or "")
        flag = str(data[0].get("res_flag"))
        rowid = str(data[0].get("res_rowid") or "")
    print("  shop=%-5s %-24s res_flag=%-3s rowid=%-10s msg=%s"
          % (idx, label, flag, rowid or "-", msg[:70]))
    results[idx] = (flag, rowid, msg, body)
    with open(os.path.join(OUT, "spy_shop_%s.json" % idx), "w", encoding="utf-8", newline="\n") as f:
        f.write(body)

print("\n=== 小结 ===")
ok = [k for k, v in results.items() if v[1]]
print("  有 res_rowid 的商店: %s" % (ok or "无"))
for k, v in results.items():
    if not v[1]:
        print("  %-5s 失败: %s" % (k, v[2][:90]))
