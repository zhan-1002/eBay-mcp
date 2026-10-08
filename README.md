# eBay MCP

通用 eBay Model Context Protocol 服务。它负责认证、调用、分页、字段透传、
限流重试和稳定错误结构，不包含选品、关键词扩展、商品评分或推荐逻辑。

当前版本：`0.1.0` 基础骨架。

## 当前工具

- `ebay_get_capabilities`：查看环境、Marketplace 和可用能力，不返回凭据。
- `ebay_search_items`：官方 Browse API 搜索与分页。
- `ebay_get_item`：按 REST item ID 读取商品详情。其中的 `estimatedSoldQuantity` 是官方估计已售总数，不是要采集的销量明细。
- `ebay_get_default_category_tree`：获取 Marketplace 默认类目树。
- `ebay_suggest_categories`：官方类目建议。
- `ebay_get_category_aspects`：类目必填、推荐和可选属性。
- `ebay_get_seller_feedback`：官方卖家反馈记录；不等同于完整销量。
- `ebay_translate_text`：官方 Translation API。
- `ebay_get_rate_limits`：应用实际 API 配额。
- `ebay_sales_provider_status`：购买记录 Provider 与本地浏览器会话状态。
- `ebay_sales_open_login`：由 MCP 打开并持续持有人工登录窗口。
- `ebay_read_skill`：为尚未支持 Skills 扩展的客户端读取 Skill。
- `ebay_validate_titles`：机械校验 30 条 eBay 英文标题。
- `ebay_get_sales_history`：按传统数字 itemId 采集购买记录明细。销量数据是每一笔成交，不是官方已售总数。

共 13 个只读工具和 1 个本地会话工具，当前不注册任何 eBay 写工具。

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

uv sync --extra dev
uv run ebay-mcp-server
uv run pytest
```

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
  sales_login.py         独立 Profile 的人工登录入口
  skills/*/SKILL.md      7 个可发现的工作流 Skill
  skill_registry.py      Skill 清单、摘要与安全资源读取
  title_validation.py    标题机械校验
  contracts.py           Marketplace 与统一响应
tests/                   离线契约测试
```

设计和非公开数据源边界见
[`docs/ebay-mcp-architecture.md`](docs/ebay-mcp-architecture.md)。
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
