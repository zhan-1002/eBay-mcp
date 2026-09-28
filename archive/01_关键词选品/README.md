# 关键词选品

> 已于 2026-09-28 封存。本目录不属于 eBay MCP，停止开发。说明见仓库 `archive/README.md`。

输入：关键词、站点（**默认走 eBay 官方 API**，不再需要紫鸟店铺）  
输出：30 条推荐 title + 关键词评分 / 修饰词三分类 / 价格区间与占比 / 品牌壁垒 / 末级类目 ID

## 现行脚本

| 文件 | 角色 |
|---|---|
| `脚本/run_keyword_research.py` | 总入口 |
| `脚本/collect_ziniao.py` | 紫鸟开店、点配送地、搜 200 条（详情页默认不采） |
| `脚本/collect_ebay_api.py` | **官方 Browse API 采集（默认）**：搜索 200 条 + **并发**逐条 getItem |
| `脚本/kw_menu.py` | **交互式壳程序**：填关键词（可多个）→ 选站点（可多选）→ 跑 → 打印详细日志 |
| `脚本/collect_api.py` | 旧版 API 采集（保留备用） |
| `脚本/check_ebay_api.py` | 密钥连通性探测（换 token + 试搜） |
| `99_归档/紫鸟采集_20260915/` | **紫鸟链路已封存**（保留 `--mode ziniao` 可运行） |
| `脚本/analyze.py` | 词频、相似属性合并、价格段、拼 title |
| `脚本/ziniao_runtime.py` | 紫鸟启停、开店、CDP 就绪等待 |
| `脚本/sites.py` | 站点、配送国家、邮编 |
| `启动器/关键词选品.bat` | 双击入口 |

## 怎么跑

1. 复制仓库根目录 `config.example.json` 为 `config.local.json`，填紫鸟账号；若走 API 再填 `client_id` / `client_secret`
2. 启动器会优先用旁边 `ebay看板\runtime\python.exe`

```text
紫鸟模式（默认，要店铺名）:
  python 脚本\run_keyword_research.py --store 店铺名 --keyword "wireless earbuds" --site uk

需要 item specifics 时才进详情页（默认不进，风控考虑）:
  python 脚本\run_keyword_research.py --store 店铺名 --keyword "..." --site uk --detail 10

官方 API（现在用沙盒）:
  python 脚本\check_ebay_api.py sandbox
  python 脚本\run_keyword_research.py --mode api --env sandbox --keyword iphone --site us --max 20

只分析已有 JSON:
  python 脚本\run_keyword_research.py --mode json --from-json 某次采集.json --keyword "wireless earbuds" --site us
```

可用站点：`us` `uk` `de` `au` `fr` `es` `it` `ca` `hk`

结果在 `输出/`，一个 xlsx（多 sheet）+ 一份完整 json。

## 默认走官方 API（2026-09-15 起的生产方式）

实测口径（生产环境，120 条，见 `02_soldeazy详情补数/文档/接口探查记录_20260914.md` 附二）：

```text
python 脚本\run_keyword_research.py --mode api --keyword "wireless earbuds" --site uk --max 120
```

| 项 | 实测 |
|---|---|
| item specifics 覆盖 | **120/120 = 100%**（`getItem.localizedAspects`） |
| 刊登必填项 | Brand 100% / Connectivity 100% / Colour 99.2% / Type 99.2% / Model 92.5% |
| 类目 | `categoryId` + `categoryPath` + `categoryIdPath` 100%；**第二类目**来自搜索侧 `leafCategoryIds` |
| 图片 / 描述 / 卖家 / 所在地 | 全部 100% |
| 调用消耗 | **1 次 search + 120 次 getItem = 121 次**，串行 145~150 秒 |
| 配送地 | header `X-EBAY-C-ENDUSERCTX` 精确指定，GB/US/DE 实测生效 |
| 写操作 | **零**（不碰任何账号数据） |

### 凭据（按优先级）

```text
1. 环境变量 EBAY_USER_TOKEN
2. 02_soldeazy详情补数/token.local.txt        ← 当前使用（已 gitignore）
3. config.local.json 的 ebay_api.client_id / client_secret（client_credentials 换 token）
环境: --env production（默认）| sandbox
```

### `--detail` 语义

```text
-1  全部条目都取详情（API 模式默认，实测 100% 覆盖）
 0  只搜索不取详情（紫鸟模式默认）
N>0 只取前 N 条
```

## 推荐标题改由 DeepSeek 生成（默认开启）

```text
不用 LLM（回退规则版拼装）:  --no-llm
```

### 为什么换掉规则版

规则版拼装的实测成绩 vs 文档要求：

| 指标 | 规则版 | 竞品真实标题 | DeepSeek 版 |
|---|---|---|---|
| 字符数中位 | 51 | **79** | **78** |
| ≥70 字符占比 | 5/30 | 110/120 | **30/30** |
| 高重复标题（>2次）保留 | **0/7** | — | **7/7** |
| 读起来像真人商品标题 | ❌ 规格堆叠 | — | ✅ |

### 设计要点

- **素材由脚本算好再喂**：高评分关键词表（含位置/搜索价值/差异化/综合评分）、修饰词三分类、
  结构模板、竞品完整标题、真实属性值 —— 全是本地已算出的真数据，不让模型凭空编
- **品牌判断交给 LLM**（用户明确）：脚本**不再用关键词黑名单否决**模型输出，只做机械校验
  （≤80 字符、无逗号、同标题不重复词、标题之间不重复）。原因：
  黑名单会把兼容性描述（`for Samsung`）误判为品牌并整条否决，
  且与"高重复标题原样保留"直接冲突，导致永远凑不满 30 条

- **硬约束写进 prompt + 脚本二次校验**：不达标就把问题反馈给模型重试（最多 4 轮），
  每轮合规的标题累积进候选池，最后 `select_best()` 择优 30 条（优先高重复标题、长度接近 80、
  关键词评分高、彼此词汇重叠低）
- **失败必回退**：网络/JSON/校验异常 → 自动用规则版，不中断流水线
  （⚠️ 规则版只是兜底，**不是交付物**：长度普遍 50 上下、是关键词堆叠形态。
  用 `--no-llm` 或 LLM 失败时产出的标题**不符合要求**，不要拿它交付）

### 清洗口径（2026-09-15 修正）

**必须清洗掉**：

| 类别 | 例子 | 为什么 |
|---|---|---|
| 品牌名当自家品牌用 | `Sony` / `MPOW` / `JBL` / `AirPods` | 冒充原厂，侵权风险 |
| **竞品型号编号** | `PRO4` / `LP40` / `A6S` | 别家型号，同样是侵权风险 |

**可以保留**：适配机型描述（`for iPhone` / `for Samsung` / `for Android`）、
品类词（`TWS` / `In-Ear` / `Earbuds` / `Pods`）、规格词（`5.4` / `IPX4` / `ENC`）。

> 这里踩过一个我自己造的坑：prompt 里曾写着"**不要**把型号编号（PRO4 / LP40 / A6S）
> 当品牌词删掉 —— 这是买家搜索词，删了会损失流量"，与需求里的"品牌/型号词一律不进标题"
> **直接矛盾**。结果是 30 条里残留 `MPOW`（当成自家品牌用）和 `PRO4`（竞品型号）。
> 已改成明确的两类清洗清单，重跑后这两类词**清零**。

### 实测表现（120 条 / wireless earbuds / uk）

```
候选池 41 条 → 择优 30 条（含 7/7 高重复标题）
字符 73~80，中位 79；≥70 字符 30/30；=80 字符 12 条
无逗号、无超长、同标题无重复词、30 条互不重复（机械校验 30/30 通过）
品牌/型号词残留：MPOW 0 条、PRO4 0 条、Sony/JBL/Apple 0 条
  （仅剩 `for iPhone Samsung Android` 这类**兼容性描述**，见上文口径）
token 用量：约 9.3k / 次（2 轮）；耗时约 10~20 秒
```

### 凭据

```text
config.local.json → deepseek.api_key（已 gitignore）
或环境变量 DEEPSEEK_API_KEY
模型默认 deepseek-chat；接口 https://api.deepseek.com/chat/completions（JSON 模式）
```

### 花费（实测，2026-09-15）

**一次完整生成（30 条标题 = 2 轮 API 调用）实测约 ¥0.0046，上界 ¥0.012** —— 也就是**半分钱到 1 分钱**。

真实用量（DeepSeek 返回的 usage，不是估算）：

```text
prompt_cache_hit_tokens   7296   ← 缓存命中，¥0.02/百万
prompt_cache_miss_tokens   781   ← 未命中，  ¥1/百万
completion_tokens         1221   ← 输出，    ¥3/百万  → 占成本 80%
```

**为什么命中率有 90%**：多轮重试时第 2 轮的 prompt 是第 1 轮的**严格前缀**
（代码里是 `prompt = prompt + 反馈`），DeepSeek 的前缀缓存直接命中。
早期版本没有把缓存明细打出来，所以按"全部未命中"估会高估约 2.5 倍 ——
现在 `llm_titles.estimate_cost()` 用真实命中/未命中算，每轮跑完都会打印：

```
[LLM] 花费估算：约 ¥0.0046（命中 7296 / 未命中 781 / 输出 1221 tokens）
```

单价写在 `llm_titles.PRICE_DEFAULT`，**可在 `config.local.json` 覆盖**（单价会变，以官网为准）：

```json
"deepseek": {"price": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 3.0}}
```

成本大头是**输出**（占 80%），输入因为有缓存几乎不花钱。所以：
- 按关键词数量线性增长：**100 个关键词约 ¥0.46**（上界 ¥1.17）
- 想再省一点：DeepSeek 是峰谷计费，谷时段更便宜；但一次才半分钱，**省这个意义不大**

### 注意

- LLM 标题每次约 9k token；批量多关键词时注意成本

## eBay 凭据持久化（2026-09-15 新增 `脚本/ebay_auth.py`）

**原来的问题**：`token.local.txt` 里放的是 **access token**。eBay 的 access token 只有
**2 小时**寿命，而且它**本身不可续期** —— 所以每跑一次都要人去开发者后台重新生成、再贴一遍。
这不是脚本写得烂，是"存的东西类型不对"：能持久的只有下面两种。

| 凭据 | 寿命 | 怎么拿 | 评价 |
|---|---|---|---|
| **refresh token** | 约 18 个月 | 授权码流程（浏览器同意一次） | **推荐**，脚本自动换 access token |
| **client_id + client_secret** | 长期 | 后台 App ID / Cert ID | 可直接换 app token；但权限范围比用户令牌小 |

取 token 的顺序（失败逐条报告，不静默吞）：

```text
1. 显式传入 token=
2. 环境变量 EBAY_USER_TOKEN / EBAY_ACCESS_TOKEN     ← 临时覆盖
3. 缓存 token.local.json 里未过期的 access_token
4. 缓存里的 refresh_token → grant_type=refresh_token  ← 持久化靠这条
5. token.local.txt（兼容旧的手工令牌）
6. client_credentials（需 client_id/secret 配对有效）
```

- access token 写进**缓存文件**（带过期时间），2 小时内复用；**提前 5 分钟**自动续期
- 收到 **401 自动换令牌并重试一次**（`_get` 与 `getItem` 都做了），长任务不会再中途崩
- 被 401 否掉的来源会在本次运行内**拉黑**，换下一条路 —— 贴个过期令牌也不会卡死流程
- 8 线程并发时只会续期一次（内部加锁），不会 8 个线程同时去打 token 接口
- 缓存文件 `02_soldeazy详情补数/token.local.json` 已被 `.gitignore` 的 `*token*.json` 覆盖

```bash
python 脚本/ebay_auth.py --check                # 体检：凭据对不对、哪条路真能调通 API（会真打一次）
python 脚本/ebay_auth.py --login                # 打印授权链接（拿 18 个月 refresh token）
python 脚本/ebay_auth.py --code "<回调URL>"      # 把 code 换成 refresh token 并落盘
python 脚本/ebay_auth.py --save-user-token <t>  # 手工令牌写进缓存
```

`--check` **不会只看"文件里有没有字"** —— 它会真打一次 Browse API。
（坑：`token.local.txt` 里躺着一个 2 小时前就过期的令牌，只检查"文件非空"会误报健康，
所以"读到一个令牌字符串" ≠ "这个令牌能用"。）

### 实测状态（2026-09-15）—— 已解决

**根因（拿开发者后台截图逐字比对后确认）**：`config.local.json` 里的两个字段都填错了 ——

| 字段 | 应该填 | 实际填的 | 问题 |
|---|---|---|---|
| `client_id` | 与目标环境一致的 App ID | `BETA-SBX-…-d079` | 是**沙箱** App ID，却要打 production |
| `client_secret` | **Cert ID**（`PRD-…` / `SBX-…`） | `16880a0b-a69a-4ac8-91fd-93986bb62f8a` | 这是页面上那个 **Dev ID**（开发者 ID），**根本不参与 OAuth** |

Dev ID 是 UUID 形态（`8-4-4-4-12`），Cert ID 是 `PRD-…` / `SBX-…` 形态 —— 两者用途完全不同。
填了 Dev ID，eBay 只会回 `invalid_client`，而且**报文和"值写错了"完全一样**，
所以之前几十次尝试全白跑，也解释了为什么 production / sandbox 报的是同一个错。

修好之后：

```text
client_id      -BETA-PRD-f82b86fbd-f4f4c153     ← 注意：这个 App ID 确实以 "-" 开头（28 位）
client_secret  PRD-examplecert000-0000-0000-0000-0000
client_credentials → HTTP 200，expires_in=7200
Browse 探针        → HTTP 200，total=67176        ✅
```

已加进 `--check` 的**凭据形态自检**（`credential_warnings()`），这类错误现在一眼可见：

```text
⚠️ 凭据检查  client_secret 是 UUID 形态 → 这是 **Dev ID**，不是 Cert ID！OAuth 的 client_secret 必须填 Cert ID
⚠️ 凭据检查  client_id 是**沙箱**(SBX) App ID，却要打 production —— 环境不匹配
```

它还会查：App ID 与 Cert ID 是否来自**同一套密钥集**（沙箱 App ID 配生产 Cert 这类混搭）、
App ID 是否缺 `-PRD-` / `-SBX-` 标记。**注意：形态检查通过 ≠ 密钥集真的生效**，
后者只有真打一次 API 才能确认，所以 `--check` 最后一定会发请求。

**现在这条链路已经不需要任何人工贴 token 了**：每次运行自动 client_credentials 换 token（2 小时有效），
缓存复用 + 到期自动重换 + 401 自动重试。`refresh_token`（18 个月）那条路留作备用，
需要后台 User Tokens 页的 **RuName** 才能跑 `--login`。

> `item_sales/search`（售出数据）需要**用户令牌 + eBay 额外审批**，app token 拿不到 ——
> 与"售出数据不在需求内"的结论一致。


## 采集条数：默认 200（2026-09-15 调整）

eBay Browse API 的 `limit` 上限就是 **200**，**一次请求就能拿满 200 条**，
所以默认值从 120 提到 200（用户口径：不必先截断成 120 再处理）。

```text
--max 200（默认）  → 1 次 search + 200 次 getItem，8 线程约 20~29 秒
--max 400          → 自动翻页（offset 必须是 limit 的整数倍）
```

实测（`wireless earbuds` / uk / 生产环境）：`{'search': 1, 'getItem': 200}`，
采集明细 **200 行 × 40 列**，`localizedAspects` 覆盖 100%，总耗时 29.1 秒。

## 壳程序与共享目录部署（2026-09-15）

部门共享目录 `\\192.168.120.11\Ebay部门\ebay看板`：

```text
关键词选品采集.bat                 ← 双击入口（内容纯 ASCII）
keyword_research\
    scripts\  *.py + config.json   ← 代码与凭据
    输出\     <关键词>_<时间>_<站点>.xlsx
    日志\     关键词选品_<时间>.log（完整控制台日志）
    README_使用说明.txt
```

- **文件名口径**：`关键词 + 时间 + 站点`，如 `wireless_earbuds_20260915_100852_uk.xlsx`
  （同名 `.json` 是原始数据，含未截断的完整 description）
- **产物放独立文件夹**：`keyword_research\输出\`
- **交互顺序：先选站点，再填关键词**（用户要求）——
  站点可单选/多选（`1 3 5`）或 `A` 全选；关键词多个用逗号分隔。
  跑完可选 `Y` 继续填关键词（站点不变）/ `S` 换站点 / `N` 退出
- **多关键词 × 多站点**：`wireless earbuds,phone case` × `uk us` = 4 份独立产物
- **关键词按逗号拆，绝不按空格拆** —— `wireless earbuds` 是**一个**关键词。
  （踩过：早期按空格拆，产物变成 `wireless_..._uk.xlsx` + `earbuds_..._uk.xlsx`）
- **关键词里的隐形字符会被清掉**（BOM / 零宽空格 / 不换行空格）——
  从 Excel 或聊天窗口粘贴很容易带上，`str.strip()` 去不掉，
  最后会变成"1 个看不见的关键词"一路跑到 eBay 报 400
- 复用共享目录已有的 `runtime\python.exe`（Python 3.12.10），不额外占 400MB
- 带参数可跳过交互（自动化/排查用）：`关键词选品采集.bat "wireless earbuds" uk`
- 凭据体检：`关键词选品采集.bat check`

### 为什么 bat 内容纯 ASCII、菜单写在 Python 里

第一版把代码放在 `关键词选品\脚本\`、bat 里写中文路径，结果在**控制台代码页不是 936**
的机器上直接报"找不到采集脚本"（实测代码页 65001 时，bat 里的中文路径被按错误代码页解析）。
**bat 里的中文完全受 cmd 代码页支配**，没法保证每台机器一致；
而 Python 3.6+ 在 Windows 控制台走 `WriteConsoleW`（PEP 528），
中文输入输出与代码页无关。所以：bat 只转发，中文菜单/日志都在 `kw_menu.py`。

### 关于"共享盘上双击能不能用"的验证

- **带参数模式**（不读键盘）直接从共享盘跑通：200 条、exit 0、产物落在共享盘
- **交互模式**：用 `start` 开全新控制台窗口（等同双击）启动 bat，
  6 分钟后 python 进程仍活着 → 说明它**阻塞在 `input()` 等键盘**，交互可用
  （⚠️ 注意：`cmd /c bat` 配**重定向 stdin** 时子进程会立刻 EOF ——
   这是 Windows 的行为，两行的最小 bat 也能复现，与程序无关；
   所以"用重定向喂输入"测不出双击的真实情况，别被它误导）
- 菜单逻辑本身用脚本化输入逐条验证（空关键词重问、站点多选、确认、跑完继续），
  并有单测钉住"站点先问、关键词后问"这个顺序


## 连通性自检（2026-09-15）

`文档/_test_connectivity.py` 一次过完对外依赖，7 项全通：

```
1. eBay OAuth（换 token）            ✅
2. Browse: item_summary/search      ✅
3. Browse: getItem（item specifics） ✅
4. Taxonomy: 默认类目树               ✅ categoryTreeId=3（EBAY_GB）
5. Taxonomy: 类目属性（必填/推荐/可选）   ✅
6. Taxonomy: 属性允许值               ✅
7. DeepSeek 接口                     ✅（请求 deepseek-chat，服务端实为 deepseek-flash）
```

**Taxonomy API 用同一套 client_credentials 令牌就能调**，不需要额外授权：

```
GET /commerce/taxonomy/v1/get_default_category_tree_id?marketplace_id=EBAY_GB
GET /commerce/taxonomy/v1/category_tree/{tree}/get_item_aspects_for_category?category_id=112529
```

实取 `EBAY_GB` 类目 112529 Headphones 的结论：

| 字段 | 含义 | 取值 |
|---|---|---|
| `aspectRequired` | **硬性必填** | 5 个 true：Brand、Connectivity、Model、Colour、Type |
| `aspectUsage` | eBay 推荐程度 | RECOMMENDED 16 / OPTIONAL 10 |
| `aspectMode` | 填法 | FREE_TEXT 22 / SELECTION_ONLY 4（只能从候选值里选） |
| `itemToAspectCardinality` | 单值/多值 | SINGLE 19 / MULTI 7 |

⚠️ **`aspectRequired` 与 `aspectUsage` 是两个独立字段**，别只看后者
（我第一版只看了 `aspectUsage`，误报"0 个必填"）。

属性清单已缓存到 `01_关键词选品/数据/taxonomy/`，做"该填什么属性 / 竞品属性地图"时读本地即可，
不额外消耗 eBay 额度。

### ⚠️ 三层区分：有配额 ≠ 有权限 ≠ 能调通（2026-09-24 纠正）

我曾把"有配额"说成"可用"，这是**表述错误**，会让能力判断失真。准确的区分是三层：

| 层次 | 判据 | 实测（截图里那 15 个 Sell API） |
|---|---|---|
| **有配额** | `rate_limit` 额度表里有该资源 | 13/15（Stores、Inventory Mapping 没有） |
| **路径存在** | 调用返回 403/400（而非 404） | ≥9 项实测确认 |
| ****现在能调通** | 返回 200 | **0 项** —— 全部需要**用户令牌** |

反例（配额有、但永远调不通）：`buy.marketplaceinsight`（eBay 书面拒绝）、
`sell.research.product_insight`（无端点、无申请入口）。

### 能力应分两层报告

**第一层：现在就能用（7 项，application token 即可）**

```
Browse 搜索 / Browse 详情 / Taxonomy 类目属性 / Taxonomy 类目建议
Feedback 评价（销量近似）/ Translation 翻译 / Developer Analytics 额度查询
```

**第二层：账号授权（RuName + OAuth）后追加 9~15 项**

| API | 配额/天 | 能拿到 | 对选品价值 |
|---|---|---|---|
| **Fulfillment** | 100,000 | 自家订单 | ★★★ 校准留评率 |
| **Finances** | 15,000 | 自家成交金额/费用 | ★★ |
| **Analytics** | 100~400 | 自家流量/转化 | ★★ |
| **Inventory** | 2,000,000 | 自家库存 | ★ |
| **Marketing Ads / Promotion** | 100,000 / 10,000 | 自家广告效果 | ★ |
| **Metadata** | 5,000 | 类目元数据 | ★ 补充 Taxonomy |
| **Recommendation** | 5,000 | 商品建议 | ★ |
| **Sell Feed** | 100,000 | 批量任务 | ★ |
| Account / Negotiation / Compliance / Logistics | — | 账号/议价/违规/物流 | 与选品无关 |
| Stores / Inventory Mapping | 无配额 | 店铺装修 / 库存映射 | — |

**完整能力上限 ≈ 7 + 13 ≈ 20 项**，门槛就是**一次账号授权**。

## ★★ 销量 + 评论数据：已通过 Feedback API 拿到（2026-09-22）

**这是本轮最重要的突破** —— 此前"销量数据拿不到"的结论**要修正**：通过卖家的
**反馈（评价）接口**可以反推出竞品的成交结构与买家评论，**完全合规、不需要审批、不需要用户授权**。

### 可直接调用的方式（app token 即可）

```python
# 1) 用这个 scope 换令牌（应用级，client_credentials 即可，无需卖家授权）
scope = "https://api.ebay.com/oauth/api_scope/commerce.feedback.readonly"

# 2) 查任意卖家的评价（user_id 接受用户名，也接受公开用户 ID）
GET /commerce/feedback/v1/feedback
    ?user_id=<卖家用户名>&feedback_type=FEEDBACK_RECEIVED&limit=200
```

**注意三个参数的坑**（逐个试出来的）：

| 参数 | 必填 | 值 |
|---|---|---|
| `user_id` | ✅ | 卖家用户名（**不是** `username=`，那样会报 501000） |
| `feedback_type` | ✅ | `FEEDBACK_RECEIVED` 或 `FEEDBACK_SENT`（不填报 501001） |
| `limit` | — | **上限 200**（写 500 也只返回 200） |

### 返回里能拿到什么（真实数据，卖家 `jaza_trades`）

```json
{"pagination": {"total": 7047, "count": 200},
 "feedbackEntries": [{
   "orderLineItemSummary": {
     "listingId": "177937693479",
     "listingTitle": "ROCKBROS Bicycle Smart Rear Light ...",
     "listingPrice": {"value": 5.99, "currency": "GBP"},
     "orderLineItemAttributes": [{"name": "SOLD_AS_BEST_OFFER", "value": "false"}]},
   "commentType": "POSITIVE",
   "feedbackComment": {"commentText": "Order delivered on time with no issues"},
   "feedbackRatings": [{"ratingType": "ON_TIME_DELIVERY", "value": "..."}],
   "providerUserDetail": {"role": "BUYER", "feedbackScore": 602}}]}
```

**能推出什么**（实测聚合结果）：

| 想要的 | 怎么来 |
|---|---|
| **竞品单品销量榜** | 按 `listingTitle`/`listingId` 聚合评价条数 → 实测得到"OneBlade 替换刀头 61 单 / 气泵 24 单 / 车灯 18 单" |
| **累计成交规模** | `pagination.total` = 该卖家收到的评价总数（实测 7,047） |
| **好评率** | `commentType` 分布（实测 POSITIVE 196 / NEUTRAL 3 / NEGATIVE 1 = 98%） |
| **真实成交价** | `listingPrice`（是成交价，不是标价） |
| **买家评论原文** | `feedbackComment.commentText` |
| **议价成交占比** | `orderLineItemAttributes` 里的 `SOLD_AS_BEST_OFFER` |
| **是否匿名/自动评价** | `automatedFeedback`、`providerUserDetail.userId` |

**额度**：`commerce.feedback` **5,000 次/天**（已在我们 app 的额度表里），每次最多 200 条评价。

### 必须如实说明的限制

1. **只覆盖"留了评价的订单"** —— 不是全部成交。所以它是**相对指标**（用于横向比较竞品谁卖得好），
   不能当成绝对销量数字
2. **时间粒度粗**：`transactionPeriod` 只给 `LESS_THAN 90 DAY` 这类窗口，**没有精确成交日期**
3. **需要卖家用户名** —— 正好我们有（采集明细里的 `seller` 字段）
4. 美国用户的用户名可能被合规隐藏（返回不可变 `userId`）
5. `feedback_rating_summary` 还需要试对 `rating_type` 参数（暂未通过）

## eBay API 能力清单（2026-09-22 更新：官方额度接口 + 翻译 API 打通）

### ★ 官方额度查询接口（此前几轮一直查不到的问题解决了）

```
GET https://api.ebay.com/developer/analytics/v1_beta/rate_limit/
（用 application token 就能调，不需要用户授权）
```

返回 **140 条资源** —— 这实际上是**本 app 被授权的 API 完整清单 + 每日额度**，
比翻文档猜路径可靠得多。踩坑记录：此前探 `/sell/developer_analytics/v1/rate_limit`
与 `/developer_analytics/v1/rate_limit` 都 404 —— **正确路径是
`/developer/analytics/v1_beta/rate_limit/`**（少了 `_beta`、少了末尾斜杠都会 404）。

关键条目（摘录）：

| 资源 | 额度/天 | 实测 |
|---|---|---|
| `sell.research.product_insight`（Sell / **ProductResearch** V1） | 5000 | ★ 额度在，但**找不到文档/scope/端点** |
| `buy.marketing.most_watched_items` | 5000 | 路径待查 |
| `commerce.feedback`（Feedback API） | 5000 | 路径存在（403，需授权） |
| `commerce.translation.translate` | 5000 | ✅ **可用（app token）** |
| `buy.feed.snapshot` | 75000 | 403 |
| `commerce.catalog` | 10000 | 403 |
| `buy.browse` | **5000** | ✅ 正在用（额度由此确认） |
| `buy.marketplaceinsight` | 5000 | 403（**额度有、权限没给**） |
| TradingAPI（GetItem / GetOrders / GetFeedback …） | 各 5000+ | 需用户令牌 |

### ✅ Translation API 已可用（对 9 个站点直接有用）

```
POST /commerce/translation/v1_beta/translate
{"from":"en","to":"de","text":["<标题>"],"translationContext":"ITEM_TITLE"}
```

- **必须带 `translationContext`**（不填报 `110003 Context is not supported`）
- **单次只能 1 段文本**（2 段即报 `110004 Maximum number of input text reached`）
  → 额度换算：**5000 段文本/天**
- 实测效果（真实标题 → 4 种语言，eBay 自家的电商优化翻译）：

```
原文   TWS Wireless Bluetooth Earphones Air In-Ear Pods Buds for iPhone Samsung Android
德语   TWS Wireless Bluetooth Kopfhörer Air In-Ear Pods Buds für iPhone Samsung Android
法语   TWS Écouteurs Bluetooth sans Fil Air Intra-Ear Pods Buds pour iPhone Samsung Android
西语   Auriculares inalámbricos Bluetooth TWS Air In-Ear Pods Buds para iPhone Samsung Android
意语   TWS Auricolari Bluetooth Wireless Air In-Ear Pods Buds per iPhone Samsung Android
```

### 卖家端（Sell）API 全景与前置条件

`/sell/...` 下的订单、财务、库存、营销、反馈、推荐、合规、元数据、Feed 等
**全部需要用户令牌（卖家授权）** —— 实测均为 `403 errorId 1100`。

**打通它们的唯一前置条件是 `RuName`**（eBay 后台 User Tokens 页的"重定向 URL 名称"）：
有它就能走授权码流程拿用户令牌 + 18 个月 refresh token，而 `ebay_auth` 里的
refresh token 自动续期机制**已经写好**，接上即可。当前 `config.local.json` 的
`ru_name` 仍为空。

> **更正（2026-09-22）**：此前我写过"sell/analytics 不在本 app 额度清单里"——**那是错的**，
> 当时只看了额度表的前半段。完整表（146 条资源）里**有**：
> `sell.analytics.traffic_report` 100/天、`seller_standards_profile` 100/天、
> `customer_service_metric` 400/天（与公开默认额度表一致）。
> 它调不通（403）是**因为需要用户令牌**，不是没被授予。
> 教训：**别拿"表的前半段"下结论**。

### 公开默认额度表 vs 我们 app 的实际额度（精确对照）

公开的 Sell"API Call Limits"表是**通用默认值**；`rate_limit` 接口返回的才是
**"这个 app 到底被授予了什么"**。两者差异如下：

| 类别 | 条目 |
|---|---|
| **我们有、公开 Sell 表里没有** | ★ **`sell.research.product_insight`（ProductResearch V1，5000/天）** ← 销量 API<br>`commerce.feedback`（Feedback API，5000/天）<br>`buy.marketplaceinsight`（Marketplace Insights，5000/天，Buy 家族） |
| **公开表里有、但我们没有** | Merchandising、Product API、Product Metadata、Inventory Mapping、Business Policies（已弃用） |
| 两边一致（我们也有） | Account、Finances、Analytics(流量 100/天)、Notification、Feed、Inventory、Media(document)、Catalog、Charity、Metadata、Taxonomy、Marketing(Promotion/Ads)、Recommendation、Negotiation、Fulfillment、Logistics、Post-Order(4 资源)、Compliance、Identity、Trading API、Translation |

**"公开表里没有、我们额度里却有"这个矛盾，就是 Product Research API 属于未公开受限接口的最强证据。**

## eBay API 能力清单（2026-09-15 首次普查）

逐个打接口 + 逐个申请 scope 得到的结论，不靠二手资料。

### 现在就能用（基础 `api_scope`）

| API | 能给什么 |
|---|---|
| Browse `item_summary/search` | 搜索：价格/广告位/卖家/上架时间/库存阈值/议价与顶评标记/**拍卖出价次数** |
| Browse `getItem` | 详情：item specifics、类目路径、图片、描述、库存状态 |
| Browse search + **`fieldgroups=EXTENDED`** | **卖家反馈分/好评率**、上架时间、发货国、优惠券、运费 |
| Taxonomy `get_item_aspects_for_category` | 类目必填/推荐/可选属性 + 属性允许值 |
| Taxonomy `get_category_suggestions` | 按关键词猜类目 |

> `getItem` **不支持** `fieldgroups=EXTENDED`（errorId 11501），只有 search 支持。

### 拿不到的（403 `errorId 1100` + scope `invalid_scope`）

| 想要的 | 接口 | 门槛 |
|---|---|---|
| **销量 / 最近 90 天成交** | Marketplace Insights `item_sales/search` | **eBay 单独审批** |
| 促销/折扣商品 | Buy Deal `deal_item` | 审批 |
| 批量商品快照 | Buy Feed `item_snapshot` | 审批 |
| 商品目录（epid 聚合） | Catalog `product_summary/search` | 审批 |
| 批量取详情 | Browse `item/get_items` | `buy.item.bulk` scope |
| 店铺流量/转化、广告花费、库存、订单 | Sell Analytics / Marketing / Inventory / Fulfillment | 审批 **+ 用户令牌** |

**实测：11 个 scope 里只有基础 `api_scope` 能拿到令牌** —— 其余全部
`invalid_scope The requested scope is invalid, unknown, malformed, or exceeded`。

### 销量与评论的真相

- **销量**：公开 API 里**只有** Marketplace Insights 能给，且需审批。没有审批 = 拿不到。
- **评论**：eBay **没有公开的商品评论接口**。能拿到的只有**卖家层面**的
  `seller.feedbackScore`（反馈分）与 `seller.feedbackPercentage`（好评率），
  那是卖家信誉，不是商品评价。

### 现成可用的"热度替代信号"

| 信号 | 字段 | 说明 |
|---|---|---|
| **拍卖出价次数** | `bidCount` | 唯一直接的"有人在抢"信号；按 `filter=buyingOptions:{AUCTION}` 取 |
| 卖家集中度 | `seller.username` | 头部卖家垄断程度 |
| 卖家实力 | `seller.feedbackScore/Percentage` | 反馈分、好评率 |
| 上架时间 | `itemCreationDate` / `itemOriginDate` | 新品活跃度（实测样本跨 2023-03 ~ 2026-09） |
| 库存厚度 | `estimatedAvailabilities[].availabilityThreshold` | `MORE_THAN 10` = 至少 10 件 |
| 议价/顶评 | `buyingOptions` 含 `BEST_OFFER`、`topRatedBuyingExperience` | 实测 50 条里 12 条支持议价、15 条顶评 |

## 输出结构：5 张子表（2026-09-15 合并）

用户要求"子表数量减到四五个、相关内容合并"，从 13 张合并为 5 张：

| 子表 | 包含内容 |
|---|---|
| **市场概况与价格** | ① 市场概况（关键词/站点/条数/数据来源/广告位/语言/类别/类目ID）② 价格区间与占比 ③ **各价格带的广告位占比** ④ **广告位出现在第几位的分布** ⑤ **广告位位次概览** ⑥ 价格分位 ⑦ 口径说明 |
| **品牌壁垒** | ① 结论 ② 各价格带真品牌占位率 ③ 各品牌真实份额 ④ brand 字段原始取值分布 ⑤ 辅助：标题品牌词提及率 ⑥ 辅助：各价格带标题词提及率 |
| **关键词与标题** | 关键词评分（位置/搜索价值/差异化/综合评分）+ 修饰词三分类 + 类别说明 + 结构模板 + 推荐标题 30 条 + 策略建议 |
| **采集明细** | 200 行 × 40 列（前 8 列是定位用：`position / item_id / legacy_item_id / item_url / 是否广告位 / is_sponsored / 广告位标记来源 / title`；后接 item specifics / 类目 / 图片 / 描述 / 卖家 / 所在地） |
| **基础统计** | 完整 title 重复 + title 词频 + 属性词频 + 主类目 + 第二类目 |

### 广告位分析（2026-09-15 新增）

需求第 6 条是"标记是否广告位"。只给一个 true/false 不够用，所以把广告位拆成 4 个角度输出：

| 位置 | 内容 | 回答什么问题 |
|---|---|---|
| 采集明细前 8 列 | `是否广告位` / `is_sponsored` / **`广告位标记来源`** | 每一条到底是不是广告位、**依据是什么**（来自 `priorityListing`） |
| 市场概况第①段 | 广告位条数（**带占比%**）、广告位均价、全部商品均价、投放最凶价格带 | 这个类目广告多不多 |
| 市场概况第③段 | 各价格带：商品数 / 广告位条数 / 广告位占比% / 自然位条数 / **投放强度** | **哪一段卖家在砸广告**（白牌要避开哪一段） |
| 市场概况第④⑤段 | 位置区间分布（每 10 位一桶）+ 位次概览（首个广告位在第几位 / 平均位次 / 位次范围 / **前 10 位里有几条广告**） | 广告压在头部还是分散；新品从哪些位次切入是纯自然位 |
| 关键词与标题的「eBay平台建议」 | 广告位位置分布结论 + 无广告位的位次段 | 直接给可执行结论 |

**标记来源只有一个，不猜 DOM**：`priorityListing` 来自 eBay 官方 Browse API 的
`item_summary/search` 响应（`_map_summary()` 写入 `is_sponsored`，同时记 `广告位标记来源`）。
旧紫鸟链路那种"扫卡片 HTML 找 sponsored 字样"的做法会虚高，已随链路一起封存（见 `99_归档/`）。

`wireless earbuds` / uk / 120 条实测：

```text
广告位 14 条（11.7%）；广告位均价 19.91 vs 全部商品均价 12.74（广告位明显更贵）
各价格带投放强度：0-5 → 无广告(0%) ｜ 5-8 → 无广告(0%) ｜ 8-10 → 15.4%
                 10-13 → 40%（广告最凶） ｜ 13-16 → 7.1% ｜ 16-20 → 26.7% ｜ 20+ → 21.4%
位置分布：1-10 → 3 条(30%) ｜ 11-20 → 3 条(30%) ｜ 21-30 → 2 条 ｜ 31-40 → 4 条
         41-50 ～ 101-110 每段都是 0 条（纯自然位） ｜ 111-120 → 2 条
位次概览：首个广告位在第 2 位、平均位次 35.3、前 10 位里 3 条广告（30%）
```

### 品牌壁垒的主口径已换成官方 brand 字段

**为什么要改**：标题词频检测会把**兼容性词**当品牌 —— 实测标题里 `samsung` 命中 33 条(27.5%)，
但 eBay 官方 `brand` 字段里 **samsung 一次都没出现**（那些是 "for Samsung" 的兼容描述）。

| 口径 | 数据来源 | 性质 |
|---|---|---|
| **主口径** | `brand` 字段 / `item_specifics.Brand` | 权威、结构化；与详情页 Brand 完全一致 |
| 辅助（第⑤⑥段） | 标题词频 + 品牌词表 | 只反映**标题营销用词**，含兼容性词，**不代表份额** |

实测同一份数据两个口径的差异：

```
主口径：真品牌占位 35.8%（43/120）、白牌 64.2%、品牌 31 种；Sony 6 条为最高
        各价格带真品牌占位率：0-5 → 0% ｜ 5-8 → 28.1% ｜ 8-10 → 46.2% ｜ 10-13 → 10%
                            13-16 → 64.3% ｜ 16-20 → 60% ｜ 20+ → 64.3%
        → 结论：白牌切入口在 0-5 段（真品牌占位 0%）
辅助口径：标题 samsung 提及 33 条（27.5%）← 兼容性词，不代表品牌份额
```

`brand` 字段里的卖家乱填值（`InEar` / `Tws` / `Branded` 等）会在第④段标为"乱填/品类词"并**排除**在真品牌统计外。

### 并发取详情（默认开启）

```text
--workers 8     默认 8 线程，上限 16；--workers 1 = 串行
```

| 模式 | 120 条耗时 | 说明 |
|---|---|---|
| 串行 | 145 秒 | 逐条 + 0.05s 间隔 |
| **并发 8 线程** | **11.5 秒** | 每线程独立 requests.Session，提速 12.6 倍 |

并发下数据完整性不变（120/120 详情成功、item specifics 100%、第二类目正常）。
新增 `--workers` 参数，`EbayApi.collect(workers=N)`。

### 已知边界

- `limit` 上限 **200**（>200 报 errorId 12006）；`offset` 必须是 `limit` 的整数倍
- **搜索结果里没有 item specifics**，必须逐条 `getItem`
- token 有有效期，过期后需重新生成（会明确报 HTTP 401，不静默）
- 逐条详情是串行请求，120 条约 2.5 分钟；如需加速可改并发（未实现）

## 默认不进详情页（风控）

- 搜索页 **1 次加载**就能拿满 120 条：`item_id` / `legacy_item_id` / `item_url` / 价格 / 广告位 / 末级类目 ID 全覆盖
- **广告位(`promoted`)与末级类目(`leafCat`)来自搜索页内嵌 JSON**，与卡片按 itemId 对齐，不需要进商品页
- `item specifics` 搜索页没有内嵌数据块、只能进详情页 → 改成**默认不采**（`--detail 0`），下游按 `item_id` 自行取数
- 实测过的风控信号：`net::ERR_CONNECTION_CLOSED`、`TargetClosedError`、eBay 反爬挑战页。批量访问商品页的风险落在**登录态账号**上，不建议一次直连抓 120 个详情页

## 已实测的页面结构（改采集前先读这段）

2026-09-14 在真机（紫鸟店铺 + ebay.co.uk + 120 条）实测：

- 列表卡片是 **`li.s-card`**；**`li.s-item` 已是 0 条**，别再用旧选择器
- `.s-card__title` 的 innerText 尾部附 `Opens in a new window or tab`，要清掉
- `.s-card__price` 可能带区间与单位后缀：`£21.97 to £22.97(£21.97/Unit)`
- **广告位与末级类目 ID 取页面内嵌 JSON**：`"listings":[{"itemId":..,"promoted":true,"rank":0,"leafCat":112529}]`（与卡片按 itemId 对齐），不用猜正则、不用进详情页
- `_ipg=240` 单页给 242 张卡（含 2 张占位卡），6~10 秒；120 条一次就够
- **item specifics 搜索页没有**（无内嵌数据块），只能进详情页；详情页结构是 `#viTabs_0_is` 下的 `dl > dt + dd`。因风控改为默认不采
- 详情页面包屑是 `bn_*` 非数字形态（`/b/bn_7000259660`），不是数字 ID；类目数字 ID 以搜索页 `listings.leafCat` 为准
- 配送地弹层目前**没设成功**，靠搜索 URL 的 `_stpos/_fcid` 兜底
- **别在 `open_store` 之后立刻连 CDP**：那会儿窗口常还没起来（实测连续 5 次 ECONNREFUSED），用 `ziniao_runtime.connect_cdp()`

细节见 `文档/进度.md` 与 `文档/检查清单_20260914.md`。

## 测试

```text
python -m unittest discover -s tests
  test_analyze.py           分析段（17 条标题、重复保留、相似值合并、价格段…）
  test_collect_offline.py   采集段离线（价格区间/欧陆数字、a11y 尾巴、占位与下架规则）
```
