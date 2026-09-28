# eBay MCP

通用 eBay Model Context Protocol 服务。它负责认证、调用、分页、字段透传、
限流重试和稳定错误结构，不包含选品、关键词扩展、商品评分或推荐逻辑。

当前版本：`0.1.0` 基础骨架。

## 当前工具

- `ebay_get_capabilities`：查看环境、Marketplace 和可用能力，不返回凭据。
- `ebay_search_items`：官方 Browse API 搜索与分页。
- `ebay_get_item`：按 REST item ID 读取商品详情。
- `ebay_get_default_category_tree`：获取 Marketplace 默认类目树。
- `ebay_suggest_categories`：官方类目建议。
- `ebay_get_category_aspects`：类目必填、推荐和可选属性。
- `ebay_get_seller_feedback`：官方卖家反馈记录；不等同于完整销量。
- `ebay_translate_text`：官方 Translation API。
- `ebay_get_rate_limits`：应用实际 API 配额。
- `ebay_sales_provider_status`：非公开销量数据提供者状态。
- `ebay_read_skill`：为尚未支持 Skills 扩展的客户端读取 Skill。
- `ebay_validate_titles`：机械校验 30 条 eBay 英文标题。
- `ebay_get_sales_history`：预留的销量提供者接口；基础包默认关闭。

共 13 个只读工具，当前不注册任何写工具。

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

## 结构

```text
src/ebay_mcp_server/
  server.py              MCP tools 与传输入口
  clients/official.py    官方 eBay API 适配
  gateway.py             OAuth、请求头、重试、错误转换
  oauth.py               按 scope 缓存 application token
  providers/sales.py     非公开销量数据源的可插拔接口
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

eBay 未向当前应用开放完整销量 API，因此预留了 `SalesHistoryProvider`。
基础包不包含页面抓取实现，也不会尝试绕过验证码、访问控制或反自动化机制。
未来提供者应作为独立模块接受合规、限流、会话安全和解析回归检查。

## 历史研究模块

以下目录是此前项目，保留供参考，但不属于 eBay MCP 核心：

- [`01_关键词选品`](01_关键词选品/README.md)
- [`02_soldeazy详情补数`](02_soldeazy详情补数/README.md)

`02_soldeazy详情补数` 曾在生产账号创建数据表。已有记录继续封存不删；
任何后续写操作仍必须遵守其 README 中的清单和逐行复验要求。
