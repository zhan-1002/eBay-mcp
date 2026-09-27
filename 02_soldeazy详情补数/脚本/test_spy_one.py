# -*- coding: utf-8 -*-
"""试跑 1 条：从刊登下载器创建数据表（listing_spy）。

只跑 1 个 item id。会真实创建 1 张数据表（返回 res_rowid），便于确认链路与字段。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
ITEM_ID = "177632191323"          # 竞品搜索页采到的真实 item id
AJAX = "/app/soldeazy/datasheet_ajax"

c = SoldeazyClient()
print("会话保存于: %s" % c.saved_at)

# ---------- 1) 同意协议 ----------
print("\n[1] POST mode=agree（点『我同意』）")
try:
    r = c.post(AJAX, data={"mode": "agree"},
               headers={"X-Requested-With": "XMLHttpRequest",
                        "accept": "application/json, text/javascript, */*; q=0.01",
                        "referer": "https://stiger.soldeazy.com/app/soldeazy/datasheet/dsheet_list"})
except SessionExpired as exc:
    print("[会话过期] %s" % exc)
    sys.exit(3)
print("  HTTP %s | 返回: %s" % (r.status_code, r.text[:300]))

# ---------- 2) 试跑：最小参数 ----------
def try_spy(tag, payload, save=True):
    print("\n[2] POST mode=create_datasheet_from_listing_spy  (%s)" % tag)
    print("  参数: %s" % json.dumps(payload, ensure_ascii=False))
    try:
        rr = c.post(AJAX, data=payload,
                    headers={"X-Requested-With": "XMLHttpRequest",
                             "accept": "application/json, text/javascript, */*; q=0.01",
                             "referer": "https://stiger.soldeazy.com/app/soldeazy/datasheet/dsheet_list"})
    except SessionExpired as exc:
        print("  [会话过期] %s" % exc)
        return None
    print("  HTTP %s | content-type %s" % (rr.status_code, rr.headers.get("content-type", "")[:40]))
    body = rr.text
    print("  原始返回(前 800): %s" % body[:800])
    if save:
        p = os.path.join(OUT, "spy_result_%s_%s.json" % (tag, time.strftime("%H%M%S")))
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        print("  已存: %s" % os.path.basename(p))
    try:
        data = rr.json()
    except Exception:
        return None
    print("  解析结果:")
    if isinstance(data, list):
        for i, row in enumerate(data):
            print("     [%d] %s" % (i, json.dumps(row, ensure_ascii=False)[:400]))
    else:
        print("     %s" % json.dumps(data, ensure_ascii=False)[:600])
    return data


# 最小参数（不带 shop_idx）
res_min = try_spy("minimal", {
    "mode": "create_datasheet_from_listing_spy",
    "channel_type": "EBAY",
    "item_ids": ITEM_ID,
})

# 若最小参数不通过，带上 shop_idx（用 BKH=4455 试；不指定时用第一个非空商店）
need_shop = res_min is None or (isinstance(res_min, list) and any(
    str(x.get("res_flag", 0)) not in ("0", "1") or not x.get("res_rowid") for x in res_min))
if need_shop:
    print("\n  → 最小参数未成功，带上 shop_idx / template_idx / profile_idx 重试")
    res_full = try_spy("with_shop", {
        "mode": "create_datasheet_from_listing_spy",
        "channel_type": "EBAY",
        "item_ids": ITEM_ID,
        "shop_idx": "4455",
        "template_idx": "",
        "profile_idx": "",
    })
else:
    print("\n  → 最小参数已成功，无需重试")
