# -*- coding: utf-8 -*-
"""完整读 ebay-terapeak-mcp 的 README，把它的工作原理、前置条件、官方警告原文摘出来。"""
import io
import re

import requests

H = {"User-Agent": "Mozilla/5.0"}
URLS = [
    "https://raw.githubusercontent.com/bintangtimurlangit/ebay-terapeak-mcp/main/README.md",
    "https://raw.githubusercontent.com/bintangtimurlangit/ebay-terapeak-mcp/master/README.md",
]
t = ""
for u in URLS:
    r = requests.get(u, headers=H, timeout=60)
    print("%s → HTTP %s" % (u.split("/")[-2:], r.status_code))
    if r.status_code == 200:
        t = r.text
        break
if not t:
    raise SystemExit("README 抓不到")

io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_mcp_readme.md", "w",
        encoding="utf-8").write(t)
print("长度 %d 字符\n" % len(t))

print("=" * 112)
print("一、原理与前置条件（原文摘录）")
print("=" * 112)
for kw in ["Unofficial", "private endpoint", "fingerprint", "Akamai", "perfdrive",
           "Requirements", "Node", "login", "account", "cookie"]:
    for m in re.finditer(re.escape(kw), t, re.I):
        s = max(0, m.start() - 200)
        frag = re.sub(r"\s+", " ", t[s:m.start() + 320]).strip()
        print("\n  [%s] …%s…" % (kw, frag[:430]))
        break

print()
print("=" * 112)
print("二、风险相关表述（自己搜 warn/risk/ban/rate/suspend/terms）")
print("=" * 112)
for kw in ["warn", "risk", "ban", "suspend", "limit", "terms", "to be blocked",
           "detect", "responsib"]:
    hits = list(re.finditer(re.escape(kw), t, re.I))
    if hits:
        for m in hits[:2]:
            s = max(0, m.start() - 180)
            frag = re.sub(r"\s+", " ", t[s:m.start() + 260]).strip()
            print("\n  [%s] …%s…" % (kw, frag[:400]))

print()
print("=" * 112)
print("三、它暴露的 Terapeak 私有端点原文")
print("=" * 112)
for m in re.finditer(r"(sh/research[\w/]*)", t):
    s = max(0, m.start() - 260)
    print("\n  …%s…" % re.sub(r"\s+", " ", t[s:m.start() + 300])[:480])
    break
