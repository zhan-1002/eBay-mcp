# 02 Soldeazy 详情补数

用途：拿 `01_关键词选品` 采到的 eBay **刊登编号（item id）**，去 Soldeazy 的
**新增数据表 → 从刊登下载器创建数据表**，把详情（标题 / item specifics / 类目 / 价格 / 图片 / 描述）取回来补全。

## 为什么单独一个模块

- 采集源不同：`01` 走紫鸟浏览器抓 eBay 搜索页；本模块走 **Soldeazy 自己的 Web 接口**（requests，不开浏览器）
- 需要登录：登录一次存会话后，后续全部 requests 复用
- **是写操作**：Soldeazy 侧会**创建数据表**，属于对生产账号的写入 → 有严格的安全要求（见下）

## 现行脚本

| 文件 | 角色 |
|---|---|
| `脚本/soldeazy_login.py` | 自动登录 + 存会话（`--check` 自检 / `--manual` 人工登录） |
| `脚本/soldeazy_client.py` | 会话复用客户端（requests；会话过期抛 `SessionExpired`，不静默） |
| `脚本/manifest.py` | **写操作清单**：所有写操作先记账；删除判定的唯一依据 |
| `脚本/probe_*.py` `test_*.py` | 只读探查（页面结构 / 接口 / 判定信号），可随时重跑 |

## 怎么跑

```text
# 1) 登录（凭据放本目录 config.json 的 soldeazy.username/password）
python 脚本\soldeazy_login.py
python 脚本\soldeazy_login.py --check      # 会话自检

# 2) 只读探查（确认页面结构没变）
python 脚本\probe_soldeazy_atlas.py
```

## 完整链路（已实测跑通）

```
01 模块采卡片页 → item_id
      ↓
listing_spy 创建数据表（写，带渠道账号）
      ↓  返回 res_dsheet（212 字段，含全部详情）
内容三重校验（区分"有效 / 内容不符 / 拒绝"）
      ↓
回填到本地 Excel / JSON
```

调用形态：

```text
POST /app/soldeazy/datasheet_ajax
  mode=create_datasheet_from_listing_spy
  channel_type=EBAY
  item_ids=<刊登编号，可多个>
  shop_idx=<渠道账号 id，必填，token 需有效>
  template_idx= / profile_idx=
```

**一次调用即拿到全部详情**（`res_dsheet`），不需要再进详情页读 JS。

## ⚠️ 生产账号安全要求（必须遵守）

1. **不允许删除**：本批探查创建的数据表已封存，未获人工确认前**不得删除**。
   清单见 `文档/生产账号数据表创建记录_封存.md` 与 `输出/_manifest/created_rows.jsonl`
2. **写前记账**：任何 `listing_spy` 调用前，先 `manifest.record_intent(...)`；拿到 rowid 后
   `manifest.record_created(...)`。**清单是"哪些是我们建的"的唯一权威依据**
3. **删除只按 rowid 白名单 + 逐行复验**，四要素（rowid / 主货品标籤 / 渠道账号 / 创建时间窗）全对才可操作；
   **禁止**"按文件名或时间窗批量删"—— 同账号同事建的表文件名前缀完全相同，无法区分
4. **页面没有"按创建人分组/标记"**，也**不能自定义生成的数据表名称**（创建接口只接受上面 5 个参数）
5. 渠道账号 `shop_idx` 的 eBay token 需有效；实测 `SB(167)` 无效

## 关键坑：`res_flag` 判不出内容真假

请求一个**不存在的 item id**，服务端**照样返回 `res_flag=0` + `res_rowid` + 完整 `res_dsheet`**，
但内容是**另一个真实商品**（实测请求 `123456789012` → 返回一个 PS4 游戏，站点 US、类目 139973）。

→ 必须做内容校验，且把三类结果分开记录：

| 判定 | 依据 |
|---|---|
| 拒绝 / 失败 | 无 `res_rowid`，或 `res_message` 为拒绝类（shop 无效 / eBay token 失效） |
| **内容不符**（疑似受保护 / 取不到） | 有 rowid，但**返回标题与关键词品类不匹配** |
| 有效 | 有 rowid + 请求 id 出现在返回内容 + 标题品类匹配 + 业务字段完整 |

## 参考实现

- 同集团站会话式下载：`\\192.168.120.11\Ebay部门\ebay看板\scripts\ebay_gigab2b_export_download.py`
  （requests 会话 + csrf + 提交导出 + 轮询下载中心）
- 共享里那两个 `soldeazy_*.py` **只处理 Excel 价格表，不含网页抓取**；
  原先"下载"环节由影刀 RPA 完成 —— 本模块是把这一步用 Python 重做
- dsheet 价格表导出结构（供参考）：`Row ID / Sales channel / P.SKU / SKU / Qty / Price / Post.D.`
  样例在 `D:\PythonProject\ebay\soldeazy\download\export_dsheet_UK.xlsx`

## 文档

- `文档/接口探查记录_20260914.md` —— 登录 / 列表搜索 / 详情 / listing_spy 的完整实测机制
- `文档/生产账号数据表创建记录_封存.md` —— 已创建数据表清单（封存，不删）

## 需求范围（2026-09-15 用户确认）

- **不做「售出/最近成交（sold item）」** —— 该需求已从范围中移除。
  因此 Marketplace Insights API 的 403 权限问题**不再是缺口**，无需申请。
- 需要的是：**搜索 120 条** + **逐条取 item specifics / 类目 / 图片 / 描述**。
  这两项已由 eBay Browse API 生产环境实测 100% 覆盖（见文档附二）。

## 建议的落地形态

```
01_关键词选品 采集段  →  改用 eBay Browse API
    search(item_summary, limit=200)          1 次调用拿 120 条
    getItem(v1|xxx|0) × 120                  逐条拿 localizedAspects
    实测覆盖率 100%，121 次调用 / 2.5 分钟

紫鸟链路      →  保留作为备用（配送地弹层问题仍在）
Soldeazy 链路 →  可停用（不再需要写生产账号）
封存数据表    →  11 条按指示不删，清单见文档
```
