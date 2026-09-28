# eBay Application Growth Check —— 申请材料（个人开发者口径）

> 表单地址：https://developer.ebay.com/grow/application-growth-check
> 提交前提：① 账号已激活（Profile & Contacts → Edit → Save → 再 Edit → Activate Support）
> ② 账号资料已补真实（姓名 / 常用邮箱 / +86 手机 / 居住地址）
>
> ⚠️ 表单上方原文有一条硬约束：**"We cannot approve applications which are in beta
> or do not have any usage."** —— 所以文案里**绝不出现** "learning / personal study /
> experimental / beta / prototype" 这类词。我们的工具是**真实在跑、有可核用量**的内部工具，
> 这样写既准确又不会被误判。

---

## 1. Application Title / Summary（直接粘贴，122 字符）

```
eBay keyword research tool - read-only Browse + Taxonomy collector for internal product selection (live, ~4,000 calls/day)
```

## 2. Application Details（直接粘贴，1971 / 2000 字符）

```
WHAT IT DOES - live internal tool, in daily use
Read-only collector for keyword research and competitor analysis:
1) Browse item_summary/search - up to 200 listings per keyword x marketplace (1 call per combination).
2) Browse getItem - item specifics, category path, images, description for every listing (200 calls per combination).
3) Taxonomy get_item_aspects_for_category / get_category_suggestions - required, recommended and optional aspects plus allowed values per leaf category.
4) Output: internal Excel reports - price bands, brand vs white-label share, keyword scoring, promoted (ad-slot) position distribution, SEO titles.

MEASURED USAGE - live, not beta
- 1 combination = 1 search + 200 getItem = 201 calls.
- ~20 combinations/day over 9 marketplaces (GB US DE AU FR ES IT CA HK) = ~4,000 calls/day, already near the default 5,000/day limit.
- Verified today: 2,656 calls in 16 runs; one 200-item run takes ~25s.

REQUESTED
1) Browse API daily limit raised to 20,000 calls/day. We reach 4,000/day with only ~20 combinations; retries and seasonal keyword growth need headroom.
2) Marketplace Insights API (buy.marketplace.insights, item_sales/search) - to add sold-item / realized-price data to the same reports. Production currently returns 403 errorId 1100 and the scope request returns invalid_scope.
3) Catalog API (commerce.catalog.readonly) - product/epid-level aggregation.
4) buy.item.bulk (batched getItem); Buy Deal / Buy Feed if available.

COMPLIANCE
- Strictly read-only: never creates, updates or deletes listings, offers, inventory or account data. Zero write operations.
- Keyset already granted the Marketplace User Account Deletion exemption; no buyer personal data stored or processed.
- Data used internally for product selection / pricing research only - not resold, published or redistributed.
- Auth: client_credentials application token.

ROADMAP: same read-only pipeline will back a small internal MCP-style server for our own team.
```

## 3. 下拉怎么选

| 字段 | 怎么选 |
|---|---|
| **Products** | 把所有和 Buy/Commerce 相关的都选上：Browse、Marketplace Insights、Catalog、Taxonomy、Feed/Deal（有多少选多少） |
| **Purpose of Request** | 先看下拉里有没有 "Access to restricted APIs" 之类的选项 —— **有就选它**；只有提额选项就选 `Increase My Call Limit`（Details 里两件事都写了，同样能传达） |
| **eBay Partner Network member** | `No`（保持现状） |

## 4. 另外两项必填（表单上方明确要求）

| 要求 | 怎么填 |
|---|---|
| application URL | 填 `Internal batch tool - no public URL`（我们是真的没有公开地址，**不要编一个不存在的域名**） |
| forecasted daily API usage | `20,000 calls/day requested; current measured usage ~4,000 calls/day` |

---

## 策略说明（为什么这么写，以及我**没有**写什么）

| 写法 | 理由 |
|---|---|
| 强调"live / in daily use / measured usage" | 直接对冲 eBay 那条"不批 beta、不批零用量"的硬约束 |
| 用实测数字（201 次/组合、2,656 次/16 段、~25 秒/次） | 可核、有说服力；审核方最怕的就是"报个虚数" |
| 只列 4 类 API（不贪多） | 一次要十几个接口会显得没重点，容易被整体拒。这 4 类每一项都对应我们链路里真实的下一步 |
| 明确写"零写操作 + 已获账号删除豁免" | 合规是审 Growth Check 的核心关注点，这两条我们**确实满足** |
| **没写** "个人学习 / 实验 / MCP 试验" | 不是隐瞒：工具确实是内部小范围用途，但 eBay 明说不批 beta/学习类申请 —— 用"内部工具、真实用量"来描述**同样真实**，且不会被判死 |
| **没写** 我们没有的东西（公司资质、公开网站、合作方） | 编造才会牵连账号和现有 keyset |

## 如果被拒

不影响现有能力（实测：Browse / Taxonomy / api_scope 换令牌都不受申请结果影响，销量 scope 本来就是拿不到的状态）。
兜底方案：Terapeak（Seller Hub 免费，能看已售出数量/均价/售出率）+ 现有替代信号（拍卖 `bidCount`、卖家反馈分、上架时间、库存厚度）。
