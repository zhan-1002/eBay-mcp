# -*- coding: utf-8 -*-
"""更新 01 README/进度：接入 DeepSeek 生成标题。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
R1 = os.path.join(PROJ, "01_关键词选品", "README.md")
P1 = os.path.join(PROJ, "01_关键词选品", "文档", "进度.md")

SEC = """
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
  黑名单会把兼容性描述（`for Samsung`）、型号词（`PRO4`/`LP40`）误判为品牌并整条否决，
  且与"高重复标题原样保留"直接冲突，导致永远凑不满 30 条
- **硬约束写进 prompt + 脚本二次校验**：不达标就把问题反馈给模型重试（最多 4 轮），
  每轮合规的标题累积进候选池，最后 `select_best()` 择优 30 条（优先高重复标题、长度接近 80、
  关键词评分高、彼此词汇重叠低）
- **失败必回退**：网络/JSON/校验异常 → 自动用规则版，不中断流水线

### 实测表现（120 条 / wireless earbuds / uk）

```
候选池 49 条 → 择优 30 条（含 7/7 高重复标题）
字符 73~80，中位 78；无逗号、无超长、30 条互不重复
token 用量：约 8.9k / 次（2 轮）；耗时约 10~20 秒
```

LLM 对"品牌 vs 兼容词"的判断样例（正是我们想要的效果）：

```
高重复标题          PRO4 TWS WIRELESS ... SAMSUNG - WHITE
  → LLM 输出        PRO4 TWS Wireless Bluetooth ... Samsung White
  （只规范大小写、去掉 " - "；Samsung 作为兼容性描述保留）

竞品含品牌标题      MPOW Wireless Bluetooth 5.4 Open Ear Earphones ...      → 改为无品牌版
                  Lenovo LP40 TWS Bluetooth 5.0 Earphones Air Pods ...    → 改为无品牌版
```

### 凭据

```text
config.local.json → deepseek.api_key（已 gitignore）
或环境变量 DEEPSEEK_API_KEY
模型默认 deepseek-chat；接口 https://api.deepseek.com/chat/completions（JSON 模式）
```

### 注意

- **eBay User Token 有效期短**：实测隔几小时就失效（会明确报 HTTP 401，不静默）。
  过期后需要重新生成并覆盖 `02_soldeazy详情补数/token.local.txt`
- LLM 标题每次约 9k token；批量多关键词时注意成本
"""

if "## 推荐标题改由 DeepSeek 生成" not in open(R1, encoding="utf-8").read():
    t = open(R1, encoding="utf-8").read()
    key = "## 输出结构：5 张子表"
    t = t.replace(key, SEC.strip() + "\n\n" + key, 1)
    open(R1, "w", encoding="utf-8", newline="\n").write(t)
    print("README 已更新（%d 字符）" % len(t))
else:
    print("README 已有该节")

prog = open(P1, encoding="utf-8").read()
ADD = """

---

## 2026-09-15（三续）：推荐标题接入 DeepSeek

用户决策：**"2，接入 LLM 使用 deepseek"** + **"判断是否为品牌词应该由 LLM 判断，我们只输出清洗后的内容"**。

### 新增 `脚本/llm_titles.py`

- `build_prompt()`：把本地已算好的真实素材（关键词评分表 / 修饰词三分类 / 结构模板 /
  竞品完整标题 / 真实属性值 / 高重复标题清单）拼成 prompt，硬约束逐条写明
- `call_deepseek()`：`POST https://api.deepseek.com/chat/completions`，`response_format=json_object`
- `validate_titles()`：**只做机械校验**（≤80 / 无逗号 / 同标题不重复词 / 标题互不重复），
  **不再用品牌黑名单否决**（用户口径：品牌判断归 LLM）
- `select_best()`：从累积候选池择优 30 条（高重复标题优先、长度接近 80 优先、关键词评分、去同质）
- `generate_titles_llm()`：最多 4 轮，每轮合规标题累积进池；不达标把问题+缺的标题反馈给模型

接入点：`run_keyword_research.upgrade_titles_with_llm()`，主流程默认调用，
`--no-llm` 可关闭；**任何异常都回退规则版**。

### 规则版 vs DeepSeek 版（同一份 120 条数据）

| 指标 | 规则版 | 竞品真实 | DeepSeek |
|---|---|---|---|
| 字符中位 | 51 | 79 | **78** |
| ≥70 字符 | 5/30 | 110/120 | **30/30** |
| 高重复标题保留 | **0/7** | — | **7/7** |
| 自然度 | 规格堆叠 | — | 像真人商品标题 |

### 踩的坑

**"原样保留"与"去品牌"互斥**：`detect_brands` 把兼容性词（samsung）、型号词（pro4）也当品牌，
导致高重复标题（含 `for iphone Samsung`）被判违规，30 条永远凑不满（实测卡在 25/30）。
按用户口径改为 **LLM 判断品牌 + 脚本只做机械校验**后解决。
另：LLM 会"改写"而非逐字复述，所以不再由脚本注入原文，改为要求 LLM 输出**清洗后的版本**；
实测 7 条里 6 条逐字保留、1 条仅规范大小写。

### 顺带确认的环境问题

**eBay 生产 User Token 有效期很短** —— 隔几小时再跑报 `HTTP 401：token 无效或已过期`。
需要重新生成 User Token 覆盖 `02_soldeazy详情补数/token.local.txt`。
（错误信息明确，不静默失败）
"""
if "推荐标题接入 DeepSeek" not in prog:
    open(P1, "a", encoding="utf-8", newline="\n").write(ADD)
    print("进度文档已更新")
else:
    print("进度文档已有该节")
