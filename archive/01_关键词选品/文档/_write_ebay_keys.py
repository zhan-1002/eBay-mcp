# -*- coding: utf-8 -*-
"""把可用的生产密钥对写进 config.local.json（gitignored），并归档失效的旧令牌文件。

已验证可用：
  App ID  = -BETA-PRD-f82b86fbd-f4f4c153          （28 位，确实以 "-" 开头）
  Cert ID = PRD-examplecert000-0000-0000-0000-0000
  换 token → HTTP 200，expires_in=7200
"""
import io
import json
import os
import shutil
import time

PROJ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CFG = os.path.join(PROJ, "config.local.json")
LEGACY = os.path.join(PROJ, "02_soldeazy详情补数", "token.local.txt")

NEW_CID = "-BETA-PRD-f82b86fbd-f4f4c153"
NEW_SEC = "PRD-examplecert000-0000-0000-0000-0000"


def mask(v):
    v = str(v or "")
    return "<空>" if not v else (v[:6] + "..." + v[-4:] if len(v) > 14 else v)


# 1) 备份 + 写入
shutil.copy2(CFG, CFG + ".bak_%s" % time.strftime("%Y%m%d_%H%M%S"))
with io.open(CFG, encoding="utf-8") as f:
    cfg = json.load(f)
old = dict(cfg.get("ebay_api") or {})
cfg.setdefault("ebay_api", {})
cfg["ebay_api"]["client_id"] = NEW_CID
cfg["ebay_api"]["client_secret"] = NEW_SEC
cfg["ebay_api"].setdefault("env", "production")
with io.open(CFG, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)

print("config.local.json 已更新（已备份 .bak）")
print("  client_id      %s → %s" % (mask(old.get("client_id")), mask(NEW_CID)))
print("  client_secret  %s → %s" % (mask(old.get("client_secret")), mask(NEW_SEC)))
print("  其余键保持不变: %s" % ", ".join(sorted(cfg.keys())))

# 2) 归档失效的旧令牌文件（不删，改名，避免它继续被当成"可用的手工令牌"优先取用）
if os.path.isfile(LEGACY):
    dst = os.path.join(os.path.dirname(LEGACY), "token.local.expired.txt")
    shutil.move(LEGACY, dst)
    print("旧令牌文件已归档（内容保留）: %s → %s"
          % (os.path.basename(LEGACY), os.path.basename(dst)))
else:
    print("没有 token.local.txt，跳过归档")
