# -*- coding: utf-8 -*-
"""最终复核：5 张子表结构 + 广告位三段 + 采集明细前 8 列（临时诊断脚本）。"""
import sys
from openpyxl import load_workbook

path = sys.argv[1]
wb = load_workbook(path, data_only=True)
print("子表:", wb.sheetnames)

market = wb["市场概况与价格"]
seg_titles = [r[0] for r in market.iter_rows(values_only=True)
              if r and isinstance(r[0], str) and "、" in r[0] and r[0][0] in "一二三四五六七"]
print("市场概况段落:", seg_titles)

det = wb["采集明细"]
hdr = [c.value for c in next(det.iter_rows(min_row=1, max_row=1))]
print("采集明细列数:", len(hdr))
print("前 8 列:", hdr[:8])
print("行数:", det.max_row - 1)

for name in ("品牌壁垒", "关键词与标题", "基础统计"):
    ws = wb[name]
    print("%s: %d 行 x %d 列" % (name, ws.max_row, ws.max_column))

# 广告位一致性：明细里的广告位条数 vs 概览里的广告位条数
idx_ad = hdr.index("是否广告位")
idx_src = hdr.index("广告位标记来源")
ad_rows = [r for r in det.iter_rows(min_row=2, values_only=True) if r[idx_ad] in (True, "True", 1)]
srcs = {r[idx_src] for r in ad_rows}
print("明细广告位条数:", len(ad_rows), "｜ 标记来源:", srcs)
