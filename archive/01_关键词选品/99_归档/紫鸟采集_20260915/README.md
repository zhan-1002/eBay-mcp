# 紫鸟采集链路 —— 已封存（2026-09-15）

> **状态：封存、不再使用。** 保留全部代码与诊断工具，便于追溯与必要时恢复。
> 采集与详情补数已整体切到 **eBay 官方 Browse API**（见 `01_关键词选品/脚本/collect_ebay_api.py`）。

## 为什么封存

| 维度 | 紫鸟链路 | 官方 API（现行） |
|---|---|---|
| item specifics 覆盖 | 有，但受"保护/内容回落"影响 | **实测 120/120 = 100%** |
| 配送地 | `set_ship_to` 始终没设成功，只靠搜索 URL 的 `_stpos/_fcid` 兜底 | header 精确指定，GB/US/DE 实测生效 |
| 风控 | eBay 挑战页 / 连接被断（`ERR_CONNECTION_CLOSED`、`TargetClosedError`） | 无浏览器风控 |
| 速度 | 开窗 + 翻页，分钟级且不稳 | 121 次调用，8 线程并发 **11.5 秒** |
| 写账号 | 需配合 Soldeazy（会在生产账号创建数据表） | **零写操作** |

## 归档内容

```
99_归档/紫鸟采集_20260915/
  脚本/ziniao_runtime.py      紫鸟启停/开店/CDP 就绪等待（含 wait_for_cdp、connect_cdp）
  脚本/collect_ziniao.py      紫鸟采集主流程（s-card 解析、set_ship_to、详情抓取）
  启动器/probe_store.py       只开窗不采集的探针（验证店铺可打开）
  启动器/probe_dom.py         搜索页/详情页 DOM 探针（含 --detail 模式）
  诊断脚本/_diag_*.py         当时的各类定位脚本（shipto / skip / pipeline / seq / detail …）
  诊断脚本/_ziniao_probe.py   进程级诊断（后来确认是沙箱限制导致启动失败）
  诊断脚本/_attach_diag.py    接管已开窗口做只读观察
```

## 如何恢复使用

`run_keyword_research.py` **保留 `--mode ziniao`**，并按归档路径加载这两个模块：

```text
python 脚本\run_keyword_research.py --mode ziniao --store haihu_8075 --keyword "wireless earbuds" --site uk
```

运行时会打印「紫鸟链路已封存」提示。需要的话把两个 `.py` 移回 `脚本/` 即可（那时删掉入口里的归档路径注入）。

## 归档时仍然存在的已知问题（未修）

1. **配送地弹层设不成功**：点到 `button.gh-flyout__target`，弹层容器选择器 `[role='dialog']` 会命中 137 个元素、抓到的是页头；
   最终靠搜索 URL 的 `_stpos/_fcid` 兜底（结果确实落在站点口径，但没有可信的成败信号）
2. **`set_ship_to` 的返回语义**已改为"如实反映"（失败返回 `{}`），但能力本身没解决
3. **CDP 接管时序**已修（`wait_for_cdp` / `connect_cdp`），`kill_ziniao` 已改为确认杀干净
4. **诊断脚本里的相对路径**指向原来位置，直接跑会找不到模块 —— 属归档快照，用前需自行调路径

## 还保留的紫鸟相关文件（未移动）

- `01_关键词选品/输出/_dom/*.html` —— 当时 dump 的搜索页/详情页 HTML（含真实卡片结构，很有参考价值）
- `02_soldeazy详情补数/` 整个模块 —— Soldeazy 链路，同样已停用（售出数据不在需求内）
- `config.local.json` 的 `ziniao` 段 —— 紫鸟凭据，保留
