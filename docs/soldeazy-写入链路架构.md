# Soldeazy 写入链路：架构与验收清单

> 2026-11-07 定稿。用户提出的硬要求：**接口解决、无头运行、改动集不可变、对账可追溯**。

## 一、一次改动的完整生命周期

```
① 起草  soldeazy_plan_changes(kind, site, targets)
        └ 读当前值（1 次导出）→ 逐条算出 old/new → 写 plan.json（status=draft）

② 确认  soldeazy_confirm_plan(plan_id)
        └ 写 sha256 旁车 + 文件设只读 → 此后任何程序不得修改
        └ 发现要改：另起一份新计划（supersedes 指向旧的），旧计划归档 archive/

③ 执行  soldeazy_apply_plan(plan_id, dry_run=False)
        └ 校验哈希 → 导出（1 次）→ 批量改单元格 → 上传（1 次）
        └ 整个计划 = 2 次请求，与条数无关

④ 对账  soldeazy_reconcile_plan(plan_id)
        └ 轮询导出实际值，与计划的 new 逐条比对
        └ 连续两轮一致即判定稳定；结果写 <plan_id>.reconcile.json
```

## 二、为什么是"导出→批量改→一次上传"

单条保存（打开表单 + 提交）每条要 2 次请求，500 条就是 1000 次；
批量通道固定 2 次请求，规模越大优势越明显。

逐条保存的通道已封存（`apply_datasheet_changes`），只在单独修一条记录时才用。

## 三、对账怎么保证

1. **意图不可变**：计划的 sha256 在确认时锁定，执行前重算，被改过直接拒绝；
2. **读的是线上真相**：对账重新导出，不看接口返回的"成功"字样；
3. **轮询到稳定**：平台应用是异步的，读一次就判会误报（实测出现过 7/8，稍后变 8/8）；
4. **不自动修**：不一致只报告，由人决定是补一份新计划还是接受现状；
5. **留痕**：`<plan>.audit.jsonl` 记录每次执行，`<plan>.reconcile.json` 记录每次对账。

## 四、运行形态

| 项 | 值 | 说明 |
|---|---|---|
| 浏览器 | **无头**（`SOLDEAZY_HEADLESS` 默认 1） | 只在首次登录或需要人工介入时开有头 |
| 进程 | 单例常驻 | MCP 服务端全程一个浏览器，不重复登录 |
| 登录 | 勾「记住用户名」+ cookie 落盘 | `session_cookies.json` 保存含会话级的 cookie，重启可复用 |
| 导出通道 | `SOLDEAZY_EXPORT_CHANNEL=page`（默认） | 可切 `cookie`，见下 |

## 五、待实机验证（未验证前保持现状）

1. **纯 cookie 导出**（`export_via_api`）：表单字段取自抓包
   （`bulk_option=whole_result` + `listExppf=55` + `listExpfmt=xlsx`），
   写好了但没有实跑过，默认关闭。
2. **cookie 落盘恢复**：`session_cookies.json` 能否跨进程恢复 `_ht_ses_`，
   需要重启一次验证。
3. **计划工具全链路**：起草/确认/执行/对账四个 MCP 工具已接上，
   但只在脚本里跑过，没通过 MCP 客户端调用过。

## 六、已知限制

- 批量通道失败粒度整份，不像逐条那样能精确到某一条；
  对账会补上这个信息（哪几行没生效）。
- 多变体数据表的子体行变更走"母体 SKU 展开"，用户的输入必须是母体 SKU。
- 价格只按子体 SKU 精确匹配；前缀命中多条时报冲突，不猜。
