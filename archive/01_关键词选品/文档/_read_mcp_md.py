# -*- coding: utf-8 -*-
"""抓 MCP 规范的 .md 纯文本版（文档站一般支持），拿到干净内容。"""
import io
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/markdown,text/plain,*/*"}

VER = "2026-07-28"
URLS = [
    ("文档索引 llms.txt", "https://modelcontextprotocol.io/llms.txt"),
    ("生命周期/初始化", "https://modelcontextprotocol.io/specification/%s/basic/lifecycle.md" % VER),
    ("工具 Tools", "https://modelcontextprotocol.io/specification/%s/server/tools.md" % VER),
    ("资源 Resources", "https://modelcontextprotocol.io/specification/%s/server/resources.md" % VER),
    ("提示词 Prompts", "https://modelcontextprotocol.io/specification/%s/server/prompts.md" % VER),
    ("工具变更记录", "https://modelcontextprotocol.io/specification/%s/changelog.md" % VER),
]

for label, url in URLS:
    print("=" * 110)
    print("%s  ←  %s" % (label, url))
    print("=" * 110)
    try:
        r = requests.get(url, headers=H, timeout=45)
        print("HTTP %s ｜ %d 字节 ｜ type=%s"
              % (r.status_code, len(r.content), r.headers.get("content-type", "")[:40]))
        if r.status_code != 200:
            print("  %s" % r.text[:200].replace("\n", " "))
            print()
            continue
        t = r.text
        io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\mcp_%s.md"
                % re.sub(r"\W+", "_", label)[:28], "w", encoding="utf-8").write(t)
        print("  已存，%d 字符" % len(t))
        if "llms.txt" in url:
            print(t[:2500])
        else:
            print("\n--- 前 2200 字符 ---")
            print(t[:2200])
    except Exception as exc:
        print("  异常 %s" % str(exc)[:120])
    print()
