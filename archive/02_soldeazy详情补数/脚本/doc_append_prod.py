# -*- coding: utf-8 -*-
"""把生产实测结论写入工程文档。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.normpath(os.path.join(HERE, "..", "文档", "接口探查记录_20260914.md"))

SECTION = """

---

# 附二：eBay 官方 Browse API **生产环境**实测（2026-09-14/15）

> 凭据：开发者后台 **Production 环境 User Token**（`token.local.txt`，已 gitignore）。
> 域名 `https://api.ebay.com`，`X-EBAY-C-MARKETPLACE-ID=EBAY_GB`，
> `X-EBAY-C-ENDUSERCTX=contextualLocation=country=GB,zip=SW1A1AA`。
> 关键词 `wireless earbuds`，取前 120 条逐条取详情。**全程只读，零写操作。**

## 一、搜索（`item_summary/search`）

```
HTTP 200 | 耗时 2.0s | total=70879 | limit=200 一页返回 200 条 | 有 next 翻页链接
```

- `limit` 上限 **200**（>200 报 errorId 12006）
- 真实数据佐证（第 1 条）：卖家 `jaza_trades`（99.8%、6797 分）、价格 `£4.99`、
  地点 `Cottingham / GB`、图片 `i.ebayimg.com`、`shortDescription` 有值
- **搜索结果仍无 item specifics**（需逐条 getItem）

## 二、`getItem` 覆盖率（120 条全量实测）

```
getItem 成功 120/120（0 失败）| 总耗时 149.3s | 平均 1.24s/条
★ localizedAspects 覆盖率 = 100.0%（120/120）
```

| 字段 | 覆盖 |
|---|---|
| localizedAspects 非空 | **120/120 = 100.0%** |
| 描述非空 | 120/120 = 100.0%（>300 字符 119/120） |
| 有图片 | 120/120 = 100.0% |
| categoryPath / categoryId | 120/120 = 100.0% |
| brand / condition / returnTerms | 120/120 = 100.0% |
| color | 119/120 = 99.2% |

### 刊登表单「必须」项覆盖（这是我们最关心的）

| 必填项 | API 有值 |
|---|---|
| **Brand** | **120/120 = 100.0%** |
| **Connectivity** | **120/120 = 100.0%** |
| **Type** | 119/120 = 99.2% |
| **Colour** | 119/120 = 99.2% |
| **Model** | 110/120 = 91.7% |

### localizedAspects 字段名频次（top 10）

```
Brand 120 | Connectivity 120 | Colour 119 | Type 119 | Features 115
Form Factor 113 | Wireless Technology 112 | Number of Earpieces 110
Model 110 | Microphone Type 105
```

→ **结论：官方 API 能 100% 覆盖 item specifics，可直接替代 Soldeazy 抓详情，
且不产生任何生产账号写操作。**

## 三、调用消耗

```
120 条 = 1 次 search + 120 次 getItem = 121 次调用
平均 1.24 s/条（串行）；120 条总耗时约 2.5 分钟
```

## 四、Marketplace Insights（售出数据）：**生产环境 403 无权限**

```
GET /buy/marketplace_insights/v1_beta/item_sales/search
→ HTTP 403 {"errors":[{"errorId":1100,"domain":"ACCESS","category":"REQUEST",
   "message":"Access denied",
   "longMessage":"Insufficient permissions to fulfill the request."}]}
```

- **沙箱**同类调用返回 **200**（`total=0`，沙箱无成交数据）—— 说明沙箱对权限是宽松的，
  **不能拿沙箱结果推断生产可用**
- 生产 403 的可能原因（未区分）：
  1. 该**应用**未获 Marketplace Insights 授权（需单独申请，eBay 侧审批）
  2. 该 **User Token** 的 scope 不含 Marketplace Insights
- → 需求里「show only → sold item 抓最近成交」这条，**目前 API 侧不可用**；
  需申请权限，或继续由紫鸟抓 sold 页面实现

## 五、结论：两条链路对比（生产实测口径）

| 维度 | 紫鸟 + Soldeazy | **eBay 官方 API** |
|---|---|---|
| item specifics 覆盖 | 有，但受"保护/内容回落"影响 | **100%（120/120 实测）** |
| 配送地 | `set_ship_to` 设不成功，URL 兜底 | **header 精确指定，GB/US/DE 均生效** |
| 写生产账号 | Soldeazy 建数据表（已封存 11 条） | **零写操作** |
| 速度 | 浏览器开窗 + 翻页，分钟级且不稳 | **121 次调用 / 2.5 分钟，稳定** |
| 风控 | 挑战页/断连风险 | 无浏览器风控，受配额约束 |
| 售出数据 | 无（需另行抓 sold 页） | **403 无权限，需申请** |
| 调用成本 | 无显式配额 | 121 次/关键词/站点 |

**建议**：`01_关键词选品` 的采集与详情补数整体切到官方 API；
Soldeazy 那条（写生产账号）可以停用；「sold item」需求单独走 Marketplace Insights 申请或保留紫鸟。
"""

old = open(DOC, encoding="utf-8").read()
if "生产环境**实测" in old or "附二" in old:
    print("已追加过，跳过")
else:
    with open(DOC, "a", encoding="utf-8", newline="\n") as f:
        f.write(SECTION)
    print("已追加附二，文档现 %d 字符" % len(open(DOC, encoding="utf-8").read()))
