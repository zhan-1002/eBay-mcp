# -*- coding: utf-8 -*-
"""更新 README 与进度文档：采集段已切官方 API。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
R1 = os.path.join(PROJ, "01_关键词选品", "README.md")
R2 = os.path.join(PROJ, "README.md")
P1 = os.path.join(PROJ, "01_关键词选品", "文档", "进度.md")

# ---------- 01 README ----------
old = open(R1, encoding="utf-8").read()
old = old.replace(
    "输入：紫鸟店铺名（或 API 密钥）、关键词、站点  \n输出：至少 20 条推荐 title + 词频 / 属性 / 末级类目 ID / 价格段",
    "输入：关键词、站点（**默认走 eBay 官方 API**，不再需要紫鸟店铺）  \n"
    "输出：30 条推荐 title + 关键词评分 / 修饰词三分类 / 价格区间与占比 / 品牌壁垒 / 末级类目 ID")
old = old.replace(
    "| `脚本/collect_api.py` | Browse API 搜索 + 前 10 条详情 |",
    "| `脚本/collect_ebay_api.py` | **官方 Browse API 采集（默认）**：搜索 120 条 + 逐条 getItem |\n"
    "| `脚本/collect_api.py` | 旧版 API 采集（保留备用，已被 collect_ebay_api 取代） |")

API_SECTION = """
## 默认走官方 API（2026-09-15 起的生产方式）

实测口径（生产环境，120 条，见 `02_soldeazy详情补数/文档/接口探查记录_20260914.md` 附二）：

```text
python 脚本\\run_keyword_research.py --mode api --keyword "wireless earbuds" --site uk --max 120
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

### 已知边界

- `limit` 上限 **200**（>200 报 errorId 12006）；`offset` 必须是 `limit` 的整数倍
- **搜索结果里没有 item specifics**，必须逐条 `getItem`
- token 有有效期，过期后需重新生成（会明确报 HTTP 401，不静默）
- 逐条详情是串行请求，120 条约 2.5 分钟；如需加速可改并发（未实现）
"""

if "默认走官方 API（2026-09-15" not in old:
    key = "## 默认不进详情页（风控）"
    if key in old:
        old = old.replace(key, API_SECTION.strip() + "\n\n" + key, 1)
    else:
        old = old.rstrip() + "\n\n" + API_SECTION
    open(R1, "w", encoding="utf-8", newline="\n").write(old)
    print("已更新 01/README.md（%d 字符）" % len(old))
else:
    print("01/README.md 已含该节，跳过")

# ---------- 01 进度 ----------
prog = open(P1, encoding="utf-8").read()
ADD = """

---

## 2026-09-15：采集段整体切到 eBay 官方 API

用户决定：**全改为官方 API 形式**（紫鸟保留备用、Soldeazy 停用；售出数据不在需求内）。

### 新增 `脚本/collect_ebay_api.py`

- `EbayApi` 类：`search()` / `get_item()` / `collect()`，凭据三级回退（环境变量 → token.local.txt → client_credentials）
- `run_keyword_research.py --mode api` 改用它；`--detail` 默认 **-1（全部取详情）**；`--env` 默认 **production**
- 字段直接映射进既有分析段（价格区间/品牌壁垒/关键词评分/修饰词/30 条标题），**分析段零改动**

### 生产实测（120 条，`wireless earbuds` / uk）

```
详情成功 120/120（0 失败）| 总耗时 145~150 秒 | 调用 {search:1, getItem:120}
item specifics 覆盖 100% ｜ 每条属性数 6 / 中位 18 / 最多 33 ｜ 属性名 186 种
Brand 100% | Connectivity 100% | Colour 99.2% | Type 99.2% | Model 92.5%
leaf_category_ids 100% | category_path 100% | 图片 100% | 描述 100% | 卖家 100%
广告位(priorityListing) 14 条 | 末级类目 112529:112, 80077:8
产物：输出/api_uk_wireless_earbuds_20260915_004214.xlsx（13 子表 / 采集明细 38 列）
```

### 踩的坑（已加回归测试）

**类目合并时把第二类目丢了**：
搜索 `itemSummary.leafCategoryIds` 可以有**两个**类别（如 `[112529, 80077]`），
而详情 `getItem` **只回单个 `categoryId`，且不含 `leafCategoryIds`/`categories`**。
我最初在 `_enrich` 里直接用详情的值覆盖，导致"第二类目"从 3~4 条变成 **0 条**。
修法：抽出纯函数 `merge_categories()` —— 叶子以搜索为准、祖先链用 `categoryIdPath`+`categoryPath` 按位配对。
修复后第二类目恢复（位置 58/88/105）。

新增 8 个单测（`tests/test_ebay_api_offline.py`）：类目合并 6 个 + 站点映射 2 个。测试总数 **21 → 29**。
"""
if "整体切到 eBay 官方 API" not in prog:
    open(P1, "a", encoding="utf-8", newline="\n").write(ADD)
    print("已更新 01/文档/进度.md")
else:
    print("进度文档已含该节，跳过")

# ---------- 根 README ----------
root = open(R2, encoding="utf-8").read()
root = root.replace(
    "| [01_关键词选品](01_关键词选品/README.md) | 输入店铺/关键词/站点，抓前 120 条，做词频/属性/类目/价格段，输出推荐 title + item_id | 不上架、不改 listing、不绕风控、默认不进详情页 |",
    "| [01_关键词选品](01_关键词选品/README.md) | 输入关键词/站点，**走 eBay 官方 API** 抓 120 条含 item specifics，做词频/属性/类目/价格段/品牌壁垒，输出 30 条推荐 title | 不上架、不改 listing |")
root = root.replace(
    "`01` 支持两种采集，分析逻辑共用：",
    "`01` 支持三种采集，分析逻辑共用（**默认官方 API**）：")
open(R2, "w", encoding="utf-8", newline="\n").write(root)
print("已更新根 README.md")
