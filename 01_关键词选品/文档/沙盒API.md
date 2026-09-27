# eBay 沙盒（Sandbox）怎么用

沙盒是开发者计划里的**测试站**，域名是 `api.sandbox.ebay.com`，商品是假数据。  
用来验证：密钥对不对、token 能不能换、搜索请求格式对不对。  
**不能拿沙盒结果给运营上架**（标题、价格、类目都不是真实市场）。

## 1. 在控制台拿沙盒密钥

1. 打开 https://developer.ebay.com 登录  
2. 进 **Application Keys**（或 User Access Tokens 旁边的 Keysets）  
3. 看 **Sandbox** 那一组，不要拿 Production  
4. 复制：
   - **App ID (Client ID)**
   - **Cert ID (Client Secret)**

沙盒和生产是两套钥匙，不能混用。沙盒 ID 去打 `api.ebay.com` 会 401。

## 2. 写进本工程

复制根目录 `config.example.json` 为 `config.local.json`（若已有就改 `ebay_api` 段）：

```json
"ebay_api": {
  "environment": "sandbox",
  "client_id": "这里贴沙盒 App ID",
  "client_secret": "这里贴沙盒 Cert ID"
}
```

公开搜索只用 **应用级 token**（client_credentials），不必创建 Sandbox User，也不必买家登录。

## 3. 先探测通不通

```text
python 脚本\check_ebay_api.py sandbox
```

通了会看到 `换 token: OK`。沙盒搜 `iphone` 可能只有几条，甚至 0 条，这是正常的。

## 4. 走选品脚本（仍是测试数据）

```text
关键词选品.bat --mode api --env sandbox --keyword iphone --site us --max 20
```

脚本会打：`API [sandbox] 搜索: ...`

## 5. 沙盒和真站对照

| | 沙盒 Sandbox | 生产 Production |
|---|---|---|
| 密钥 | Sandbox Keyset | Production Keyset |
| 地址 | `api.sandbox.ebay.com` | `api.ebay.com` |
| 数据 | 测试商品 | 真实在售 |
| 用途 | 验证对接 | 真正选品 |
| 本工程 | `--env sandbox`（默认） | `--env production` |

生产密钥另外申请/启用后，把 `config.local.json` 改成生产那一对，并加 `--env production`。生产常还要配「账号删除通知」或申请豁免。

## 常见报错

- **401 / invalid_client**：用了生产密钥打沙盒，或 App ID / Cert 复制反了、多了空格  
- **搜索 0 条**：沙盒库存本来就少，换 `iphone` / `test` 再试；真选品仍用紫鸟或生产 API  
- **Keyset disabled**：看的是 Production；先用 Sandbox 那一组
