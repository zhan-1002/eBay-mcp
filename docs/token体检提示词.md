# 给「跑旧版 MCP 的机器」的历史取证提示词

用途：那台机器跑的是旧版本，抓不到我们这边的改动。让它把**已有的使用历史**交出来，
我们照着改。**不需要它重新测试、不需要它调用任何工具。**

下面整段可直接复制给对方 agent。

---

## 提示词（从这里开始复制）

我在另一台机器上维护同一个 eBay MCP 的新版本，需要你这边的**历史使用数据**做对比。

**这次不要执行任何新操作**：

1. **不要调用任何 MCP 工具**（包括 `soldeazy_status`），不要启动浏览器，不要跑测试。
2. 全程只读。不要修改、移动、删除任何文件，尤其不要动 `.soldeazy-data`。
3. 报告里不要出现凭据、cookie、session、token 内容。原始日志一律不要发给我，
   只发**聚合数字**和**截断到 2KB 的脱敏样本**。

你只需要做四件事：找到日志 → 识别格式 → 聚合统计 → 补上仓库里的历史产物。

### 第一步：找到历史日志都落在哪

按顺序找，找到就记下路径（不用全找齐）：

- MCP 客户端自己的数据目录。常见位置：
  - `~/.workbuddy/`（含 `mcp.json` 同级的日志、session、localStorage 导出）
  - `%APPDATA%` 或 `%LOCALAPPDATA%` 下该客户端名字的目录
  - `~/.claude/`、`~/.cursor/`、`~/.codex/` 之类
- 客户端的对话/会话记录（通常是 `.json` / `.jsonl`，一条一行）
- MCP 服务进程的 stderr 日志（服务端 `logging` 输出，可能被客户端捕获成日志文件）
- 仓库自身的历史产物（这个一定有，见第四步）

**先只做一件事**：把找到的**文件名、大小、修改时间、前 3 行**（脱敏）列给我，
并说明每份大概是"工具调用记录 / 对话记录 / 纯文本日志"里的哪一种。

### 第二步：聚合统计（关键）

用下面这段脚本扫一个目录（只读，不联网）。它能兼容常见的 JSON / JSONL / 日志格式，
把形如 `{"name": ..., "arguments": ..., "result": ...}` 的记录抓出来。

```python
import collections, json, os, sys

root = sys.argv[1]          # 替换成你第一步找到的目录
stats = collections.defaultdict(lambda: {"calls": 0, "args": 0, "res": 0, "max": 0})
samples = {}

def size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except Exception:
        return len(str(value))

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__", ".venv"}]
    for name in filenames:
        if not name.lower().endswith((".json", ".jsonl", ".log", ".txt")):
            continue
        path = os.path.join(dirpath, name)
        try:
            if os.path.getsize(path) > 200 * 1024 * 1024:
                continue
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line[0] not in "[{":
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            stack = [obj]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    tool = next((node.get(k) for k in ("tool", "tool_name", "name")
                                 if isinstance(node.get(k), str) and node.get(k)), None)
                    args = next((node.get(k) for k in ("arguments", "args", "input", "parameters")
                                 if k in node), None)
                    res = next((node.get(k) for k in ("result", "output", "response", "content")
                                if k in node), None)
                    if tool and (args is not None or res is not None):
                        row = stats[tool]
                        row["calls"] += 1
                        a = size(args) if args is not None else 0
                        r = size(res) if res is not None else 0
                        row["args"] += a
                        row["res"] += r
                        row["max"] = max(row["max"], a + r)
                        samples.setdefault(tool, {"arguments": args, "result": res})
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)

print(f"{'tool':<30}{'calls':>7}{'args_chars':>12}{'res_chars':>12}{'max_chars':>11}")
for tool, row in sorted(stats.items(), key=lambda kv: kv[1]["args"] + kv[1]["res"], reverse=True):
    print(f"{tool:<30}{row['calls']:>7}{row['args']:>12}{row['res']:>12}{row['max']:>11}")

def estimate(text_len_chars, text):
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return round(ascii_chars / 4 + (len(text) - ascii_chars) * 1.5)

json.dump(stats, open("token_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n聚合结果已写入 token_stats.json")
```

跑完把表格给我。如果一份日志都没有，如实说"没有日志"，直接跳到第四步。

### 第三步：看会话里有没有"被截断/被拦"的痕迹

在历史记录里搜这几个字符串，命中就把**上下文 200 字**贴过来（脱敏）：

- `SOLDEAZY_OUTPUT_TOO_LARGE`
- `allow_large_output`
- `verbose`
- `582 token` / `token，超过单次上限`

这是判断闸门到底拦了多少次的直接证据。

### 第四步：仓库里的历史产物（一定有，重点）

旧版本每次改动都会在仓库留下文件，这些**不需要跑任何东西**就能读：

```
<仓库>/.soldeazy-data/soldeazy-plans/
  *.json               计划：看 items 数组长度 = 单次改了多少条
  *.reconcile.json     对账：看 mismatched_total / absent_total
  *.audit.jsonl        审计：看每次执行的 applied / failed / warnings
```

统计出：

- 一共几个计划、单次 `items` 条数的**分布**（最小/中位/最大）
- 有没有超过 200 条的计划，最大那条多少条
- `reconcile` 里 `mismatched` / `absent` 的最大条数
- `audit.jsonl` 里出现过的 `warnings` 内容（去重）

**这一条最能说明你们的真实批量规模**，比任何估算都准。

### 第五步：交回来的报告格式

```
## 1. 版本指纹
- git HEAD（如有）
- 工具总数
- 是否存在：apply_toolset / targets_file / outputSchema / MAX_PACKS

## 2. 日志位置
| 文件 | 大小 | 类型（工具调用/对话/纯文本） |
|---|---|---|

## 3. 按工具的聚合（第三步脚本的输出表）
tool | calls | args_chars | res_chars | max_chars

## 4. 被拦/被截断的痕迹
命中的字符串 + 出现次数 + 1 条脱敏上下文

## 5. 历史产物的规模
- 计划数、items 分布、最大一条多少条
- reconcile 的 mismatched / absent 最大值
- audit 里的 warnings（去重后）

## 6. 结论：按"每次调用字符数 × 次数"排序的前 5 个消耗点
每条写：哪个工具、哪个字段最大、你判断的原因
```

### 注意

- **不要为了凑数据去跑工具**。没有就说没有。
- 脚本只读文件，不会改任何东西；如果不放心，先在一个副本目录上跑。
- 如果历史里只有"结果"没有"入参"，那就只报返回侧，入参那栏留空。

---

## 拿到报告后我怎么用

| 它的数据 | 我这边对应的改动 |
|---|---|
| 工具 schema 体积 | `MCP_TOOLSET` 子集 + 关 `outputSchema`（已做，7,565 → 4,225） |
| 大批量计划的 `items` 分布 | `targets_file`（已做，2000 条 10,450 → 5） |
| `SOLDEAZY_OUTPUT_TOO_LARGE` 命中次数 | 默认 limit 已降到 20，明细降到 20/10 |
| `skipped_packs` 相关 warnings | 已截断到 10 条 + total |
| 它挖出的、我没预料到的字段 | 按它的排序补 |

## 第一份回传报告的处理结果（2026-11-11）

| 报告发现 | 结论 | 改动 |
|---|---|---|
| `ebay_get_sales_history` 2 次共 33,096 字符（单次最大 32,938） | 全量成交明细回传 | 默认每 item 只回 20 条，`summary`/`coverage` 仍全量；`max_transactions_per_item` 可调 |
| `ebay_validate_titles` 3 次共 24,604 字符 | 30 条标题文本回显 | 新增 `include_titles=false`，只回 index + 判决 |
| `verbose` 在历史里出现 61 次 | 模型在拿明细自查 | 判决优先策略已有；报告佐证了方向正确 |
| `allow_large_output` 出现 7 次 | 闸门在旧版被绕过 | 默认 limit 降到 20 后，常规调用不再需要它 |
| 计划 items 分布 4/194/235/235/277 | 真实批量规模 200+ | `targets_file` 正是为此设计 |
| 审计警告"计划 209 个、只勾选到 18 个" | **不是 token 问题，是正确性问题** | 根因是结果表分页（默认 25 行/页）：已修，见 TODO 第 5 节 |

> 注意最后一行：那份报告里最值钱的不是 token 数字，而是这条审计警告。
> 它暴露的是旧版**勾选不全**——同步只作用于渲染出来的行。这个 bug 比
> 任何 token 优化都重要，已修并加了逐页翻找 + 完整清单传参。