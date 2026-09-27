# -*- coding: utf-8 -*-
"""按用户决定更新 02 模块 README：售出数据不在需求内。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "README.md"))
txt = open(P, encoding="utf-8").read()

add = """
## 需求范围（2026-09-15 用户确认）

- **不做「售出/最近成交（sold item）」** —— 该需求已从范围中移除。
  因此 Marketplace Insights API 的 403 权限问题**不再是缺口**，无需申请。
- 需要的是：**搜索 120 条** + **逐条取 item specifics / 类目 / 图片 / 描述**。
  这两项已由 eBay Browse API 生产环境实测 100% 覆盖（见文档附二）。

## 建议的落地形态

```
01_关键词选品 采集段  →  改用 eBay Browse API
    search(item_summary, limit=200)          1 次调用拿 120 条
    getItem(v1|xxx|0) × 120                  逐条拿 localizedAspects
    实测覆盖率 100%，121 次调用 / 2.5 分钟

紫鸟链路      →  保留作为备用（配送地弹层问题仍在）
Soldeazy 链路 →  可停用（不再需要写生产账号）
封存数据表    →  11 条按指示不删，清单见文档
```
"""

if "需求范围（2026-09-15 用户确认）" in txt:
    print("已存在该节，跳过")
else:
    txt = txt.rstrip() + "\n" + add
    with open(P, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print("已更新 %s（现 %d 字符）" % (os.path.basename(P), len(txt)))
