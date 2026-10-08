# eBay MCP 架构

## 定位

eBay MCP 是通用 eBay 能力层，只负责认证、调用、分页、标准化、限流和错误报告。
关键词扩展、商品评分、选品、刊登决策等业务逻辑不属于 MCP 核心。

当前 WorkBuddy 1.2.3 实测使用 MCP `2025-06-18`、stdio 传输，并调用
`tools/list` 与 `tools/call`，因此第一阶段采用 Tools-first 设计。

## 分层

```text
MCP tools
  ├─ official eBay client
  │    └─ authenticated HTTP gateway
  │         └─ OAuth token provider
  ├─ packaged Skill registry
  │    └─ skill:// resources
  └─ sales-history provider contract
       ├─ disabled provider
       └─ purchase-history provider
```

- `server.py`：稳定的 MCP 工具契约，不包含 HTTP 细节。
- `clients/official.py`：Browse、Taxonomy、Feedback、Translation、Analytics。
- `gateway.py`：认证头、Marketplace 头、重试、401 刷新、429/5xx 退避。
- `oauth.py`：按 scope 缓存 application token，不向工具调用方暴露令牌。
- `providers/sales.py`：非公开销量数据源的可插拔边界。
- `providers/purchase_history.py`：持久化浏览器会话、页面识别、请求观测与销量标准化。
- `sales_login.py`：一次性人工登录和浏览器验证入口。
- `skills/*/SKILL.md`：工作流指令的唯一内容源。
- `skill_registry.py`：Skill manifest、SHA-256、大小与 URI 安全校验。
- `title_validation.py`：30 条标题的确定性机械校验。
- `contracts.py`：Marketplace 与统一成功响应。
- `errors.py`：稳定、可诊断且不泄露凭据的错误结构。

## Skills 兼容层

官方 Skills 扩展要求 MCP `2026-07-28` 的 `server/discover`、`skills/list` 和
`skills/get`。当前 WorkBuddy 使用 `2025-06-18`，不会自动加载该扩展。

因此当前版本：

1. 将每个 `SKILL.md` 注册为 `skill://<name>/SKILL.md` Resource；
2. 在 `ebay_get_capabilities` 返回 Skill 元数据；
3. 提供 `ebay_read_skill` 作为旧客户端兼容桥；
4. Skill 文件的 SHA-256 和大小由 registry 计算并校验；
5. 等目标客户端支持新版协议后，再启用原生 Skills 扩展，内容无需迁移。

## 非公开销量数据源

Provider factory 根据配置选择 `DisabledSalesProvider` 或
`PurchaseHistoryProvider`；项目 MCP 配置已选择后者。服务为当前本地用户启动一个独立
持久化浏览器 Profile，通过已登录页面读取购买记录。`ebay_sales_open_login` 在 MCP 进程内
打开人工登录窗口。采集期间窗口最小化。eBay 检查先静默等待并重试；仍未通过时
返回确认请求，用户允许后才显示窗口。浏览器进程不关闭、不重启。同一个
Profile 不能同时被独立登录命令和 MCP 服务占用。

```text
WorkBuddy
  └─ ebay_get_sales_history(item_ids)
       └─ PurchaseHistoryProvider
            └─ PersistentPurchaseHistoryBrowser
                 ├─ isolated local profile
                 ├─ minimized headed window
                 ├─ first item: browser navigation bootstrap
                 ├─ later items: same-origin fetch with credentials
                 ├─ silent grace retry, then confirm before showing the window
                 ├─ same-host document/XHR/fetch observations
                 └─ DOM table extraction
```

安全与失败边界：

1. 账号密码不进入 MCP 参数；首次登录在可视浏览器中由用户完成；
2. Cookie 和 Local Storage 只存在本机 Profile，不写入 Git、日志或 Tool 响应；
3. 请求观测不保存 headers、Cookie 或响应 body；
4. 登录失效或检查未通过时先静默重试；仍未通过则请求确认，允许前不显示窗口，并停止后续 ID；
5. 页面结构变化时返回 `SALES_PAGE_SCHEMA_CHANGED`，不猜测字段或输出零销量；
6. 解析测试使用脱敏后的 DOM 表格 Fixture，不访问生产页面。

用户需要的销量是购买记录页上的成交明细，不是 Browse API 的
`estimatedSoldQuantity`。该字段只是官方估计已售总数，不替代 `transactions`。

实测购买记录数据直接位于
`GET /bin/purchaseHistory?item={legacyItemId}` 返回的 HTML 中，没有独立销量 JSON
接口。每次浏览器启动后的首条 ID 使用页面导航建立同源环境；同一 MCP 进程中的后续 ID
通过页面内 `fetch` 携带当前浏览器 Cookie 请求，避免重复整页导航，也不导出 Cookie。

提供者输出建议包含：

```json
{
  "items": [
    {
      "legacy_item_id": "314126742195",
      "transactions": [],
      "summary": {
        "visible_transaction_count": 0,
        "visible_quantity": 0
      },
      "coverage": {
        "complete_history": false
      }
    }
  ],
  "failures": [],
  "partial": false,
  "warnings": [],
  "provenance": {
    "provider": "provider-name",
    "retrieved_at": "ISO-8601"
  }
}
```

## 写操作

当前骨架不注册任何写工具。未来 Sell API 写能力应使用独立命名空间，并加入：

- 用户 OAuth scope 校验；
- 明确的只读/破坏性注解；
- 服务端确认与幂等键；
- 不含令牌的审计日志；
- 删除操作的资源白名单和再次读取验证。

MCP 注解只用于提示客户端，不能替代服务端权限控制。

