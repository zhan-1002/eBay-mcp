# -*- coding: utf-8 -*-
"""挖两个最有价值的仓库：
  1. colindaniels/eBay-sold-items-documentation —— 纯文档，今天更新
  2. Jason-Vaughan/openclaw-ebay-research —— 声称用 client_credentials 就能查 sold history
"""
import base64
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"


def readme(repo, limit=4200):
    r = requests.get("%s/repos/%s/readme" % (API, repo), headers=H, timeout=60)
    if r.status_code != 200:
        return "（无 README，HTTP %s）" % r.status_code
    return base64.b64decode(r.json()["content"]).decode("utf-8", "replace")[:limit]


def tree(repo):
    r = requests.get("%s/repos/%s" % (API, repo), headers=H, timeout=45)
    br = (r.json().get("default_branch") or "main") if r.status_code == 200 else "main"
    t = requests.get("%s/repos/%s/git/trees/%s?recursive=1" % (API, repo, br),
                     headers=H, timeout=60)
    if t.status_code != 200:
        return []
    return [x["path"] for x in (t.json().get("tree") or []) if x["type"] == "blob"]


print("#" * 122)
print("# 1) colindaniels/eBay-sold-items-documentation")
print("#" * 122)
print("--- 文件树 ---")
files = tree("colindaniels/eBay-sold-items-documentation")
for f in files[:40]:
    print("   %s" % f)
print("   共 %d 个文件" % len(files))
print()
print("--- README（前 4200 字）---")
print(readme("colindaniels/eBay-sold-items-documentation"))
time.sleep(1)

print()
print("#" * 122)
print("# 2) Jason-Vaughan/openclaw-ebay-research（声称 client_credentials 查 sold history）")
print("#" * 122)
print("--- 文件树 ---")
files2 = tree("Jason-Vaughan/openclaw-ebay-research")
for f in files2[:60]:
    print("   %s" % f)
print("   共 %d 个文件" % len(files2))

# 在代码里找 sold history 用的是什么端点
print()
print("--- 代码里搜 sold / 端点 ---")
for f in files2:
    if not f.endswith((".ts", ".js", ".py", ".json", ".md")):
        continue
    fr = requests.get("%s/repos/%s/contents/%s" % (API, "Jason-Vaughan/openclaw-ebay-research", f),
                      headers=H, timeout=60)
    if fr.status_code != 200:
        continue
    try:
        src = base64.b64decode(fr.json()["content"]).decode("utf-8", "replace")
    except Exception:
        continue
    hits = []
    for kw in ["sold", "marketplace_insights", "item_sales", "sell/research",
               "product_insight", "api_scope", "terapeak", "soldHistory", "sold_history"]:
        for m in re.finditer(kw, src, re.I):
            s = max(0, m.start() - 110)
            frag = re.sub(r"\s+", " ", src[s:m.start() + 170])
            hits.append((kw, frag))
            break
    if hits:
        print("\n   【%s】" % f)
        for kw, frag in hits[:5]:
            print("      [%s] %s" % (kw, frag[:210]))
    time.sleep(0.6)
