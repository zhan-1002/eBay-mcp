# -*- coding: utf-8 -*-
"""写操作清单（manifest）：所有对生产账号的写操作先在这里记账。

原则：
  - 每次创建/修改生产账号数据前，先把意图写入 _manifest/pending.jsonl
  - 服务端返回 rowid 后，追加到 _manifest/created_rows.jsonl（含四要素，供将来精确复验）
  - 删除永不自动执行；必须由人工确认后，按 rowid 白名单逐行复验

用法（供其它脚本 import）:
    from manifest import record_intent, record_created
    record_intent("listing_spy", {"item_id": "177632191323", "shop_idx": "151"})
    record_created("4551545", item_id="177632191323", shop="151", psku="177632191323-P",
                   site="UK", batch="test_spy_shops")
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
MANIFEST_DIR = os.path.join(PROJ, "输出", "_manifest")
PENDING = os.path.join(MANIFEST_DIR, "pending.jsonl")
CREATED = os.path.join(MANIFEST_DIR, "created_rows.jsonl")


def _ensure():
    os.makedirs(MANIFEST_DIR, exist_ok=True)


def _append(path, obj):
    _ensure()
    obj = dict(obj)
    obj.setdefault("at", time.strftime("%Y-%m-%d %H:%M:%S"))
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def record_intent(action, params=None):
    """记录"即将对生产账号做什么"（在真正提交之前调用）。"""
    _append(PENDING, {"kind": "intent", "action": action, "params": params or {}})


def record_created(rowid, item_id="", shop="", psku="", site="", batch="", extra=None):
    """记录已创建的数据表（服务端返回 rowid 后调用）。"""
    rec = {"kind": "created", "rowid": str(rowid), "item_id": str(item_id),
           "shop": str(shop), "psku": str(psku), "site": str(site), "batch": batch}
    if extra:
        rec["extra"] = extra
    _append(CREATED, rec)


def load_created():
    """读回所有已创建记录（清单就是唯一权威，不靠页面特征识别）。"""
    if not os.path.isfile(CREATED):
        return []
    out = []
    for line in open(CREATED, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def seed_from_sealed_record():
    """把封存文档里那 11 条补写进清单（一次性回填）。"""
    rows = [
        ("4551545", "177632191323", "151", "177632191323-P", "UK", "test_spy_shops"),
        ("4551546", "177632191323", "4337", "177632191323-P", "UK", "test_spy_shops"),
        ("4551547", "177632191323", "137", "177632191323-P", "UK", "test_spy_shops"),
        ("4551548", "177632191323", "152", "177632191323-P", "UK", "test_spy_shops"),
        ("4551549", "177632191323", "187", "177632191323-P", "UK", "test_spy_shops"),
        ("4551550", "177632191323", "195", "177632191323-P", "UK", "test_spy_shops"),
        ("4551551", "177632191323", "164", "177632191323-P", "UK", "test_spy_shops"),
        ("4551566", "177632191323", "151", "177632191323-P", "UK", "probe_flag_spectrum"),
        ("4551567", "406803296693", "151", "406803296693-P", "UK", "probe_flag_spectrum"),
        ("4551570", "276643769322", "151", "BT-EB-PIXFAB-T8-MAIN-APPLE-NEW-P", "UK",
         "probe_flag_spectrum"),
        ("4551571", "123456789012", "151", "", "US", "probe_flag_spectrum"),
    ]
    existing = {r.get("rowid") for r in load_created()}
    n = 0
    for rowid, item_id, shop, psku, site, batch in rows:
        if rowid in existing:
            continue
        record_created(rowid, item_id=item_id, shop=shop, psku=psku, site=site, batch=batch,
                       extra={"note": "回填自 生产账号数据表创建记录_封存.md"})
        n += 1
    return n


if __name__ == "__main__":
    added = seed_from_sealed_record()
    print("回填 %d 条到 %s" % (added, CREATED))
    recs = load_created()
    print("清单现有 %d 条:" % len(recs))
    for r in recs:
        print("   rowid=%-9s shop=%-5s site=%-3s psku=%-38s item=%s"
              % (r["rowid"], r["shop"], r["site"], r["psku"][:36], r["item_id"]))
