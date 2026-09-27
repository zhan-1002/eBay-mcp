# -*- coding: utf-8 -*-
"""统计 eBay API 实际请求量：单次采集的构成 + 至今累计（临时诊断脚本）。

数据来源：共享盘 keyword_research\\日志\\*.log 里每次运行打印的
"API 调用统计: {'search': n, 'getItem': m, 'token': t}"
"""
import glob
import io
import json
import os
import re
from collections import Counter

LOGS = r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\日志\*.log"
PAT = re.compile(r"API 调用统计: (\{[^}]*\})")

rows = []
for p in sorted(glob.glob(LOGS)):
    txt = io.open(p, encoding="utf-8", errors="replace").read()
    # 一份日志里可能有多段（一次跑多个组合），逐段累加
    for m in PAT.finditer(txt):
        d = json.loads(m.group(1).replace("'", '"'))
        rows.append((os.path.basename(p), d))

print("共享盘日志里的采集段数: %d" % len(rows))
print()
print("%-40s %8s %8s %6s" % ("日志", "search", "getItem", "token"))
tot = Counter()
for name, d in rows:
    print("%-40s %8s %8s %6s" % (name[:40], d.get("search", 0), d.get("getItem", 0),
                                 d.get("token", 0)))
    tot.update(d)
print("-" * 66)
print("%-40s %8d %8d %6d" % ("合计", tot["search"], tot["getItem"], tot["token"]))
billable = tot["search"] + tot["getItem"]
print()
print("eBay 侧计费请求合计（search + getItem）: %d" % billable)
print("token 请求 %d 次（走 OAuth 端点，不计入 Browse API 调用配额）" % tot["token"])
if rows:
    n = len(rows)
    print()
    print("单次组合平均: search %.2f ｜ getItem %.1f ｜ 合计 %.1f 次请求"
          % (tot["search"] / n, tot["getItem"] / n, billable / n))

print()
print("按天推算（每个「关键词 × 站点」组合 = 1 次 search + 200 次 getItem = 201 次）：")
for combos in (1, 5, 10, 20, 25, 30, 50, 100):
    print("   %3d 组合/天 → %6d 次请求/天" % (combos, combos * 201))
