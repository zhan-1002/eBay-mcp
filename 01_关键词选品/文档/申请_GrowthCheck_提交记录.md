# Application Growth Check 提交记录

## 受理信息

| 项 | 值 |
|---|---|
| **受理号（follow up 用这个）** | **`260922-000031`** |
| 提交日期 | 2026-09-22（星期二） |
| 提交渠道 | Developer Technical Support → **Application Growth Check** 标签 |
| 承诺回复时限 | **1~2 个工作日**（预计 2026-09-23 ~ 09-24） |
| 查询 / 补充入口 | 同一页面的 **`My Tickets`** 标签 → 点 subject 打开并更新 |
| Application ID | `-BETA-PRD-f82b86fbd-f4f4c153`（生产 keyset） |
| eBay Partner Network member | No |

## 提交了什么

| 字段 | 内容 |
|---|---|
| Application Title / Summary | `Read-only eBay market-research tool (Browse + Taxonomy, live) - Marketplace Insights / sold-data access required` |
| Application Details | 短版 1643 字符（14 行）—— 见 `文档/申请材料_GrowthCheck.md` 的 v2 段 |
| Call Volume Estimate | 当前 ~4,000 次/天（20 组合 × 201），申请 20,000 次/天，附增长测算 |
| Attach Documents | `01_关键词选品/文档/申请附件_GrowthCheck详情.txt`（5,585 字符，5 节） |
| Products | Marketplace Insights API（+ Browse API） |
| Purpose of Request | Increase My Call Limit |

**核心诉求（用户口径：销量是必须项）**：Marketplace Insights API
（`/buy/marketplace_insights/v1_beta/item_sales/search`，scope `buy.marketplace.insights`）
—— 现在生产 403 errorId 1100、申请 scope 返回 `invalid_scope`。

## 踩过的坑（留档，避免重复）

- **"Application Details exceeds the allowed character limit"**：字段标称 limit 2000，
  我们交 1971 仍被判超。原因是**富文本编辑器给每行自动包标记，每行多 7~11 字符**，
  30 行就 +300、实际入库 2300+ 超标。→ 解决办法：**正文压到 14 行以内**，
  细节全部放进附件（附件没有 2000 上限）。

## 等待期间/被追问时可提供的证据

| 材料 | 位置 | 说明 |
|---|---|---|
| 当日 API 用量计数 | 共享盘 `keyword_research/日志/_api用量.json` | 本工具自记的按天累计（eBay 不提供额度查询接口，所以只能自记） |
| 真实产物 | 共享盘 `keyword_research/输出/*.xlsx` | 5 张子表，可证明工具真在产出 |
| 凭据体检输出 | `runtime\python.exe keyword_research\scripts\kw_menu.py check` | 证明链路健康、只读 |
| 只读证据 | 代码里没有任何 POST/PUT/DELETE 写接口调用 | 全程只读、零写操作 |

## 如果对方追问，可直接回的英文模板

> Thank you. Additional evidence for reference:
>
> - Live usage (local counter, per-run): 2,656 API calls across 16 collection runs on
>   2026-09-15; each run = 1 item_summary/search + 200 getItem (201 calls per
>   keyword x marketplace combination).
> - The tool is an internal batch process launched from a network share; it has no
>   public URL. Output is internal Excel workbooks (5 sheets each) used for product
>   selection and pricing research.
> - The application is strictly read-only: there is no code path that creates,
>   updates or deletes listings, offers, inventory or account data, and no write
>   scopes are requested.
> - Our keyset has already been granted the eBay Marketplace User Account Deletion
>   exemption.
>
> Our hard requirement is the Marketplace Insights API
> (/buy/marketplace_insights/v1_beta/item_sales/search) for sold-item and
> realized-price data. Please let us know if any further detail is required.

## 状态跟踪

| 日期 | 事件 |
|---|---|
| 2026-09-22 15:13 | 已提交（受理号 `260922-000031`） |
| 2026-09-22 23:43 | **eBay 回复：拒绝**（Support: Suraj Patel） |
| 2026-09-22 | 实测核对：其他诉求也都没批（见下） |

## 结果（2026-09-22 eBay 回复原文要点）

> "Thank you for your interest in accessing eBay's Marketplace Insights API. We have reviewed
> your request with the eBay business unit, and unfortunately, **we are unable to grant access
> at this time**. The Marketplace Insights API is protected by specific OAuth scopes and requires
> approval of business use cases following eBay's internal processes. **Access to this API is
> highly limited and generally reserved for eBay's approved partners only.** ...
> our team is here to assist with any questions or **alternative options** that might fit your
> use case. ... This ticket is hereby closed."

**性质判断：这是政策门槛（仅限 approved partners），不是材料质量问题** ——
所以**重申同一件事没有意义**。10 天 reopen 窗口应该用来**问新问题**，而不是申辩。

### 实测核对：其他诉求的结果

| 诉求 | 结果 |
|---|---|
| Marketplace Insights（销量） | ❌ 明确拒绝 |
| Browse 每日额度 → 20,000 | ❓ 回复未提；**接口无法查询**（eBay 不返额度信息、也无公开查询接口），只能去后台看 |
| Catalog API（commerce.catalog.readonly） | ❌ `invalid_scope` |
| buy.item.bulk | ❌ `invalid_scope` |
| Buy Feed / Buy Deal | ❌ `invalid_scope` |

**结论：本次申请没有带来任何权限变化**；现有 Browse + Taxonomy 能力不变
（实测 `api_scope` 换令牌、搜索、getItem、Taxonomy 全部 HTTP 200）。

## 待发的追问草稿（回邮件，必须写在标记之间）

> ⚠️ 已被下面 **「修订后的追问邮件（v2）」** 取代（v2 加入了 Terapeak API 的关键问法）——
> 直接用 v2，本段仅作历史留档。

## 销量（必须项）的落地路径

| 路径 | 可行性 | 说明 |
|---|---|---|
| Marketplace Insights API | ❌ 当前不可行 | 仅限 approved partners，个人开发者够不着 |
| 成为 approved partner / EPN | ❌ **形态不符** | 见下（Buy API Program 的定位与我们的用途不同） |
| **Terapeak**（Seller Hub → Product research） | ✅ **现在可用（官方给卖家的答案）** | 免费；3 年销售数据 |
| 现有替代信号（bidCount / 卖家反馈 / 上架时间 / 库存） | ✅ 已实测可用 | 零额外请求；作为"热度"近似指标先顶上 |

### Terapeak 能看到的字段（官方原文，2026-09-22 抓取）

出处：https://export.ebay.com/en/marketing/ebay-services-and-tools-help-seller/terapeak/

> "Product research gives you access to the **last 3 years** of eBay sales data for millions of
> items, including: Sales trends · **Average sales price** · **Sold price range** · Average
> shipping costs and the number of listings offering free shipping · **Sell through rate**
> (for searches of items sold 90 days ago or less) · **Total number of sellers who have sold
> that item** · The selling format in which items are sold"

入口：Seller Hub → **Product research**（免费）。另支持"items sold and at what prices over
time"的可视化，以及"compare your listings with top-performing competitors"。

### EPN / Buy API Program 的真实定位（协议原文挖出来的）

出处：https://partnernetwork.ebay.fr/page/network-agreement（EPN 网络协议）

> "**eBay's Buy API Program**: An approved EPN Program that permits **Affiliates who have
> entered into an agreement with eBay**, or an EPN approved third party, to **display and
> facilitate the purchase of products through eBay's API**."
>
> "...participating in eBay's Buy API Program in exchange for **a percentage of GMB**
> (Gross Merchandise Bought) associated with an end user's purchase of products or services
> through your implementation of eBay's Buy API Program."
>
> "EPN may in its sole discretion **reject your application** and terminate the Agreement for
> any reason without any compensation to you."

**关键判断：Buy API Program 是"面向终端用户展示商品并促成购买、按成交额拿佣金"的联盟营销
（affiliate）合作**。我们的工具是**内部选品调研**，既不给 eBay 引流成交、也不面向终端用户
—— **形态不符**。为了拿 API 去注册 EPN 而不真做推广，属于申报用途不符，有账号风险
（与前面讨论的合规红线一致）。

**结论：改"非个人身份"不解决这个问题** —— 门槛是"approved partner"，不是账号类型；
企业主体只是签约的前提之一，业务形态不符照样拿不到。

## 追问邮件（中间版本，已被 v2 取代）

> ⚠️ 见下面 **「修订后的追问邮件（v2）」** —— 直接用 v2。本段留档，说明思路演进。

### 重要线索：2021 年 eBay 曾发布过「Terapeak 产品调研 API」

来源：eBay Connect 2021 大中华区开发者大会（极客公园报道
https://www.geekpark.net/news/286803 ；官方 PPT
https://www.ebay.cn/uploadfile/pdf/eBayConnectGC2021-TerapeakAPI.pdf ）

> "eBay 新推出的 **Terapeak 产品调研 API** 可以帮助卖家便捷找出**一年内售出刊登**的采购先机、
> **价格趋势**、**销售率**和其他关键销售指标。此外，把功能加入到 **ERP** 后，有关的数据也可以
> 跟卖家其他的系统做对接、交换数据。"

PPT 本体已抓到（979KB），元数据确认是《eBayConnectGC2021-TerapeakAPI.pptx》（作者 cheiw），
但正文是 CID 编码，**解不出中文内容**（不装懂）。

**但它现在是否还存在？实测：看不到**

```
scope  api_scope/sell.research              🔒 无效
scope  api_scope/sell.terapeak              🔒 无效
scope  api_scope/commerce.terapeak.readonly 🔒 无效
路径   /commerce/terapeak/v1/research        HTTP 404
路径   /sell/research/v1/terapeak            HTTP 404
路径   /commerce/research/v1/product_research HTTP 404
路径   /buy/marketplace_insights/.../item_sales/search  HTTP 403（已知）
```

**推断（标注为推断）**：2021 那个 Terapeak 产品调研 API 极可能就是现在 **Marketplace Insights**
的前身/同一数据源；访问模型从"面向卖家的 ERP 集成"**收窄**成"仅限 approved partners"。
这也解释了 eBay 为什么让我们"去用 Terapeak"（UI），而不给 API。

**⚠️ 但有一个没被排除的可能**：上面的探测都用 **application token**（client_credentials）。
如果那个 Terapeak API 是**卖家授权（user token）**才能调的 Sell 类接口，
用 app token 探测**根本看不到它** —— 所以"探测不到"不能证明"不存在"。

**需要 eBay 明确回答**（已并入下面邮件草稿第 3 问）。

## 修订后的追问邮件（v2：加入 Terapeak API 的问题）

> Hello,
>
> Thank you for the review and the clear explanation regarding the Marketplace Insights API.
>
> Could you help with three short clarifications on this same ticket, so that we proceed
> correctly instead of resubmitting the same request?
>
> 1) The other items in my Growth Check request were not addressed in your reply:
>    - raising the Browse API daily limit from the default to 20,000 calls/day
>    - Catalog API (commerce.catalog.readonly)
>    - buy.item.bulk for batched getItem
>    Could you confirm the status of each, and if not approved, what conditions would need to be met?
>
> 2) At eBay Connect 2021 (Greater China Developer Conference) eBay announced a
>    "Terapeak Product Research API" for sellers, described as giving sold listings within a
>    year, price trends and sell-through metrics, and as being designed for ERP integration.
>    Is that API still available as a separate API today? If yes, what scope and endpoint does
>    it use, and does it require user authorization (a user access token) rather than an
>    application token? Our scope probes with an application token returned invalid_scope for
>    sell.research / sell.terapeak / commerce.terapeak.readonly, and the paths we tried returned
>    404 — but we understand a user-token-only API would be invisible to those probes.
>
> 3) If that API has been replaced by the Marketplace Insights API, could you confirm the
>    recommended channel for an eBay seller (not a partner) to obtain sold-item and
>    sell-through data? Is it Terapeak Product Research in Seller Hub?
>
> We are an eBay seller using this data for our own sourcing and pricing decisions; the tool is
> internal-only and does not display eBay content to end users. We would simply like to use the
> correct channel.
>
> Best regards,

## 修订后的追问邮件（v3 最终版：用 eBay 自己的额度数据提问）

**关键升级**：我们已能读到本 app 的官方额度表
（`GET /developer/analytics/v1_beta/rate_limit/`，返回 140 条资源），
其中赫然列着 **`sell.research.product_insight`（Sell / ProductResearch V1，额度 5000/天）**
—— 但公开文档里找不到它的 scope 和端点。**用对方自己的数据提问，最难被套话糊过去。**

> Hello,
>
> Thank you for the review and the clear explanation regarding the Marketplace Insights API.
>
> Before deciding on alternatives, could you clarify three points on this same ticket?
>
> 1) Our application's own rate-limit response
>    (`GET /developer/analytics/v1_beta/rate_limit/`) lists a resource named
>    **`sell.research.product_insight`** under **Sell / ProductResearch V1**, with a limit of
>    **5,000 calls/day and zero usage so far**.
>
>    However, we cannot find this API anywhere in your public material:
>      - searching "Product Research" in the eBay developer documentation returns no matching API;
>      - there is no public OpenAPI specification for it;
>      - every endpoint path we tried under /sell/research/v1/... returns 404.
>
>    Could you tell us the exact endpoint, the required OAuth scope, and whether it requires
>    user authorization (a user access token)? Since the quota is already provisioned to our
>    application, we assume access exists and that we are only missing the documentation.
>
> 2) The other items in my Growth Check request were not addressed in your reply:
>    - raising the Browse API daily limit from the default to 20,000 calls/day
>    - Catalog API (commerce.catalog.readonly)
>    - buy.item.bulk for batched getItem
>    Our own rate-limit response shows quota for `commerce.catalog` (10,000/day) and
>    `buy.browse.item.bulk` (5,000/day), yet both calls return 403 errorId 1100. Could you
>    confirm the status and, if not approved, the conditions required?
>
> 3) If the Product Research API above is not available to us, could you confirm whether
>    **Terapeak Product Research in Seller Hub** is the recommended channel for an eBay seller
>    to obtain sold-item and sell-through data?
>
> Our tool is an internal, read-only research process for our own sourcing and pricing
> decisions; it does not display eBay content to end users and does not drive traffic or
> transactions, so we understand it may not fit the affiliate use case. We would simply like to
> use the correct channel.
>
> Best regards,

## 待用户确认的一件小事（可能直接有答案）

Growth Check 表单的 **Products 下拉**里，请找找有没有这些名字，并告诉我：

- **Terapeak**
- **Marketplace Insights**
- **Research**
- 另外：截图里出现过 **`MIP`** 这个选项 —— 它展开是什么？（不确定指什么）

**如果下拉里出现 `Terapeak`**，说明它至今仍作为一个"可申请的产品"存在 —— 那我们就该申请
**那个（面向卖家）**，而不是 Marketplace Insights（面向合作伙伴）。

## 🔚 终局判断：销量 API 的两条路都走完了（2026-09-22 靠下拉清单确认）

用户提供的 **Growth Check「Products」下拉**完整清单（决定性证据）：

```
Buy APIs      : Offer / Marketplace Insights / Deal / Marketing / Feed / Browse / Order
Developer APIs: Analytics / Key Management
Post Order    : Cancellation / Case Management / Inquiry / Return
Sell APIs     : Recommendation / Compliance / Logistics / Finances(Alpha) / Negotiation /
                Sell Feed / Marketing Ads / Stores / Inventory Mapping / Account /
                Inventory / Fulfillment / Marketing Promotion / Analytics / Metadata
```

**整个下拉里没有 `Product Research`。**

| 销量路径 | 在可申请清单里？ | 结果 |
|---|---|---|
| **Marketplace Insights API** | ✅ 在 | ❌ 已被 eBay 书面拒绝（仅 approved partners） |
| **Product Research API** | ❌ **不在** | ❓ **连申请入口都没有**（尽管额度表里有 5000/天） |
| Terapeak 网页 | — | ✅ 能用，但只有 UI、无 API |

### 这个矛盾的解释

```
rate_limit 额度表      = API 目录（列配额）  → 有 sell.research.product_insight
Growth Check 产品下拉   = 可申请的产品        → 没有 Product Research
```

⇒ **它是真实 API，但不是提供给第三方应用申请的产品** —— 极可能就是
**Seller Hub UI 自己调用的内部接口**（Terapeak 页面在用，配额记在我们 app 的桶里）。

与旁证吻合：第三方项目 `ebay-terapeak-mcp` 爬的私有端点正是 **Seller Hub 网页端的
`/sh/research/api/search`** —— `sell.research.product_insight` 很可能就是它的配额桶。

### 结论

**官方 API 拿"真·销量"这条路，对我们已经走完**：可申请的那条被拒、不可申请的那条无入口。
v3 邮件仍可发出（拿官方定论，避免以后再纠结），但不应再指望它。

**精力应转到能落地的方案**：Feedback 评价聚合 + 自家订单校准留评率 + Terapeak 人工/扩展。

## 若被拒的备选（销量既然是必须项，先想好）

1. **Terapeak 顶住**：人工查核心关键词（已售出数量 / 平均成交价 / 售出率 / 有多少卖家卖过），
   结论并进现有报表做校准。先确认 Terapeak 页面**有没有导出功能**，有就做半自动化
2. **走 My Tickets 追问**（用上面的 v2 草稿）
3. 把现有替代信号（`bidCount` / `feedbackScore` / `itemCreationDate` / 库存 / 议价）
   正式接进报表，作为销量的近似指标（零额外请求、可规模化）
