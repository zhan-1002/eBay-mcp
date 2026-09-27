# -*- coding: utf-8 -*-
"""更新 01 文档：紫鸟封存 + 并发。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
R1 = os.path.join(PROJ, "01_关键词选品", "README.md")
P1 = os.path.join(PROJ, "01_关键词选品", "文档", "进度.md")

# ---------- README：脚本表 + 并发说明 ----------
t = open(R1, encoding="utf-8").read()
t = t.replace(
    "| `脚本/collect_ebay_api.py` | **官方 Browse API 采集（默认）**：搜索 120 条 + 逐条 getItem |\n"
    "| `脚本/collect_api.py` | 旧版 API 采集（保留备用，已被 collect_ebay_api 取代） |",
    "| `脚本/collect_ebay_api.py` | **官方 Browse API 采集（默认）**：搜索 120 条 + **并发**逐条 getItem |\n"
    "| `脚本/collect_api.py` | 旧版 API 采集（保留备用） |\n"
    "| `脚本/check_ebay_api.py` | 密钥连通性探测（换 token + 试搜） |\n"
    "| `99_归档/紫鸟采集_20260915/` | **紫鸟链路已封存**（保留 `--mode ziniao` 可运行） |")

CONC = """
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
"""

if "### 并发取详情（默认开启）" not in t:
    key = "### 已知边界"
    t = t.replace(key, CONC.strip() + "\n\n" + key, 1)
    open(R1, "w", encoding="utf-8", newline="\n").write(t)
    print("README 已加并发说明（%d 字符）" % len(t))
else:
    print("README 已有并发说明")

# ---------- 进度 ----------
prog = open(P1, encoding="utf-8").read()
ADD = """

---

## 2026-09-15（续）：并发取详情 + 紫鸟封存

### 并发

`EbayApi.collect(workers=N)` + `run_keyword_research.py --workers`（默认 8，上限 16）。
每线程独立 `requests.Session`（连接复用 + 线程安全），结果按下标写回保证顺序。

| 模式 | 120 条耗时 |
|---|---|
| 串行 | 145 秒 |
| **并发 8 线程** | **11.5 秒**（提速 12.6 倍） |

并发后数据完整性复核：120/120 详情成功、item specifics 100%、第二类目 4 条正常、类目路径 100%。

### 紫鸟链路封存

移至 `01_关键词选品/99_归档/紫鸟采集_20260915/`：

```
脚本/ziniao_runtime.py, 脚本/collect_ziniao.py
启动器/probe_store.py, 启动器/probe_dom.py
诊断脚本/_diag_*.py, _ziniao_probe.py, _attach_diag.py
```

- `run_keyword_research.py` 的 `--mode ziniao` **保留可用**（按归档路径注入 sys.path 加载），运行时打印"已封存"提示
- **`--mode` 默认值改为 `api`**（原来是 ziniao）
- `tests/test_collect_offline.py` 改为从归档目录导入 `collect_ziniao`（价格解析等测试继续有效）
- 启动器 `.bat` 用法示例改为 API 模式为主
- 归档说明见 `99_归档/紫鸟采集_20260915/README.md`（含"为什么封存"对比表与未修问题清单）

测试仍 **29 个全过**。
"""
if "并发取详情 + 紫鸟封存" not in prog:
    open(P1, "a", encoding="utf-8", newline="\n").write(ADD)
    print("进度文档已更新")
else:
    print("进度文档已有该节")
