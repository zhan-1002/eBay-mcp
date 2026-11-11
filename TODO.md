# eBay MCP Roadmap

本文件记录可选能力。它们不进入当前 `0.1.0` 核心工具，按依赖逐步启用。

依赖标记：

- `[OFFICIAL]`：现有官方 application token 可以实现。
- `[SALES_PROVIDER]`：等待非公开销量数据 Provider 通过合规与稳定性检查。
- `[USER_OAUTH]`：需要卖家账号授权、RuName 和用户级 scopes。
- `[INFRA]`：需要持久化、调度器、Worker 或通知基础设施。

## 0. 当前基线

- [x] 官方 Browse、Taxonomy、Feedback、Translation、Rate Limits。
- [x] OAuth、重试、分页、统一错误和只读 Tool 注解。
- [x] 可插拔 `SalesHistoryProvider`，按配置选择数据源。
- [x] 购买记录 Provider：独立持久化 Profile、显式 itemId、串行采集和部分失败。
- [x] 7 个 Skill Resources 和 WorkBuddy 兼容读取。
- [x] 30 条标题机械校验。

## 1. 监控基础设施

- [ ] `[INFRA]` 定义监控任务模型：任务 ID、类型、目标、Marketplace、周期、状态和所有者。
- [ ] `[INFRA]` 使用 SQLite 起步，并预留 PostgreSQL 存储适配器。
- [ ] `[INFRA]` 增加调度器与独立 Worker；MCP 只负责管理任务，不在一次 Tool Call 内长期运行。
- [ ] `[INFRA]` 保存不可变快照、字段级 Diff、执行记录和数据来源。
- [ ] `[INFRA]` 支持立即运行、暂停、恢复、重试、回填和取消。
- [ ] `[INFRA]` 增加幂等键，避免重复建立任务或重复发送预警。
- [ ] `[INFRA]` 根据 eBay 配额自动分配运行预算并错峰调度。
- [ ] `[INFRA]` 设置数据保留期、归档、清理和数据库迁移策略。
- [ ] `[INFRA]` 增加任务健康度：连续失败、延迟、数据缺口和 Provider 状态。

### 1.1 API 凭据池、配额路由与轮换

- [ ] `[INFRA]` 将单组 eBay 凭据升级为命名凭据池，每组包含环境、App ID、Cert ID、能力和所有者。
- [ ] `[INFRA]` 凭据只引用 Secret Store 中的 ID，数据库、任务参数、日志和 MCP 响应不保存明文。
- [ ] `[OFFICIAL]` 定期调用 Developer Analytics，记录每个 Keyset 的资源级额度、已用量和重置时间。
- [ ] `[INFRA]` 路由前匹配环境、API family、scope、token 类型、Marketplace 和剩余额度。
- [ ] `[INFRA]` 支持加权轮询、最少使用和最大剩余额度三种只读请求调度策略。
- [ ] `[INFRA]` 为每个 Keyset 设置独立并发、QPS、日预算、安全余量和冷却时间。
- [ ] `[INFRA]` 同一监控任务默认粘滞到一个 Keyset，避免分页、缓存和口径不一致。
- [ ] `[INFRA]` 达到安全余量后停止分配新任务，并在合法可用的 Keyset 中选择下一组。
- [ ] `[INFRA]` 429 进入配额冷却；401/`invalid_client` 立即隔离凭据并预警，不进行无限轮换。
- [ ] `[INFRA]` 403 按 scope/entitlement 失败处理，不把轮换当成权限修复方案。
- [ ] `[INFRA]` 5xx/网络故障先按单 Keyset 重试预算处理，再执行有上限的只读故障转移。
- [ ] `[INFRA]` Refresh Token、Access Token 和 Client Credentials 必须绑定同一 Keyset，禁止交叉混用。
- [ ] `[INFRA]` 写操作默认禁止跨 Keyset 自动重试，防止请求实际成功却重复创建或修改数据。
- [ ] `[INFRA]` 所有路由、轮换、隔离、恢复和额度决策写入不含密钥的审计日志。
- [ ] `[INFRA]` 提供凭据池状态 Tool：健康度、能力、剩余额度和冷却状态，仅返回脱敏标识。
- [ ] `[INFRA]` 提供人工启用、停用、优先级调整和恢复 Tool，并要求管理员权限。
- [ ] `[INFRA]` 使用虚假 Keyset 与模拟响应测试配额耗尽、429、401、403、5xx 和并发竞争。

> 凭据池只能管理组织合法拥有并获授权的 eBay Keyset，不得通过创建或借用多账号来规避
> eBay 配额政策。额度不足时应优先减少调用、缓存、错峰调度并申请 Application Growth
> Check；轮换只用于容量规划、能力隔离和故障转移。

## 2. 竞争店铺监控

- [ ] `[OFFICIAL]` 建立竞争店铺观察列表，保存 seller ID、Marketplace 和备注。
- [ ] `[OFFICIAL]` 定期获取公开在售商品并生成店铺商品快照。
- [ ] `[OFFICIAL]` 识别新上架、下架、重新刊登和链接/Item ID 变化。
- [ ] `[OFFICIAL]` 跟踪标题、价格、运费、成色、类目和 item specifics 变化。
- [ ] `[OFFICIAL]` 跟踪图片数量、主图 URL、描述摘要和商品所在地变化。
- [ ] `[OFFICIAL]` 跟踪优惠、议价、Top Rated、库存阈值等公开字段。
- [ ] `[OFFICIAL]` 跟踪 `priorityListing` 和搜索位置，形成广告曝光代理趋势。
- [ ] `[OFFICIAL]` 分析店铺上新频率、下架频率、类目扩张和商品组合变化。
- [ ] `[OFFICIAL]` 建立重新刊登关联规则，避免把同一商品误判为全新商品。
- [ ] `[SALES_PROVIDER]` 补充公开接口无法提供的成交观察和销量时间序列。

> 竞争店铺的真实广告花费、出价、ROAS 和预算不是公开数据。只能将广告标记、
> 搜索位次和出现频率称为“广告曝光代理指标”，不得表述为实际广告投入。

## 3. 销量与趋势

- [x] `[SALES_PROVIDER]` 标准化可见成交记录：listing ID、成交价、时间范围、数量和来源。
- [x] `[SALES_PROVIDER]` 输出每条数据的覆盖范围、采集时间和完整历史标记。
- [ ] `[SALES_PROVIDER]` 计算商品、店铺和类目的销量趋势与销售速度。
- [ ] `[SALES_PROVIDER]` 分析价格变化与销量变化的时间关系。
- [ ] `[SALES_PROVIDER]` 分析上新后首单时间、生命周期和衰减趋势。
- [ ] `[SALES_PROVIDER]` 分析周期性、季节性和异常峰值。
- [ ] `[SALES_PROVIDER]` 将官方 Feedback 数据作为独立辅助信号，不冒充完整销量。
- [ ] `[SALES_PROVIDER]` Provider 数据缺失时返回 partial 与 coverage，不进行无依据补全。

## 4. 本品与竞品对比

- [ ] `[OFFICIAL]` 建立本品与一个或多个竞品的映射关系。
- [ ] `[OFFICIAL]` 比较商品价、运费和到手价。
- [ ] `[OFFICIAL]` 比较标题长度、关键词覆盖和标题结构，不自动作出选品判断。
- [ ] `[OFFICIAL]` 比较类目、必填属性、推荐属性和属性完整度。
- [ ] `[OFFICIAL]` 比较图片数量、描述完整度、成色、所在地和配送信息。
- [ ] `[OFFICIAL]` 比较卖家反馈分、好评率和反馈样本。
- [ ] `[OFFICIAL]` 输出字段级差异、证据链接和抓取时间。
- [ ] `[SALES_PROVIDER]` 增加销量、成交价和销售速度对比。
- [ ] `[USER_OAUTH]` 将自家流量、转化、广告和订单指标与公开竞品指标分栏展示。
- [ ] `[USER_OAUTH]` 自家真实广告花费和 ROAS 只从已授权 Sell API 获取。

## 5. 竞品监控任务

- [ ] `[INFRA]` 支持按 seller、item、query、category 建立监控任务。
- [ ] `[INFRA]` 支持分钟、小时、每日和自定义 Cron 周期。
- [ ] `[INFRA]` 提供任务创建、查看、暂停、恢复和删除 Tool。
- [ ] `[INFRA]` 写操作要求显式确认、审计日志和所有者校验。
- [ ] `[INFRA]` 提供最近一次结果、执行历史、下次执行时间和失败原因。
- [ ] `[INFRA]` 支持竞争店铺分组和不同优先级。
- [ ] `[INFRA]` 支持任务模板，避免重复配置相同指标。

## 6. 预警任务

- [ ] `[INFRA]` 定义规则：指标、比较方式、阈值、窗口、连续次数和严重级别。
- [ ] `[OFFICIAL]` 新商品出现、商品消失或重新刊登预警。
- [ ] `[OFFICIAL]` 价格绝对值或百分比变化预警。
- [ ] `[OFFICIAL]` 运费、配送地、类目、标题和关键属性变化预警。
- [ ] `[OFFICIAL]` 广告标记或搜索曝光代理指标突变预警。
- [ ] `[OFFICIAL]` 卖家负面/中性反馈增加预警。
- [ ] `[SALES_PROVIDER]` 销量速度、成交价和成交量异常预警。
- [ ] `[USER_OAUTH]` 自家库存、流量、转化、订单、广告花费和 ROAS 预警。
- [ ] `[INFRA]` 支持静态阈值、环比、同比、移动平均和季节性基线。
- [ ] `[INFRA]` 增加去重、冷却时间、恢复通知和升级策略，避免预警风暴。
- [ ] `[INFRA]` 支持 Webhook、飞书和邮件；渠道凭据只放私密配置。
- [ ] `[INFRA]` 每条预警包含证据快照、旧值、新值、时间和来源。

## 7. 可追加能力

- [ ] `[OFFICIAL]` 类目观察列表：新品数量、价格分布和属性变化。
- [ ] `[OFFICIAL]` 新品发布雷达：识别竞争店铺首次出现的新产品族。
- [ ] `[OFFICIAL]` 商品组合分析：按类目、价格带、品牌字段和属性聚类。
- [ ] `[OFFICIAL]` 优惠与促销变化时间线。
- [ ] `[OFFICIAL]` 物流与退货政策变化监控（仅限 API 实际可见字段）。
- [ ] `[OFFICIAL]` Listing 质量回归：本品标题、图片和必填属性被修改或缺失。
- [ ] `[INFRA]` 日报、周报和事件摘要，支持 JSON/CSV 导出。
- [ ] `[INFRA]` 时间线回放：复现任意日期的店铺或商品状态。
- [ ] `[INFRA]` 数据质量面板：来源可用性、字段覆盖率、延迟和异常值。
- [ ] `[INFRA]` 规则模拟：建立预警前先用历史快照回放误报率。
- [ ] `[INFRA]` 多租户隔离、角色权限和每用户配额。
- [ ] `[SALES_PROVIDER]` 多 Provider 交叉验证；冲突时保留各自来源，不静默合并。
- [ ] `[USER_OAUTH]` 自家账号经营看板，与公开竞品监控严格区分数据来源。

## 8. 结果 Excel

- [ ] `[OFFICIAL]` 新增 Skill `ebay-result-workbook`：根据任务类型选择模板、检查必填字段、调用导出工具，并说明每个工作表的数据来源。
- [ ] `[OFFICIAL]` 新增只读 Tool `ebay_export_workbook`：接收结构化数据和模板 ID，按模板填充并返回本地 `.xlsx` 路径。
- [ ] `[OFFICIAL]` 模板与填充逻辑分离；工具不重新计算选品、评分或销量，只写入已有结果。
- [ ] `[OFFICIAL]` 固定工作表名称、列名、列序和数据类型，缺字段留空并在“数据说明”表记录原因。
- [ ] `[OFFICIAL]` 超长文本截断到 Excel 单元格上限，并注明完整内容所在的配套 JSON。
- [ ] `[OFFICIAL]` 文件名使用“任务类型 + 关键词或目标 + Marketplace + 时间”，避免覆盖旧文件。
- [ ] `[OFFICIAL]` 导出目录可配置，默认不入库；模板本身入库，生成结果不入库。
- [ ] `[OFFICIAL]` 用固定 Fixture 校验工作表、列序、空值和超长截断，不依赖真实 eBay 响应。

### 8.1 配套 Excel 模板

- [ ] `[OFFICIAL]` `title-delivery`：30 条标题、字符数、校验结果、禁用词和数据来源。
- [ ] `[OFFICIAL]` `listing-search`：搜索条件、分页、采集明细、类目和属性。
- [ ] `[OFFICIAL]` `seller-feedback`：卖家反馈明细、分页范围和“非完整销量”口径说明。
- [ ] `[OFFICIAL]` `taxonomy-aspects`：类目建议、必填属性、推荐属性、可选属性和允许值。
- [ ] `[INFRA]` `store-monitor`：店铺快照、链接变化、字段差异和广告曝光代理指标。
- [ ] `[INFRA]` `competitor-comparison`：本品与竞品的字段对照、证据链接和采集时间。
- [ ] `[INFRA]` `alert-events`：预警规则、触发值、旧值、新值、证据和通知状态。
- [ ] `[SALES_PROVIDER]` `sales-trend`：成交观察、时间范围、覆盖率、可信度和趋势口径。
- [ ] `[USER_OAUTH]` `own-store-performance`：自家流量、转化、订单和广告数据，单独成表且不与竞品数据混列。

## 9. 安全与数据边界

- [x] 非公开 Provider 独立串行限流；登录失效或验证页会停止当前批次。
- [x] Cookie 和 Token 不进入任务参数、日志、MCP 响应或 Git。
- [ ] 竞争店铺只处理合法可访问的公开数据。
- [ ] 所有推断指标标注计算口径，不把代理信号表述为真实花费或完整销量。
- [ ] 删除监控任务不等于删除历史数据；两种操作分别确认并审计。


## Soldeazy 待办

### 0. 测试纪律（硬约束，先看这条）

- **唯一允许写入的测试账号是 `FUN`（shop_idx=159）**。它名下的数据表是**未刊登**的，
  所以在「已刊登(所有)」筛选下**搜到 0 行**（2026-11-11 实测）；任何要读/写它的测试
  都必须传 `include_unlisted=true`，否则会误判成"目标不存在"。
- **搜索必须显式指定店铺，否则看到的不是你的店铺。**（2026-11-11 踩到）
  `search()` 只有在传了 `shop`（或先 `switch_shop` 设了 `active_shop`）时才加店铺过滤；
  两样都没有时**不做任何过滤**，返回的是平台默认店铺的数据。
  实测：同一个 `US / 已刊登(所有)` 查询，不加过滤返回 25 行全属 **EBAY TAY**；
  显式 `FUN` 返回 **0 行**；显式 `LT` 返回 25 行全属 EBAY LT。
  所以**看完结果先看 `search()["shop"]` 和行内店铺分布**，别假设是 FUN。
- **`LT`（shop_idx=4432）有真实刊登，绝对禁止写入。** 读它是可以的（25 行，SKU `2401`）。
- 实机数据在仓库 `.soldeazy-data`：登录态 `.soldeazy-data\profile`，
  计划与审计 `.soldeazy-data\soldeazy-plans`（profile 的兄弟目录）。
  **不是** `%LOCALAPPDATA%\ebay-mcp`。
- 只读操作（`soldeazy_status` / `search_datasheet` / `list_shops`）可以随便跑。

### 1. `include_unlisted` 下的同步条数判定（已按「只警告不判失败」实现）

- **原记录**：FUN 全是未刊登时，上传 N 条、同步 0 条，`sync_problems` 非空会让
  `ok=false`，属于误报。
- **2026-11-11 实测取证（只读 + 一次登录，未写任何数据）**：
  - 工序队列 25 个任务**全是 `DSUploadTask`，从来没有任何同步类任务**——
    说明 `_await_latest_job` 那条"同步了 N 个数据表"的比对，实际很少触发；
  - 勾选没问题：请求 8 个、实际勾上 8 个；
  - 状态筛选没问题：页面默认空值（=全部），`only_listed=True` 会切到「已刊登(所有)」；
  - **注意**：这次取证没加店铺过滤，行不属于 FUN（见第 0 条），
    所以"FUN 现在的数据是什么状态"仍然只有一条可靠结论：**已刊登筛选下 0 行**。
  - **原症状没能复现**。
- **已做的修改**：`apply_plan` 把 `tolerate_mismatch=not plan.only_listed` 传给
  `_await_latest_job`——计划本身包含未刊登时，条数差额进 `notes`（→ 判决里的
  `warnings`），不判失败；**失败条数（`failed != 0`）仍然严格判失败**。
  已刊登账号的安全边界没有放宽。
- **仍需真实复现**：等 FUN 再出现未刊登数据表时，跑一次完整改动确认 `warnings`
  里出现该提示、且 `ok=true`。

### 2. 校验策略：判决优先，失败才深挖

- `soldeazy_change_price` / `soldeazy_change_stock` 默认只回判决（约 70 token）。
- 只有 `ok=false` 时，才用 `verbose=true` 或分步工具（`reconcile_plan` 等）做细核对。
- 原因：让模型逐条读明细校验，实测累积到 6000 万 token；校验留在服务端才有意义。

### 3. 进度（2026-11-11）

已完成，均为离线改动 + 离线测试，**未对任何账号发过写操作**：

| 项 | 结果 | 位置 |
|---|---|---|
| 关掉自动生成的 `outputSchema` | 7,565 → 6,752 token/请求 | `server.disable_output_schema()` |
| `MCP_TOOLSET` 工具面子集 | 30 → 16 个工具，再降到 4,225 token/请求 | `server.apply_toolset()`、`config.mcp_toolset` |
| `skipped_packs` 截断 | 每次判决最多再省 2,700 token | `soldeazy_change.cap_packs()` |
| 批量目标走文件 `targets_file` | 2000 条入参 10,450 → 5 token | `providers/soldeazy_targets.py` |
| `include_unlisted` 同步条数只警告 | 未刊登计划不再误判 `ok=false` | `soldeazy_apply._await_latest_job` |
| 默认 `limit` 与闸门对齐 | 50 行必被拦 → 20 行可直接返回 | `server._cap_rows`、`plan_changes`、`reconcile` |
| 搜索如实回传店铺范围 | 不再静默返回默认店铺的数据 | `soldeazy._shop_scope_hint` |
| 对账店铺校验 | 读错店铺不再误报成"改动没生效" | `soldeazy_apply.shop_scope_problem` |
| 店铺名长短名兼容 | 导出列 `FUN` / 页面 `EBAY FUN` 都认 | `soldeazy_apply._shop_name_matches` |
| 结果表分页修复 | 每页 25 → 200；勾选逐页翻找；同步按完整清单传 row_ids | `soldeazy._select_page_limit` / `select_datasheets` / `sync_up_via_api` |
| `ebay_get_sales_history` 明细截断 | 默认每 item 只回 20 条成交（旧版单次 3.3 万字符） | `server.ebay_get_sales_history` |
| `ebay_validate_titles` 可不回显标题 | `include_titles=false` 省约 8k 字符/次 | `server.ebay_validate_titles` |
| 明文凭据迁到 `.env` | Cert ID / 紫鸟密码 / DeepSeek key 已离开 `config.local.json` | `.env`（不入库） |
| 数据目录文档对齐 | README 写明本机指到 `.soldeazy-data`，`status` 回显 `plan_dir` | README、`.env.example` |

### 4. 导出/对账的店铺一致性（2026-11-11 检查结果）

- **apply 本来就是安全的**：`shop_problems()` 同时校验「活动账号 id」和「导出文件里的店铺名」，
  不一致就在上传前中止。
- **对账原来没有校验**：`reconcile` 直接 search + export，既不传 `shop` 也不检查导出内容。
  没设 `active_shop` 时导出的是平台默认店铺，每一行都会被判成"查不到"，
  看起来像改动没生效，实际是读错了店。
- **已修**：`read_datasheet_values` 记录本次导出的店铺名（`last_export_shops`），
  `reconcile` 先调 `shop_scope_problem()`，不一致就**中止并写明原因**，
  返回 `error` 而不是 `absent_total=N`；判决层把这条 error 原样报出。
- **店铺名两种写法都要认**：导出文件第 1 列是短名 `FUN`（实测历史 export 确认），
  页面和搜索结果里是长名 `EBAY FUN`。统一成 `_shop_name_matches()`，
  避免格式差异导致误报"没有计划所属的渠道账号"而中止上传。

测试：`223 passed`。

### 5. 结果表分页：旧版"勾选不全"的根因（2026-11-11 实机取证）

- **现象来源**：另一台机器的历史审计里"一次计划 209 个数据表，实际只勾选到 18 个"。
- **根因（LT 只读实测）**：结果表 `#tbl_dSheet` 是分页的，分页条
  `.pagination select.limit` 档位 25/50/100/200，**默认 25 行/页**；
  308 笔记录分 13 页。勾选框和 BULK SYNC 只作用于**渲染出来的行**，
  所以旧版 `select_datasheets` 只能勾到第 1 页里的目标。
- **另外两个坑**：
  - 搜索提交会把每页条数**重置回 25**，所以调档必须放在搜索之后；
  - 调档后 DOM 有 200 行，但页面是虚拟化渲染，视口外的行 `innerText` 为空，
    搜索回显仍只能读到约 60 行——**全量数据必须走导出（whole_result）**。
- **已修**：
  - `search()` 搜索后调 `_select_page_limit(200)`，并回传 `page_limit` /
    `total_records`，让调用方看见分页状态；
  - `select_datasheets()` 改成逐页翻找（`max_pages=20` 封顶），返回
    `{selected, wanted, pages_walked, found, missing}`；
  - `sync_up_via_api(row_ids=...)` 支持显式传完整清单，`apply_plan` 现在
    按计划的 rowid 全量传，不再依赖"页面上勾了哪些"。
- **未修（已知限制）**：搜索回显的虚拟化渲染上限约 60 行/页。
  影响面：`soldeazy_search_datasheet` 的 `limit` 再大也拿不到超过一页的行；
  需要全量时走 `read_datasheet_values`（导出通道）。已在代码注释里写明。

### 6. FUN 实机小批量验证结果（2026-11-11，已获批准）

计划 `price-20261111-064925`：2 个 SKU（`MCPSKU001`、`XS2E8-Black-2B`）共 10 行，
+0.5 改价 → 还原原值。**最终对账 10/10，价格已回到原值**（19.99 / 21.9），
审计 `success=true`。FUN 数据无残留改动。

过程中暴露并修掉 3 个真 bug：

1. **页面导出弹层不可靠**：FUN 上点「导出」后 `#jqizoo` 不出现（第一次 change_price
   就死在这）。已把默认导出通道切到 cookie/API（`export_via_api`），实测一次拿全
   7075 行 / 1637 个 rowid；页面通道保留为 `SOLDEAZY_EXPORT_CHANNEL=page` 的回退。
2. **`include_unlisted=true` 之前是假的**：页面状态 select 会沿用上次的「已刊登」，
   不清档的话 include_unlisted 实际仍按已刊登过滤。现在显式清回空（=全部）。
3. **search 里调每页条数会把导出按钮的点击绑定弄坏**（AJAX 重拉竞态）。
   现在 search 只读档位不改档；需要大页的勾选动作在 `select_datasheets` 里自己调，
   并且所有页面 evaluate 都套了导航竞态重试（`_eval_with_retry`）。

另外把「勾选失败」从 problems 降为 notes：上传已经发生后，勾选崩溃不该把链路
掐在"已改价未同步"的中间态；同步接口本来就按完整清单传 `table_row_ids`。

**TODO #1（warnings 分支）仍未在实机触发**：FUN 的 BULK SYNC 从来不产生工序任务
（历史 25 个任务全是 DSUploadTask），`_await_latest_job` 拿不到 job，notes 无从附加；
`synced=ok` 只代表同步接口返回 200。该分支目前只有单测覆盖，等出现"有同步任务且
条数对不上"的账号才能实机验证。

### 7. 多会话共用与 profile 锁（2026-11-11）

- **机制**：Chromium 一个 user-data-dir 只允许一个进程打开；stdio 模式每会话一个
  服务进程 → 第二个会话抢不到 `.soldeazy-data\profile`。与"全局安装"无关。
- **旧代码把抢锁失败误报成 `SOLDEAZY_BROWSER_LAUNCH_FAILED`**（找不到 Chrome），
  已拆出 `SOLDEAZY_PROFILE_LOCKED`（`launch_error()` 三分类）。
- **空闲自动释放**：`SOLDEAZY_BROWSER_IDLE_SECONDS`（默认 300，0=关）。
  空闲到点先落盘 cookie 再关浏览器，锁交还；持 `_lock`（search 进行中）时顺延。
  会话之间从"互斥"变成"接力"。
- **实时共用仍只有一条路**：`ebay-mcp-server --transport sse` 常驻单例。
- 注意：空闲释放只对**跑新代码的进程**生效；11-09 那串旧服务进程必须重启才受益。

待办：
- [ ] 第 1 条的真实复现：等 FUN 再有未刊登数据表时验证 `warnings` 生效。
- [x] 默认 `limit=50` 与 4000 字符闸门自相矛盾 —— 已把默认降到 20，
      `plan_changes` 明细 20 条、`reconcile` 明细各 10 条；新增测试守住
      「默认参数必须能通过闸门」。
