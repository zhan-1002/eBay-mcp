# -*- coding: utf-8 -*-
"""用 GitHub contents API 拉规格文件（绕开 raw 域名的超时/404），提取真实路径与 scope。"""
import base64
import json
import re
import sys
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"
DIR = "src/types/restful/specs"

WANT = ["commerce_feedback_v1_beta_oas3.ts", "buy_marketing_v1_beta_oas3.ts",
        "buy_marketplace_insights_v1_beta_oas3.ts", "sell_analytics_v1_oas3.ts"]

meta = requests.get("%s/repos/hendt/ebay-api/contents/%s" % (API, DIR),
                    headers=H, timeout=45).json()
default_branch = requests.get("%s/repos/hendt/ebay-api" % API,
                              headers=H, timeout=45).json().get("default_branch")
print("默认分支: %s" % default_branch)

paths_by_file = {}
for name in WANT:
    url = "%s/repos/hendt/ebay-api/contents/%s/%s" % (API, DIR, name)
    r = requests.get(url, headers=H, timeout=90)
    print("=" * 96)
    print("%s → HTTP %s" % (name, r.status_code))
    if r.status_code != 200:
        print("  %s" % r.text[:150])
        continue
    d = r.json()
    try:
        txt = base64.b64decode(d.get("content") or "").decode("utf-8", "replace")
    except Exception as exc:
        print("  解码失败 %s" % exc)
        continue
    print("  大小 %d 字符" % len(txt))
    # 路径
    cands = sorted(set(re.findall(r'["\'](/[A-Za-z0-9_\-/{}]{3,80})["\']\s*:', txt)))
    cands = [c for c in cands if not c.startswith("/#") and "http" not in c]
    print("  路径 %d 个：" % len(cands))
    for c in cands[:16]:
        print("     %s" % c)
    # 基础 URL / scope
    for m in re.finditer(r"(https://api\.ebay\.com/[A-Za-z0-9_/\-{}]+)", txt):
        print("  基础 URL: %s" % m.group(1))
        break
    scopes = sorted(set(re.findall(r"(?:api_scope[\w./]*)", txt)))
    if scopes:
        print("  scope 片段: %s" % ", ".join(scopes[:6]))
    paths_by_file[name] = cands
    time.sleep(1)

# 用真实路径实测
sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}

print()
print("=" * 96)
print("实测：规格里的真实路径")
print("=" * 96)
for name, cands in paths_by_file.items():
    for c in cands:
        if "{" in c:          # 跳过得填参数的
            continue
        full = c if c.startswith("/commerce") or c.startswith("/buy") or c.startswith("/sell") else None
        if not full:
            continue
        try:
            r = requests.get("https://api.ebay.com" + full, headers=A,
                             params={"limit": 5}, timeout=30)
            if r.status_code == 200:
                tag = "✅ 200 ｜ %s" % ", ".join(list(r.json().keys())[:6])
            elif r.status_code in (401, 403):
                tag = "🔒 %s 存在但无权限" % r.status_code
            elif r.status_code == 400:
                tag = "★ 400 存在（参数问题）"
            elif r.status_code == 404:
                continue          # 404 就不刷屏了
            else:
                tag = "HTTP %s" % r.status_code
            print("  %-56s %s" % (full, tag))
        except Exception as exc:
            print("  %-56s 异常 %s" % (full, str(exc)[:40]))
