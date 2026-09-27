# -*- coding: utf-8 -*-
"""统计本项目实际消耗的 DeepSeek token（临时诊断脚本，不联网）。

数据来源：输出目录里每份 xxx.json 的 report.llm_titles.meta.usage
（run_keyword_research 每次跑完都会把它写进结果，所以这是**真实用量**，不是估算）。
"""
import glob
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出"))

rows = []
for p in sorted(glob.glob(os.path.join(OUT, "*.json"))):
    try:
        with io.open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        continue
    info = d.get("llm_titles") or {}
    meta = info.get("meta") or {}
    usage = meta.get("usage") or {}
    if not usage:
        continue
    titles = (d.get("market") or {}).get("target_titles") or []
    rows.append({
        "file": os.path.basename(p),
        "rounds": meta.get("attempts"),
        "pool": meta.get("pool_size"),
        "prompt": usage.get("prompt_tokens") or 0,
        "completion": usage.get("completion_tokens") or 0,
        "total": usage.get("total_tokens") or 0,
        "titles": len(titles),
    })

print("=" * 92)
print("%-46s %5s %6s %8s %8s %8s" % ("文件", "轮数", "候选池", "输入", "输出", "合计"))
print("-" * 92)
for r in rows:
    print("%-46s %5s %6s %8d %8d %8d"
          % (r["file"][:46], r["rounds"], r["pool"], r["prompt"], r["completion"], r["total"]))

tp = sum(r["prompt"] for r in rows)
tc = sum(r["completion"] for r in rows)
tt = sum(r["total"] for r in rows)
print("-" * 92)
print("共 %d 次带 LLM 的运行 ｜ 输入 %d ｜ 输出 %d ｜ 合计 %d tokens"
      % (len(rows), tp, tc, tt))
if rows:
    print("单次平均：输入 %d ｜ 输出 %d ｜ 合计 %d tokens"
          % (tp / len(rows), tc / len(rows), tt / len(rows)))
print("=" * 92)

# 单价场景（元 / 百万 tokens）
scenarios = [
    ("缓存命中0.02 / 未命中1 / 输出3", 1.0, 0.02, 3.0),
    ("缓存命中0.2 / 未命中2 / 输出3", 2.0, 0.2, 3.0),
    ("缓存命中0.5 / 未命中2 / 输出8", 2.0, 0.5, 8.0),
]
print("按不同单价算（元）：")
for name, miss, hit, out in scenarios:
    per_run = (tp / len(rows) / 1e6 * miss) + (tc / len(rows) / 1e6 * out)
    total = (tp / 1e6 * miss) + (tc / 1e6 * out)
    hit_run = (tp / len(rows) / 1e6 * hit) + (tc / len(rows) / 1e6 * out)
    print("  %-30s 单次 ¥%.5f（全程缓存命中 ¥%.5f）｜ 累计 ¥%.4f"
          % (name, per_run, hit_run, total))
