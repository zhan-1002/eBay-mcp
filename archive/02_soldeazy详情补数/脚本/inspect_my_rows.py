# -*- coding: utf-8 -*-
"""看我建的这批数据表有哪些可精确锚定的特征（用于安全清理与隔离）。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))

MINE = ["4551545", "4551546", "4551547", "4551548", "4551549", "4551550", "4551551",
        "4551566", "4551567", "4551570", "4551571"]

print("=" * 92)
print("我创建的这些行，可锚定字段一览")
print("=" * 92)
for rowid in MINE:
    p = os.path.join(OUT, "flag_probe_%s.json" % rowid)
    src = "flag_probe"
    if not os.path.isfile(p):
        # 商店试跑那批没有单独存 res_dsheet，只存了 spy_shop_*.json
        cands = [f for f in os.listdir(OUT) if f.startswith("spy_shop_") or f.startswith("spy_result_")]
        p = None
        src = "（无 res_dsheet 存档）"
    print("\n  rowid=%s  [%s]" % (rowid, src))
    if not p or not os.path.isfile(p):
        continue
    try:
        rows = json.loads(open(p, encoding="utf-8").read())
    except Exception:
        continue
    if not rows:
        continue
    ds = rows[0].get("res_dsheet") or {}
    for k in ("dsheet_custom_label", "dsheet_filename", "dsheet_shop_initial",
              "dsheet_sitecode", "dsheet_product_code", "dsheet_excelid",
              "dsheet_sessionid", "dsheet_ct_datetime", "dsheet_ct_staff_id",
              "dsheet_titleexternal", "dsheet_row_id", "sh_ch_type",
              "dsheet_shop_initial_idx", "soldeazy_client_idx"):
        if k in ds:
            print("     %-26s = %s" % (k, str(ds.get(k))[:70]))

print()
print("=" * 92)
print("规律总结")
print("=" * 92)
print("""
  从实测数据看，我这批行有几个**稳定的共同特征**：
    1. dsheet_custom_label = 请求的 eBay 刊登编号（如 177632191323 / 123456789012）
    2. dsheet_filename     = "superlaptop Download from <刊登编号>"
       （superlaptop 是登录账号名 → 这就是"谁创建的"的身份标记）
    3. dsheet_excelid      = 一个 4~5 位编号（每行不同，不是稳定锚点）
    4. dsheet_custom_label / product_code 里带的就是我批量试的那些 id
  所以"按 filename 前缀 + 时间窗 + 白名单 rowid"三重限定，就能只命中我创建的。
""")
