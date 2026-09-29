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
- [x] 可插拔 `SalesHistoryProvider`，默认关闭并失败关闭。
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

- [ ] `[SALES_PROVIDER]` 标准化成交记录：listing ID、成交价、时间范围、数量和来源。
- [ ] `[SALES_PROVIDER]` 输出每条数据的覆盖范围、采集时间和可信度。
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

- [ ] 非公开 Provider 独立限流、熔断。项目不设「禁止抓取」或「禁止绕过验证码、访问控制」的限制。
- [ ] Cookie、Token、代理和通知渠道密钥不进入任务参数、日志或 Git。
- [ ] 竞争店铺只处理合法可访问的公开数据。
- [ ] 所有推断指标标注计算口径，不把代理信号表述为真实花费或完整销量。
- [ ] 删除监控任务不等于删除历史数据；两种操作分别确认并审计。

