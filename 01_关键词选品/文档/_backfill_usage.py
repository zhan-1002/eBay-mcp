# -*- coding: utf-8 -*-
"""把共享盘日志里已发生的 API 调用回填进当日用量文件。

计数功能是今天才加的，之前跑的（开发 + 验收）没被记进去，
从日志里回算出来补上，免得今日数字少算。
"""
import glob
import io
import json
import os
import re

LOG_DIR = r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\日志"
USAGE = os.path.join(LOG_DIR, "_api用量.json")
PAT = re.compile(r"API 调用统计: (\{[^}]*\})")

tot = {"search": 0, "getItem": 0, "token": 0, "其他": 0}
days = {}
for p in sorted(glob.glob(os.path.join(LOG_DIR, "*.log"))):
    txt = io.open(p, encoding="utf-8", errors="replace").read()
    # 日志文件名里带日期：关键词选品_YYYYmmdd_HHMMSS.log
    m = re.search(r"_(\d{8})_", os.path.basename(p))
    day = "%s-%s-%s" % (m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:]) if m else "unknown"
    for mm in PAT.finditer(txt):
        d = json.loads(mm.group(1).replace("'", '"'))
        cur = days.setdefault(day, {"search": 0, "getItem": 0, "token": 0, "其他": 0,
                                    "运行段数": 0})
        for k in tot:
            cur[k] = cur.get(k, 0) + (d.get(k) or 0)
        cur["运行段数"] += 1

print("从日志回算：")
for day, cur in sorted(days.items()):
    cur["计费请求"] = cur["search"] + cur["getItem"] + cur["其他"]
    cur["更新时间"] = "（由日志回填）"
    print("   %s  search=%d getItem=%d token=%d 运行段数=%d → 计费请求 %d"
          % (day, cur["search"], cur["getItem"], cur["token"],
             cur["运行段数"], cur["计费请求"]))

data = {}
if os.path.isfile(USAGE):
    with io.open(USAGE, encoding="utf-8") as f:
        data = json.load(f) or {}
data.update(days)
with io.open(USAGE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("\n已写入 %s" % USAGE)
with io.open(USAGE, encoding="utf-8") as f:
    print(f.read())
