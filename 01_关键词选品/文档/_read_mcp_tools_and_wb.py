# -*- coding: utf-8 -*-
"""读本地的 MCP tools 规范 + 抓变更记录 + 查 WorkBuddy 的 MCP 细节。"""
import io
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/markdown,text/plain,text/html,*/*"}
BASE = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay"

# ---------- 1. 本地已存的 tools 规范 ----------
print("#" * 110)
print("# MCP 工具规范要点（2026-07-28）")
print("#" * 110)
try:
    t = io.open(BASE + r"\mcp_工具_Tools.md", encoding="utf-8").read()
except Exception:
    import glob
    f = glob.glob(BASE + r"\mcp_*Tools*.md") or glob.glob(BASE + r"\mcp_*.md")
    t = io.open(f[0], encoding="utf-8").read() if f else ""
    print("（用文件 %s）" % (f[0] if f else "无"))
print("长度 %d 字符\n" % len(t))
for kw in ["annotations", "readOnlyHint", "destructiveHint", "idempotentHint",
           "openWorldHint", "outputSchema", "structuredContent", "title",
           "progress", "isError", "listChanged"]:
    n = len(re.findall(re.escape(kw), t))
    if n:
        m = re.search(r"[^\n]{0,160}%s[^\n]{0,260}" % re.escape(kw), t)
        print("  %-20s %2d 次 ｜ %s" % (kw, n, re.sub(r"\s+", " ", m.group(0))[:300]))
print()
print("--- 工具定义示例（规范里的 JSON）---")
m = re.search(r"```json\s*(\{.*?\})\s*```", t, re.S)
if m:
    print(m.group(1)[:1500])

# ---------- 2. 变更记录 ----------
print()
print("#" * 110)
print("# 2026-07-28 关键变更")
print("#" * 110)
for u in ["https://modelcontextprotocol.io/specification/2026-07-28/changelog.md",
          "https://modelcontextprotocol.io/specification/2026-07-28/key-changes.md"]:
    r = requests.get(u, headers=H, timeout=45)
    print("%s → HTTP %s ｜ %d 字节" % (u.split("/")[-1], r.status_code, len(r.content)))
    if r.status_code == 200:
        io.open(BASE + r"\mcp_change.md", "w", encoding="utf-8").write(r.text)
        print(r.text[:2500])
        break

# ---------- 3. WorkBuddy / CodeBuddy 的 MCP 文档 ----------
print()
print("#" * 110)
print("# WorkBuddy / CodeBuddy 的 MCP 支持细节")
print("#" * 110)
for u in ["https://cnb.cool/codebuddy/codebuddy-code/-/blob/main/README.md",
          "https://raw.githubusercontent.com/search?q=codebuddy+mcp",
          "https://cloud.tencent.com.cn/developer/article/2698011"]:
    try:
        r = requests.get(u, headers=H, timeout=45)
        print("%s → HTTP %s ｜ %d 字节" % (u[:70], r.status_code, len(r.content)))
        if r.status_code == 200 and "codebuddy" in u:
            io.open(BASE + r"\wb_doc.md", "w", encoding="utf-8").write(r.text)
            print(r.text[:1200])
    except Exception as exc:
        print("%s 异常 %s" % (u[:60], str(exc)[:60]))
