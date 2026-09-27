# -*- coding: utf-8 -*-
"""把 eBay API 实测结论追加到接口探查记录。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.normpath(os.path.join(HERE, "..", "文档", "接口探查记录_20260914.md"))

SECTION = """

---

# 附：eBay 官方 Browse API 实测（2026-09-14，沙箱 User Token）

> 凭据：开发者后台的 **User Token**（`token.local.txt`，沙箱），非 client_credentials。
> 沙箱数据是 eBay 测试数据（每个查询只 1~3 条），**验证的是机制与字段，不代表生产数据量**。

## A. 能拿到什么（实测）

### A1. `GET /buy/browse/v1/item_summary/search` —— 搜索结果

返回字段（实测逐项）：
```
itemId / legacyItemId / title / leafCategoryIds=["112529"]
categories=[{112529,Headphones},{293,...}]
price={value,currency} / condition / conditionId
seller / shippingOptions / buyingOptions
itemWebUrl / itemLocation={city,postalCode,country}
itemCreationDate / itemOriginDate / priorityListing
listingMarketplaceId / distanceFromPickupLocation
```

**★ 搜索结果里没有 item specifics**（无 `localizedAspects` / 无 aspect 类字段）—— 与 Soldeazy 侧结论一致，**必须逐条取详情**。

### A2. `GET /buy/browse/v1/item/{itemId}` —— 详情（关键）

返回 33 个键，其中对我们最有用的：
```
localizedAspects   ← item specifics（刊登表单必填项）
categoryPath / categoryIdPath / categoryId
image / description / brand / color
returnTerms / taxes / shippingOptions / estimatedAvailabilities
unitPrice / lotSize / paymentMethods / immediatePay
```

实测 `localizedAspects`（1 条样本）：
```
Brand=Unbranded  Connectivity=Bluetooth  Type=In-Ear
Colour=Black     Model=2026 Pro          Unit Quantity=1  Unit Type=Unit
```

→ **Brand / Connectivity / Type / Colour / Model 正好是刊登表单的 5 个「必须」项**，
说明这条路径能直接满足补数需求，且**不需要写任何生产账号**。

### A3. `GET /buy/marketplace_insights/v1_beta/item_sales/search` —— 售出数据

实测 **HTTP 200**（`{"limit":1,"offset":0,"total":0}`）→ **该 app 有此权限**；
沙箱 `total=0` 属正常（无成交数据）。**生产环境需实测确认有数据**。

## B. 容量与配额（实测）

| 项 | 实测结论 |
|---|---|
| 单页条数上限 | **`limit` 最大 200**（`limit=300` → HTTP 400，errorId 12006：`should be between 1 and 200`） |
| 翻页 | **`offset` 必须是 `limit` 的整数倍**（`offset=1/2` 配 `limit=5` → HTTP 400，errorId 12515） |
| 拿 120 条 | `limit=200` **一页即可**（120 < 200），翻页仅在 >200 时才有意义 |
| 调用消耗（一次完整跑） | **1 次 search + N 次 getItem**；120 条 = **1 + 120 = 121 次调用** |
| 多站点 | `X-EBAY-C-MARKETPLACE-ID` + `X-EBAY-C-ENDUSERCTX` **生效**：GB/US/DE 各自返回对应 `listingMarketplaceId` 与 `itemLocation.country`，且站点匹配 |

## C. 与现有两段方案的对比

| 维度 | 紫鸟 + Soldeazy | 官方 API |
|---|---|---|
| **配送地** | `set_ship_to` 至今**设不成功**，只靠搜索 URL 的 `_stpos/_fcid` 兜底 | **header 明确指定**，实测 GB/US/DE 均生效 |
| **风控** | eBay 有挑战页/断连风险，风险落在登录态账号 | 走 API 配额，无浏览器风控 |
| **写生产账号** | Soldeazy `listing_spy` 会在生产账号**创建数据表**（已封存 11 条） | **零写操作** |
| **item specifics** | 有，但受"保护/内容回落"影响（`res_flag=0` 也可能是别的商品） | `getItem.localizedAspects`，字段结构化、无需判定真伪 |
| **售出数据** | 无 | Marketplace Insights（权限已通） |
| **调用成本** | 无显式配额，但有账号风险 | 121 次/关键词/站点，受每日额度约束 |

## D. 待生产环境验证

1. **生产 token 下 `getItem` 的 localizedAspects 覆盖率**（沙箱只有 1 条样本，覆盖率要真实数据才能判）
2. **真实数据量与翻页**：`total` > 200 时的 `offset=200,400...` 翻页
3. **每日额度**：121 次 × 关键词数 × 站点数 是否在配额内（需在开发者后台看调用统计）
4. **Marketplace Insights 生产数据**：是否真返回成交记录、字段有哪些、能否满足"sold item"需求
5. client_credentials 与 User Token 两条路径的取舍（前者无需授权但同样能搜公共数据）
"""

old = open(DOC, encoding="utf-8").read()
if "eBay 官方 Browse API 实测" in old:
    print("已追加过，跳过")
else:
    with open(DOC, "a", encoding="utf-8", newline="\n") as f:
        f.write(SECTION)
    print("已追加到 %s" % os.path.basename(DOC))
    print("当前文档长度: %d 字符" % len(open(DOC, encoding="utf-8").read()))
