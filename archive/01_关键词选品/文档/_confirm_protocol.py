# -*- coding: utf-8 -*-
"""确认三件事：
  1. WorkBuddy 官方文章里关于 MCP 的实现细节（协议版本/传输）
  2. CodeBuddy（WorkBuddy 同源）的 MCP 文档
  3. MCP Python SDK 支持哪些协议版本（决定我们能不能靠 SDK 免写协议层）
"""
import io
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/markdown,text/plain,text/html,application/json,*/*"}
BASE = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay"

# ---------- 1. WorkBuddy 文章里搜 MCP 细节 ----------
print("#" * 108)
print("# WorkBuddy 官方文章：MCP 实现细节")
print("#" * 108)
try:
    t = io.open(BASE + r"\wb_article.txt", encoding="utf-8").read()
    print("文章 %d 字" % len(t))
    for kw in ["stdio", "SSE", "HTTP", "协议", "版本", "command", "args", "env",
               "mcp.json", "npx", "uvx", "python", "环境变量", "超时", "timeout"]:
        for m in re.finditer(re.escape(kw), t, re.I):
            s = max(0, m.start() - 150)
            frag = re.sub(r"\s+", " ", t[s:m.start() + 230])
            print("  [%-8s] %s" % (kw, frag[:300]))
            break
except Exception as exc:
    print("  读文章失败 %s" % exc)

# ---------- 2. CodeBuddy 的 MCP 文档 ----------
print()
print("#" * 108)
print("# CodeBuddy（WorkBuddy 同源）MCP 文档")
print("#" * 108)
CB = [
    ("cnb raw README", "https://cnb.cool/codebuddy/codebuddy-code/-/raw/main/README.md"),
    ("cnb raw docs/MCP.md",
     "https://cnb.cool/codebuddy/codebuddy-code/-/raw/main/docs/mcp.md"),
    ("cnb raw .mcp.json 示例",
     "https://cnb.cool/codebuddy/codebuddy-code/-/raw/main/docs/MCP.md"),
]
for label, u in CB:
    try:
        r = requests.get(u, headers=H, timeout=45)
        print("%-24s HTTP %s ｜ %d 字节" % (label, r.status_code, len(r.content)))
        if r.status_code == 200 and len(r.content) > 500 \
                and not r.text.lstrip().startswith("<!DOCTYPE"):
            io.open(BASE + r"\cb_mcp.md", "w", encoding="utf-8").write(r.text)
            print("  已存；MCP 相关片段：")
            for m in re.finditer(r"mcp|MCP", r.text):
                s = max(0, m.start() - 120)
                print("    …%s…" % re.sub(r"\s+", " ", r.text[s:m.start() + 240])[:330])
                break
            print("  前 800 字：\n%s" % r.text[:800])
    except Exception as exc:
        print("%-24s 异常 %s" % (label, str(exc)[:70]))

# ---------- 3. MCP Python SDK 的协议版本支持 ----------
print()
print("#" * 108)
print("# MCP Python SDK：支持哪些协议版本")
print("#" * 108)
for u in ["https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md",
          "https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/types.py"]:
    try:
        r = requests.get(u, headers=H, timeout=60)
        print("%s → HTTP %s ｜ %d 字节" % (u.split("/")[-1], r.status_code, len(r.content)))
        if r.status_code == 200:
            txt = r.text
            vers = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", txt)))
            print("  出现的日期版本: %s" % vers[:10])
            for kw in ["LATEST_PROTOCOL_VERSION", "SUPPORTED_PROTOCOL_VERSIONS",
                       "FastMCP", "streamable", "stdio"]:
                m = re.search(r"[^\n]{0,120}%s[^\n]{0,200}" % kw, txt)
                if m:
                    print("  [%s] %s" % (kw, re.sub(r"\s+", " ", m.group(0))[:260]))
    except Exception as exc:
        print("  异常 %s" % str(exc)[:80])
