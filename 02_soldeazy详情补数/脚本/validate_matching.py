# -*- coding: utf-8 -*-
"""验证判据：返回数据的真实性与请求的 item id 是否一致。

观察到的关键事实（2026-09-14 实测）：
  请求 123456789012（不存在）→ 返回 "Firewatch PS4 - Limited Run"、类目 139973、sitecode=US
  → 服务端在抓不到目标时会**回落到其它数据**，且 res_flag 仍是 0（"成功"）
  因此【不能只看 res_flag】，必须校验返回内容与请求 id 的对应关系。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))


def load(item_id):
    p = os.path.join(OUT, "flag_probe_%s.json" % item_id)
    if not os.path.isfile(p):
        return None
    rows = json.loads(open(p, encoding="utf-8").read())
    return rows[0] if rows else None


CASES = ["177632191323", "406803296693", "276643769322", "123456789012"]
# 已知期望：前三个是无线耳机（01 模块采到），第四个不存在
EXPECT_KEYWORD = "wireless earbuds earphones"

print("=" * 96)
print("判定信号对比")
print("=" * 96)
print("%-16s %-10s %-8s %-34s %-10s %s" % ("请求id", "res_flag", "rowid?", "返回标题", "类目", "判定"))
for iid in CASES:
    r = load(iid)
    if not r:
        print("%-16s (无数据)" % iid)
        continue
    ds = r.get("res_dsheet") or {}
    title = str(ds.get("dsheet_titleexternal") or "")
    cat = str(ds.get("dsheet_ebcategory") or "")
    flag = str(r.get("res_flag"))
    rowid = bool(r.get("res_rowid"))

    # --- 判定规则 ---
    reasons = []
    # 1) 请求id 是否出现在返回内容里（标题/产品代码/自定义标签/文件名）
    in_content = (iid in title
                  or iid == str(ds.get("dsheet_product_code") or "")
                  or iid == str(ds.get("dsheet_custom_label") or "")
                  or iid in str(ds.get("dsheet_filename") or ""))
    # 2) 标题是否与关键词品类一致
    toks = set(re.findall(r"[a-z]+", title.lower()))
    kw_toks = set(EXPECT_KEYWORD.split())
    kw_hit = len(toks & kw_toks)
    # 3) 业务字段是否像"真数据"
    has_biz = bool(str(ds.get("dsheet_product_code") or "").strip()) and \
        str(ds.get("dsheet_currency") or "") in ("GBP", "EUR", "USD")

    if not rowid:
        verdict = "真失败（无 rowid）"
    elif not in_content:
        verdict = "⚠ 内容与请求id不符"
    elif kw_hit == 0:
        verdict = "⚠ 品类不符"
    else:
        verdict = "✅ 有效"

    print("%-16s %-10s %-8s %-34s %-10s %s" % (
        iid, flag, rowid, title[:32], cat, verdict))
    print("%-16s   细节: id出现在内容=%s | 标题与关键词交集=%d | 业务字段完整=%s"
          % ("", in_content, kw_hit, has_biz))

print()
print("=" * 96)
print("结论：判据设计")
print("=" * 96)
print("""
  1. res_flag 只能判"请求被拒"（如 rowid 缺失 / shop 无效 / token 失效），
     **不能**判内容真假（实测假 id 也返回 res_flag=0）
  2. 内容真实性用三重校验：
        a) 请求的 item id 是否出现在返回的标题/产品代码/自定义标签/文件名里
        b) 返回标题是否含关键词品类（如 wireless/earbuds）
        c) 关键业务字段是否完整（currency / price / category / product_code）
  3. 三者全过才落库；a 不过或 b 不过 → 记为"内容不符"（而不是失败）；
     rowid 缺失 → 记为"拒绝/失败"
""")
