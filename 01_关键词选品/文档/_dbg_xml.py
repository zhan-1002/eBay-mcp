# -*- coding: utf-8 -*-
"""拆 xlsx 看真实 XML：确认"品牌壁垒/价格分析"里的数据行到哪去了。"""
import glob
import os
import re
import zipfile

OUT = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出"
p = sorted(glob.glob(os.path.join(OUT, "json_uk_wireless_earbuds_*.xlsx")))[-1]
print("文件: %s" % os.path.basename(p))
z = zipfile.ZipFile(p)

wb = z.read("xl/workbook.xml").decode("utf-8")
rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
rel_map = {}
for m in re.finditer(r"<Relationship\b[^>]*>", rels):
    tag = m.group(0)
    idm = re.search(r'Id="([^"]+)"', tag)
    tm = re.search(r'Target="([^"]+)"', tag)
    if idm and tm:
        rel_map[idm.group(1)] = tm.group(1)
print("rels 映射条数: %d" % len(rel_map))
sheets = [(m.group(1), m.group(2)) for m in
          re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb)]
print("workbook 里的 sheet 顺序: %s" % [s[0] for s in sheets])

CELL = re.compile(r'<c r="([A-Z]+\d+)"([^>]*)>(.*?)</c>|<c r="([A-Z]+\d+)"([^>]*)/>', re.S)
VAL = re.compile(r'<v>([^<]*)</v>|<t[^>]*>([^<]*)</t>')


def cells_of(xml):
    rows = {}
    for m in re.finditer(r'<row[^>]*r="(\d+)"[^>]*>(.*?)</row>', xml, re.S):
        rnum, body = int(m.group(1)), m.group(2)
        vals = []
        for cm in CELL.finditer(body):
            ref = cm.group(1) or cm.group(4)
            inner = cm.group(3) or ""
            vm = VAL.search(inner or "")
            vals.append((ref, (vm.group(1) or vm.group(2)) if vm else ""))
        rows[rnum] = vals
    return rows


for name, rid in sheets:
    if name not in ("品牌壁垒", "价格分析", "关键词与标题"):
        continue
    tgt = rel_map.get(rid)
    if not tgt:
        print("\n[跳过] %s -> %s 不在 rels 映射里" % (name, rid))
        continue
    tgt = tgt.lstrip("/")
    if not tgt.startswith("xl/"):
        tgt = "xl/" + tgt
    xml = z.read(tgt).decode("utf-8")
    rows = cells_of(xml)
    print()
    print("=== %s (%s) 共 %d 行 ===" % (name, tgt, len(rows)))
    for rnum in sorted(rows)[:10]:
        print("  行%-3d %s" % (rnum, rows[rnum][:8]))
