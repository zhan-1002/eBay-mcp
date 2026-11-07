# eBay MCP

通用 eBay Model Context Protocol 服务。它负责认证、调用、分页、字段透传、
限流重试和稳定错误结构，不包含选品、关键词扩展、商品评分或推荐逻辑。
同时内置 Soldeazy 数据表读写链路（改价 / 改库存 / 创建 / 删除 / 图片 / 同步）。

当前版本：`0.1.0` 基础骨架。

## 当前工具

共 **32 个**：21 个只读、5 个本地动作、6 个远端写。

### eBay 官方 API

- `ebay_get_capabilities`：查看环境、Marketplace 和可用能力，不返回凭据。
- `ebay_search_items`：官方 Browse API 搜索与分页。
- `ebay_get_item`：按 REST item ID 读取商品详情。其中的 `estimatedSoldQuantity` 是官方估计已售总数，不是要采集的销量明细。
- `ebay_get_default_category_tree`：获取 Marketplace 默认类目树。
- `ebay_suggest_categories`：官方类目建议。
- `ebay_get_category_aspects`：类目必填、推荐和可选属性。
- `ebay_get_seller_feedback`：官方卖家反馈记录；不等同于完整销量。
- `ebay_translate_text`：官方 Translation API。
- `ebay_get_rate_limits`：应用实际 API 配额。
- `ebay_read_skill`：为尚未支持 Skills 扩展的客户端读取 Skill。
- `ebay_validate_titles`：机械校验 30 条 eBay 英文标题。

### 购买记录

- `ebay_sales_provider_status`：购买记录 Provider 与本地浏览器会话状态。
- `ebay_sales_open_login`：由 MCP 打开并持续持有人工登录窗口。
- `ebay_get_sales_history`：按传统数字 itemId 采集购买记录明细。销量数据是每一笔成交，不是官方已售总数。

### Soldeazy 只读

- `soldeazy_status`：浏览器 profile、凭据与写工具开关状态。
- `soldeazy_search_datasheet`：按站点 + SKU 通配串读取数据表行（Row ID / 母体 / SKU / 价格 / 运费 / 数量）。
- `soldeazy_list_shops`：列出当前登录可操作的渠道账号（店铺），返回 id 与简称。
- `soldeazy_plan_changes`：读线上现状 → 生成**改动计划草稿**（JSON），返回 `plan_id`。
- `soldeazy_reconcile_plan`：把线上实际值与已冻结计划逐条比对，输出对账报告。
- `soldeazy_stock_template`：生成运营手填的库存表模板。
- `soldeazy_change_history`：读本地变更清单，新的在前。

### Soldeazy 本地动作

- `soldeazy_open_login`：打开登录页并保留会话（有 cookie 时直接复用，不再登录）。
- `soldeazy_switch_shop`：切换当前渠道账号，后续调用默认用它。
- `soldeazy_confirm_plan`：**冻结计划**——写 sha256、文件设只读，此后任何工具都不得修改。

### Soldeazy 远端写（默认关闭）

- `soldeazy_preview_price_change` / `soldeazy_preview_stock_change`：旧版预览入口，返回 `confirm_token`。
- `soldeazy_update_price` / `soldeazy_update_stock`：旧版写入入口，凭令牌上传并 BULK SYNC。
- `soldeazy_apply_plan`：**执行已冻结计划**——导出 → 批量改 → 一次上传 → 工序核对。
- `soldeazy_create_datasheet`：创建数据表（从刊登复制，或从0建空表并填内容）。
- `soldeazy_delete_datasheet`：按 Row ID 删除数据表。
- `soldeazy_upload_photo`：上传产品图片（文件直传）或用可访问的图片 URL 热链。

写工具默认关闭：没有 `SOLDEAZY_WRITE_ENABLED=1` 一律拒绝。

## Soldeazy 写入链路（已实机验收）

Soldeazy 没有公开接口文档，生产链路是「导出 xlsx → 离线改 → 上传 → BULK SYNC」
（影刀应用 `soldeazy批量改价`）。本服务按抓包得到的真实接口复刻，**不点页面按钮**。

一次改动的完整生命周期：

```
① 起草  soldeazy_plan_changes(kind, site, targets)
        └ 读当前值 → 逐条算出 old/new → 写 plan.json（status=draft，可反复重生成）

② 确认  soldeazy_confirm_plan(plan_id)
        └ 写 sha256 旁车 + 文件设只读 → 此后任何程序不得修改
        └ 要改就另起一份新计划（supersedes 指向旧的），旧计划归档 archive/

③ 执行  soldeazy_apply_plan(plan_id, dry_run=False)
        └ 校验哈希 → 导出（1 次）→ 批量改单元格 → 上传（1 次）
        └ 整个计划固定 2 次请求，与条数无关
        └ 上传后自动核对「工序管理」任务：条数必须等于计划、零失败、逐行成功

④ 对账  soldeazy_reconcile_plan(plan_id)
        └ 轮询导出实际值，与计划的 new 逐条比对，结果写 <plan_id>.reconcile.json
```

### 业务规则（2026-11-07 用户纠正后）

- **改价**：给的是**子体 SKU** 和确切价格，写进去就是这个价。
  不推断件数、不算最低售价、不减邮费、不做"只涨不降"。
  精确匹配不到时才退化成前缀匹配；前缀命中多个子体时报冲突、**不猜**。
- **改库存**：给的是**母体 SKU**，命中的是它下面**全部行**（母体行 + 所有子体行）。
  实测：只写母体行，子体不会跟随，所以必须逐行写。
  数量是绝对值，不做打包换算。
- 上传只允许落在 **E(数量) / F(价格)** 两列，文件写回后逐格自检，出现其它列差异即拒绝上传。

### 三个必须记住的坑

1. **导出文件有两行表头**（技术表头 + 显示表头）。裁剪上传文件时必须两行都保留，
   否则平台会把第一条数据当表头吃掉，少处理一个数据表，且不报错。
2. **导出接口是 `table_action=bulk-export` + `mode=dsheet_datatable`**，
   不是搜索用的 `show` + `dsheet_list`。
3. **整份导出上传会 revise 文件里的每一行**。所以上传文件必须收窄到计划涉及的
   数据表，否则会把没打算动的行覆盖成导出时的旧值。

### 运行形态

| 项 | 默认 | 说明 |
|---|---|---|
| `SOLDEAZY_HEADLESS` | `1`（无头） | 日常零窗口；只有首次登录需要人工时才开有头 |
| `SOLDEAZY_EXPORT_CHANNEL` | `page` | 可切 `cookie`，两者输出逐格一致（已验收） |
| 登录态 | cookie 落盘 | 登录时勾「记住用户名」，cookie 存 `session_cookies.json`（含会话级），重启可复用 |

### 库存表约定（运营手填，可选）

`库存更新.xlsx`，工作表名 `库存`，第 1 行表头 `SKU | 库存 | 备注`。
也可以直接调 `soldeazy_plan_changes(kind="qty", targets={SKU: 数量})`，不必经过 Excel。


## Skills 与 Resources

服务内置 7 个 Agent Skills，并以 `skill://` MCP Resources 暴露：

- `ebay-listing-retrieval`
- `ebay-taxonomy-navigation`
- `ebay-seller-feedback`
- `ebay-translation`
- `ebay-api-diagnostics`
- `ebay-sales-history`
- `ebay-title-generation`

`ebay-title-generation` 按当前要求输出恰好 30 条标题，并配合
`ebay_validate_titles` 检查数量、80 字符、标点、重复词、重复标题以及调用方提供的
禁用品牌/型号词。

官方 Skills 扩展要求 MCP `2026-07-28`。WorkBuddy 1.2.3 当前实测仍使用
`2025-06-18`，因此 Skill 内容以 Resource 为唯一来源，同时提供
`ebay_read_skill` 兼容读取工具。

## 快速开始

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写 EBAY_CLIENT_ID / EBAY_CLIENT_SECRET
# Soldeazy 另需 SOLDEAZY_USERNAME / SOLDEAZY_PASSWORD

uv sync --extra dev --extra soldeazy
uv run ebay-mcp-server
uv run pytest
```

Soldeazy 首次运行会做一次登录（默认无头，凭据来自 `.env`），之后 cookie 落盘复用，
不再重复登录。需要人工介入时设 `SOLDEAZY_HEADLESS=0` 开窗口。

仓库根目录提供 `.mcp.json`。WorkBuddy 1.2.3 实测使用 MCP `2025-06-18`
和 stdio 传输，可把同样的 `uv run ebay-mcp-server` 命令加入其 MCP 配置。

也可以继续使用已被 `.gitignore` 排除的 `config.local.json`：

```json
{
  "ebay_api": {
    "env": "production",
    "client_id": "你的 App ID",
    "client_secret": "你的 Cert ID"
  }
}
```

环境变量优先于 JSON 配置。不要提交真实凭据、Token、Cookie 或会话文件。

### 购买记录 Provider

每位本地用户使用独立的持久化浏览器 Profile。首次启用时：

```powershell
uv sync --extra dev --extra sales
```

先在 `.env` 设置：

```dotenv
EBAY_SALES_PROVIDER=purchase_history
EBAY_SALES_BROWSER_CHANNEL=chrome
EBAY_SALES_MANUAL_RECOVERY_TIMEOUT=900
```

浏览器始终以有头模式启动，并在采集时最小化到后台。登录态保存在持久化 Profile 和
当前 MCP 进程内，不使用 Playwright 无头模式，也不发送额外保活请求。启动 MCP 后调用
`ebay_sales_open_login`，在弹出的窗口中人工完成登录或验证。随后调用
`ebay_sales_provider_status` 和 `ebay_get_sales_history`：

```json
{
  "item_ids": ["314126742195", "385543168522"],
  "marketplace_id": "EBAY_GB",
  "limit_per_item": 100
}
```

这里必须使用商品网址中的传统数字 `legacyItemId`，不能传
`v1|314126742195|0` 形式的 Browse REST ID。一次最多 50 个 ID，按配置间隔串行访问。
Profile 默认保存在用户本地数据目录，不在仓库内。不要同时运行独立登录命令和 MCP，
也不要退出浏览器进程或重启 MCP。最小化窗口不会结束登录态。

采集遇到 eBay 检查页时，窗口保持隐藏，并在约 10 秒内轮询是否出现人机验证组件。
检查自行通过时不弹出窗口。只有验证组件真正出现，才返回
`SALES_WINDOW_CONFIRMATION_REQUIRED`。没有组件、检查也未结束时返回
`SALES_CHECK_UNRESOLVED`，窗口仍然隐藏。只有用户明确允许后，才调用
`ebay_sales_open_login` 或带 `allow_browser_window=true` 重新请求。状态为
`SALES_BROWSER_PROFILE_LOCKED` 时应关闭占用同一 Profile 的浏览器进程，不能同时启动
第二个实例。

## 结构

```text
src/ebay_mcp_server/
  server.py              MCP tools 与传输入口
  clients/official.py    官方 eBay API 适配
  gateway.py             OAuth、请求头、重试、错误转换
  oauth.py               按 scope 缓存 application token
  providers/sales.py     非公开销量数据源的可插拔接口
  providers/purchase_history.py
                         持久化浏览器、购买记录解析与汇总
  providers/soldeazy.py  Soldeazy 浏览器：搜索/导出/上传/同步/创建/删除/图片/工序
  providers/soldeazy_plan.py
                         不可变改动计划：草稿 → 冻结 → 校验 → 归档
  providers/soldeazy_apply.py
                         计划执行（批量上传）与对账
  providers/soldeazy_workbook.py
                         导出表改写与上传前逐格自检
  providers/soldeazy_pricing.py
                         旧版算价内核（预览工具仍在用）
  providers/soldeazy_stock.py
                         运营库存表约定与解析
  providers/soldeazy_write.py
                         旧版写入令牌与漂移检查
  sales_login.py         独立 Profile 的人工登录入口
  skills/*/SKILL.md      7 个可发现的工作流 Skill
  skill_registry.py      Skill 清单、摘要与安全资源读取
  title_validation.py    标题机械校验
  contracts.py           Marketplace 与统一响应
tests/                   离线契约测试（158 项）
```

设计和非公开数据源边界见
[`docs/ebay-mcp-architecture.md`](docs/ebay-mcp-architecture.md)。

Soldeazy 相关文档：

- [`docs/soldeazy-写入链路架构.md`](docs/soldeazy-写入链路架构.md) — 计划生命周期与对账保证
- [`docs/soldeazy-创建与图片-接口说明.md`](docs/soldeazy-创建与图片-接口说明.md) — 创建/保存/删除/图片接口
- [`docs/soldeazy-验收清单.md`](docs/soldeazy-验收清单.md) — A–F 六组验收项及结果
- [`docs/待确认清单-影刀改价.md`](docs/待确认清单-影刀改价.md) — 与影刀原流程的差异确认记录

店铺监控、竞品对比、销量趋势和预警系统的可选路线图见
[`TODO.md`](TODO.md)。

## 非公开销量接口

eBay 未向当前应用开放完整销量 API，因此销量数据继续通过独立的
`SalesHistoryProvider` 接入。可选的 `purchase_history` 实现使用用户自己的本地登录
会话读取 `/bin/purchaseHistory?item=...`，不与官方 API 客户端混合。

用户需要的销量数据是这里采集到的成交明细：每一行的成交价、数量、时间和可见规格。
`visible_quantity` 只是这些行的数量合计。官方 `ebay_get_item` 里的
`estimatedSoldQuantity` 是估计已售总数，一般不用它代替这批明细。会话过期或出现浏览器检查页时，Provider 先静默重试；仍未通过时请求用户确认，确认前不显示窗口。超时或
页面结构无法识别时停止当前批次并返回明确状态，不会把异常页面记为零销量。网络观测只保留方法、URL、状态码、资源类型和 Content-Type，不记录请求头、
Cookie 或响应中的账号凭据。

真实页面验证表明购买记录直接包含在 `purchaseHistory` 的 HTML 响应中。浏览器启动后的
首条 ID 使用正常页面导航，后续 ID 在同一页面上下文内通过带登录凭据的 `fetch` 获取
HTML，因此 Cookie 始终由浏览器维护，不需要复制到 MCP 参数或独立 HTTP 客户端。

## 封存材料

关键词选品和 Soldeazy 详情补数不属于本 MCP。二者已于 2026-09-28 整目录封存到
[`archive/`](archive/README.md)，停止开发，也不接入当前服务。

Soldeazy 生产账号上已创建的数据表继续保留，不删除。清单和逐行复验规则见
`archive/02_soldeazy详情补数/文档/生产账号数据表创建记录_封存.md`。
