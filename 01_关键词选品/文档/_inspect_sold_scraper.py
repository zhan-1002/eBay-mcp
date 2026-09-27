# -*- coding: utf-8 -*-
"""实地考察 GeniusSecret1117/eBay-Sold-Items-Statistics-Scraper 能不能用。

看：
  1. 仓库元信息（许可证、语言、大小、活跃度、issue）
  2. 文件树
  3. README 全文
  4. 代码里怎么拿数据（官方 API？Selenium 爬？要不要登录态？）
"""
import base64
import re
import time

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"
REPO = "GeniusSecret1117/eBay-Sold-Items-Statistics-Scraper"

r = requests.get("%s/repos/%s" % (API, REPO), headers=H, timeout=45)
print("=" * 96)
print("一、仓库元信息")
print("=" * 96)
if r.status_code != 200:
    print("  HTTP %s %s" % (r.status_code, r.text[:150]))
else:
    j = r.json()
    for k in ("full_name", "description", "stargazers_count", "forks_count",
              "open_issues_count", "language", "size", "created_at", "pushed_at",
              "archived", "disabled", "default_branch"):
        print("  %-22s %s" % (k, j.get(k)))
    lic = j.get("license") or {}
    print("  %-22s %s" % ("license", lic.get("spdx_id") or "（无）"))

# 文件树
tree = requests.get("%s/repos/%s/git/trees/%s?recursive=1"
                    % (API, REPO, (j.get("default_branch") or "main")),
                    headers=H, timeout=60)
print()
print("=" * 96)
print("二、文件树")
print("=" * 96)
code_files = []
if tree.status_code == 200:
    for it in tree.json().get("tree") or []:
        if it["type"] != "blob":
            continue
        p = it["path"]
        if any(p.endswith(x) for x in (".py", ".js", ".jsx", ".ts", ".json", ".txt",
                                       ".md", ".yml", ".yaml", ".env", ".cfg")):
            print("   %-72s %s" % (p, it.get("size")))
            if p.endswith((".py", ".js", ".jsx")):
                code_files.append(p)
else:
    print("  取文件树失败 HTTP %s" % tree.status_code)

# README
rd = requests.get("%s/repos/%s/readme" % (API, REPO), headers=H, timeout=60)
if rd.status_code == 200:
    txt = base64.b64decode(rd.json()["content"]).decode("utf-8", "replace")
    print()
    print("=" * 96)
    print("三、README（前 2500 字）")
    print("=" * 96)
    print(txt[:2500])

# 代码关键点扫描
print()
print("=" * 96)
print("四、代码扫描：怎么拿数据？要不要登录态？")
print("=" * 96)
KEYS = ["selenium", "webdriver", "chrome", "undetected", "terapeak", "login",
        "cookie", "token", "oauth", "marketplace_insights", "item_sales",
        "api.ebay.com", "svcs.ebay", "requests.get", "BeautifulSoup", "sleep(",
        "headless", "user_data_dir", "profile"]
for f in code_files[:14]:
    fr = requests.get("%s/repos/%s/contents/%s" % (API, REPO, f), headers=H, timeout=60)
    if fr.status_code != 200:
        continue
    try:
        src = base64.b64decode(fr.json()["content"]).decode("utf-8", "replace")
    except Exception:
        continue
    hits = {}
    for k in KEYS:
        n = len(re.findall(re.escape(k), src, re.I))
        if n:
            hits[k] = n
    if hits:
        print("  %-46s %s" % (f[:46], hits))
    time.sleep(0.6)
