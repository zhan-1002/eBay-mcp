# Soldeazy 创建 / 保存 / 删除 / 图片 —— 接口实测说明

> 全部结论来自 2026-11-06 在测试账号 `FUN`（shop_idx=159，站点 US）上的实机抓包与回读验证。
> 账号限制：只允许在测试账号上做写操作，`LT` 等有真实刊登的账号不参与。

## 一、三个创建入口

列表页右上 `a.aShopInitPromptLink`（新增数据表）→ 弹层 `#divShopInitPrompt`，三个标签页：

| 标签 | 机制 | 状态 |
|---|---|---|
| 从0开始创建数据表 | `POST /app/soldeazy/datasheet-create/index` | ✅ 可用 |
| 从SKU创建数据表 | `POST /app/soldeazy/datasheet_ajax` `mode=skuInitSearch` | ⚠️ 只能搜到 SKU，创建动作被「暂不支持此销售渠道」挡住 |
| 从刊登下载器创建数据表 | `POST /app/soldeazy/datasheet_ajax` `mode=create_datasheet_from_listing_spy` | ✅ 可用 |

### 1.1 从0创建（空表 + 模板）

```http
POST /app/soldeazy/datasheet-create/index
Content-Type: application/x-www-form-urlencoded

mode=dsheet_datatable&table_action=create
new_dsheet_shop_initial_idx=159
new_dsheet_site_code=US
new_dsheet_listing_template_idx=5257      ← 模板 FUN-US；空则不套模板
new_dsheet_biz_profile_idx=
new_dsheet_price_margin=NaN&new_dsheet_channel_service_fee=NaN&new_dsheet_price=NaN
```

- 返回整页 HTML，随后自动跳到 `table_action=edit&table_row_id=<新 rowid>`。
- **模板只预设刊登参数**（方式/时长/币种/站点/类目模板），**不含产品数据**——
  建出来是空壳：标题为空、SKU=`0`、价格 `-`。
- 新 rowid 的获取：优先从响应里抠 `dsheet_row_id`，抠不到就比对创建前后的数据表编号集合。

### 1.2 从刊登下载器创建

```http
POST /app/soldeazy/datasheet_ajax
（先发 mode=agree 过协议门禁）

mode=create_datasheet_from_listing_spy
channel_type=EBAY
item_ids=<刊登编号，可多个>
shop_idx=159
template_idx=&profile_idx=

200 [{"res_flag":0,"res_item_id":"...","res_message":"生成数据表成功",
      "res_rowid":4569373,"res_dsheet":{...212 个字段...}}]
```

**`res_flag=0` 不代表内容是真的**：请求一个不存在的 item id 也会返回 rowid 和完整内容，
但内容是别的商品。必须校验返回标题与请求编号是否对得上。

## 二、保存数据表

```http
POST /app/soldeazy/datasheet
Content-Type: application/x-www-form-urlencoded

table_action=save
mode=dsheet_datatable
second_mode=dsheet_list
```

### 必填项（缺一项就整体失败）

报错原文：

> 储存数据表失败。请查看没有绿色对钩之区域。请检查以下部分：
> Item Country, Shipping Service(Domestic), Photo Gallery File name(eg x.jpg ,y.gif)HTML

| 字段名 | 说明 | 取值示例 |
|---|---|---|
| `dsheet_itemcountry` | 物品所在地 | `US` |
| `dsheet_ship_service` | 国内运输服务 | `Delivery`（列表见 `POST /app/soldeazy/shipping-service/domestic`，`json=1&site_code=US`） |
| `dsheet_gallery` | 图片文件名或 URL | `test1.jpg` / 完整 https 地址 |

### 字段名坑

- **价格 / 数量 / SKU 在数组字段里**：`dsku_price[]`、`dsku_qty[]`、`dsku_product_code[]`；
- 用 `dsheet_price`、`dsheet_product_code` 填**接口返回 200、页面也不报错，但值根本没进去**；
- 因此写入后必须**回读编辑页**或**导出核对**，不能只看返回值。

其余常用字段：

```
dsheet_titleexternal     标题
dsheet_ebcategory        eBay 类目 id
dsheet_full_item_model   完整型号（列表里显示的 SKU）
dsheet_shop_initial      渠道账号（FUN）
dsheet_sitecode          站点（US）
dsheet_format            刊登方式（BIN）
dsheet_duration          刊登时长（GTC）
```

## 三、删除数据表

```http
POST /app/soldeazy/datasheet
Content-Type: application/x-www-form-urlencoded

table_action=bulk-delete
mode=dsheet_datatable          ← 关键：不是搜索用的 dsheet_list
second_mode=dsheet_list
table_row_ids=<rowid>[,<rowid>...]
listshop[]=159&listsite=0 ...（其余为当前搜索条件）
```

三个坑：

1. **不是 AJAX**，是整表单提交；
2. `mode` 必须是 `dsheet_datatable`，用 `dsheet_list` 提交**既不生效也不报错**；
3. **提交前必须先按 rowid 搜一次**，否则表单没有搜索上下文，同样静默不删。

判定是否真的删掉：重新搜索，比较数据表编号集合。

## 四、图片

### 4.1 文件直传

```http
POST /app/soldeazy/datasheet_photo/upload_photos
Content-Type: multipart/form-data
  photofile=<图片文件>

200 <script>
    var upload_res={"gallery_type":"gallery",
                    "file_name":"product_test.jpg",
                    "real_name":"https://www.cdnclouds.net/np/.../_1.jpg"};
    ...
    </script>
```

- 返回不是 JSON，是**包在 `<script>` 里的 JS 赋值**（上传表单提交到隐藏 iframe）；
- 需要正则抠 `upload_res` 再解析。

### 4.2 图像超连结（热链）

图片框里还有一个 `#image_url` 输入框，对应纯前端函数 `add_image_file(path, title)`：
对 http/https 地址**不做任何转换**（只有相对路径才拼 `base_path`），直接挂进相册列表。

因此可以把公网可访问的图片地址**直接写进 `dsheet_gallery`**，不必先下载再上传。

实测：

```
dsheet_gallery = https://www.cdnclouds.net/np/.../_1.jpg
链接可访问      = HTTP 200
photo_preview  = HTTP 200，返回 <img src='https://...'>
```

取舍：

| 方式 | 优点 | 风险 |
|---|---|---|
| 文件直传 | 图片进了自家 CDN，稳定 | 多一次下载+上传 |
| 热链 | 省一次搬运，直接写 URL | 依赖对方 CDN；防盗链或失效会导致刊登掉图 |

建议：能拿到稳定 CDN 地址就热链，否则走直传。

## 五、图片框的打开方式（供参考）

- 图片区在「图片及视频」标签页里，**不切过去就没有 `.add_photo`**；
- 点 `.add_photo` 打开的是 `GET /app/soldeazy/datasheet_photo?path=&field=dsheet_gallery&...`
  返回的独立 HTML 对话框；真正的上传表单在里面（`#form_upload`，`action=upload_photos`）。
