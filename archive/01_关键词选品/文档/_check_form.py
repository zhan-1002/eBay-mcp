# -*- coding: utf-8 -*-
"""对照刊登表单必填项，盘点已采数据够不够。不联网。"""
import json
import sys
from collections import Counter

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)
from analyze import detect_brands, specifics_freq, tokenize  # noqa: E402
import report_market as rm  # noqa: E402

JSON_PATH = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\haihu_8075_uk_wireless_earbuds_20260914_113146.json"
d = json.load(open(JSON_PATH, encoding="utf-8"))
items = d["items"]
titles = [it["title"] for it in items]
spec_items = [it for it in items if it.get("item_specifics")]

print("样本 %d 条；有详情页数据的 %d 条（前 %d 位）" % (len(items), len(spec_items), len(spec_items)))
print()

# ---------- 1. 表单必填项覆盖 ----------
print("=" * 78)
print("① 刊登表单必填项：已采 · 覆盖情况")
print("=" * 78)
FORM = [("Brand", "必须"), ("Connectivity", "必须"), ("Model", "必须"),
        ("Colour", "必须"), ("Type", "必须"), ("EAN", "建议"),
        ("MPN", "建议"), ("Form Factor", "—"), ("Wireless Technology", "—"),
        ("Features", "—"), ("Country of Origin", "—")]
n = len(spec_items) or 1
names = Counter()
for it in spec_items:
    for s in it["item_specifics"]:
        names[s["name"]] += 1
print("%-24s %-6s %-8s %s" % ("属性", "重要性", "覆盖", "说明"))
for name, imp in FORM:
    c = names.get(name, 0)
    has_value = 0
    useless = {"doesn't apply", "does not apply", "n/a", "no", "unbranded", "generic", "none"}
    for it in spec_items:
        for s in it["item_specifics"]:
            if s["name"] == name and (s["value"] or "").strip().lower() not in useless:
                has_value += 1
                break
    print("%-24s %-6s %-8s 有效值 %d/%d" % (name, imp, "%d/%d" % (c, n), has_value, n))

print()
print("全部属性名（%d 种）：" % len(names))
print("  " + " ｜ ".join("%s(%d)" % (k, v) for k, v in names.most_common()))

# ---------- 2. 类目 / 其它刊登要素 ----------
print()
print("=" * 78)
print("② 其它刊登要素")
print("=" * 78)
leaf = Counter()
for it in items:
    for c in it.get("leaf_category_ids") or []:
        leaf[c] += 1
print("末级类目 ID 分布: %s" % leaf.most_common())
print("类目名（详情页面包屑末级）: %s"
      % [it.get("leaf_category_name") for it in spec_items if it.get("leaf_category_name")][:8])
print("有 category_path 的条数: %d" % sum(1 for it in items if it.get("category_path")))
print("has_secondary_category（分类目录2）: %s"
      % [it["position"] for it in items if it.get("has_secondary_category")])
print("图片: 采集字段里没有图片 URL → %s"
      % ("缺" if "image" not in (items[0].keys()) else "有"))
print("描述文本: 采集字段里没有 description → 缺")
print()
print("item_url 可点进详情页的比例: %d/%d"
      % (sum(1 for it in items if it.get("item_url")), len(items)))

# ---------- 3. 标题/属性能不能凑出必填项 ----------
print()
print("=" * 78)
print("③ 若不走详情页，必填项能否从标题+搜索页补出")
print("=" * 78)
brands = detect_brands(titles)
hit_brand = sum(1 for t in titles if {w for w in tokenize(t)} & brands)
print("标题里能识别出品牌词的条数: %d/%d（其余 = Unbranded/白牌）" % (hit_brand, len(items)))
for kw, label in (("bluetooth", "Connectivity"), ("in-ear", "Type/Form Factor"),
                  ("earbud", "Type")):
    c = sum(1 for t in titles if kw in t.lower())
    print("标题含 '%s' → 可推断 %s: %d/%d" % (kw, label, c, len(items)))
print("Model / EAN / MPN / Colour: 标题里通常没有 → 只能详情页")
