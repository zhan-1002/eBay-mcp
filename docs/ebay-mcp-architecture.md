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
       └─ disabled provider（默认）
```

- `server.py`：稳定的 MCP 工具契约，不包含 HTTP 细节。
- `clients/official.py`：Browse、Taxonomy、Feedback、Translation、Analytics。
- `gateway.py`：认证头、Marketplace 头、重试、401 刷新、429/5xx 退避。
- `oauth.py`：按 scope 缓存 application token，不向工具调用方暴露令牌。
- `providers/sales.py`：非公开销量数据源的可插拔边界。
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

基础包不包含爬虫，只预留 `SalesHistoryProvider`。未来实现必须放在独立包或独立模块，
不得把页面结构、Cookie 或反自动化处理混进官方 API 客户端。

实现提供者前需要单独确认：

1. 数据源的访问条款、账号授权和适用法律；
2. 是否允许自动访问以及允许的频率；
3. Cookie、会话与代理信息只保存在本机私密配置；
4. 不绕过验证码、访问控制或其他技术限制；
5. 设置独立限流、超时、熔断与并发上限；
6. 每条结果记录来源、抓取时间和原始标识；
7. 页面结构变化时失败关闭，不猜测字段；
8. 用 Fixture 做解析回归，不在单元测试中访问生产页面。

提供者输出建议包含：

```json
{
  "items": [],
  "next_cursor": null,
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

