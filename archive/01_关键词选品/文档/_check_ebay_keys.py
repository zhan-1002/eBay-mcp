# -*- coding: utf-8 -*-
"""比对 config 里存的凭据 vs 开发者后台截图上的真实值（临时诊断脚本）。

截图（Production / keyset=BETA）给出的真实值：
  App ID (Client ID) : ...-BETA-PRD-f82b86fbd-f4f4c153   （左侧被截断）
  Dev ID             : 16880a0b-a69a-4ac8-91fd-93986bb62f8a
  Cert ID (Secret)   : PRD-examplecert000-0000-0000-0000-0000

要回答：config.local.json 里那两个字段到底是什么。
"""
import io
import json
import os

PROJ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
with io.open(os.path.join(PROJ, "config.local.json"), encoding="utf-8") as f:
    api = json.load(f)["ebay_api"]

DEV_ID_FROM_SCREENSHOT = "16880a0b-a69a-4ac8-91fd-93986bb62f8a"

cid = api.get("client_id", "")
sec = api.get("client_secret", "")


def shape(v, name):
    print("%s:" % name)
    print("   长度 %d ｜ 段数 %d ｜ 含 '-PRD-' %s ｜ 含 '-SBX-' %s"
          % (len(v), len(v.split("-")), "-PRD-" in v.upper(), "-SBX-" in v.upper()))
    parts = v.split("-")
    print("   各段长度: %s" % [len(p) for p in parts])
    print("   头 8 位 %s ｜ 尾 4 位 %s" % (v[:8], v[-4:]))
    # 只打码中间，便于人工核对首尾
    return parts


p1 = shape(cid, "config 里的 client_id")
print()
p2 = shape(sec, "config 里的 client_secret")
print()
print("=" * 72)
print("比对（截图上的 Dev ID = %s）" % DEV_ID_FROM_SCREENSHOT)
print("  config.client_secret 与截图 Dev ID 完全相同？ → %s"
      % (sec.strip() == DEV_ID_FROM_SCREENSHOT))
print("  config.client_id 是沙箱(sandbox) App ID 吗？   → %s"
      % ("-SBX-" in cid.upper()))
print("  config.client_id 是生产(production) App ID 吗？→ %s"
      % ("-PRD-" in cid.upper()))
print()
print("App ID 形态对照（eBay 命名规则）:")
print("  生产 App ID: <应用名>-<标识>-PRD-<8位>-<8位>   ← 截图里就是这个")
print("  沙箱 App ID: <应用名>-<标识>-SBX-<8位>-<8位>")
print("  Dev ID    : 8-4-4-4-12 的 UUID，**不参与 OAuth**，不是密钥")
print("  Cert ID   : 生产 PRD-... / 沙箱 SBX-...，这才是 OAuth 的 client_secret")
