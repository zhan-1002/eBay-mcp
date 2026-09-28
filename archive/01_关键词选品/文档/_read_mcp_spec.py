# -*- coding: utf-8 -*-
"""查 MCP 协议文档 + WorkBuddy 的 MCP 支持细节（协议版本/传输/能力）。

要确认的：
  1. MCP 当前协议版本、有哪些原语（tools/resources/prompts/elicitation…）
  2. 工具定义的完整规范（annotations / outputSchema / structuredContent）
  3. 长任务怎么做（progress / cancellation）
  4. WorkBuddy 支持到什么程度（版本、传输、配置）
"""
import io
import json
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/html,application/json,text/plain,*/*;q=0.8"}

TARGETS = [
    ("MCP 规范首页", "https://modelcontextprotocol.io/specification/latest"),
    ("MCP 规范目录", "https://modelcontextprotocol.io/specification/"),
    ("MCP 工具规范", "https://modelcontextprotocol.io/specification/latest/server/tools"),
    ("MCP 资源规范", "https://modelcontextprotocol.io/specification/latest/server/resources"),
    ("MCP 提示词规范", "https://modelcontextprotocol.io/specification/latest/server/prompts"),
    ("MCP Python SDK", "https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md"),
    ("MCP 规范 schema（版本与能力）",
     "https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2025-06-18/schema.json"),
]


def text_of(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|pre|code)>", "\n", html)
    t = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'")):
        t = t.replace(a, b)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


for label, url in TARGETS:
    print("=" * 110)
    print("%s\n%s" % (label, url))
    print("=" * 110)
    try:
        r = requests.get(url, headers=H, timeout=45)
        print("HTTP %s ｜ %d 字节" % (r.status_code, len(r.content)))
        if r.status_code != 200:
            print()
            continue
        body = r.text
        if url.endswith(".json"):
            try:
                d = json.loads(body)
                # 找协议版本
                for m in re.finditer(r'"protocolVersion"[^}]{0,400}', body):
                    print("  %s" % m.group(0)[:400])
                    break
                print("  schema title: %s" % (d.get("title") or "-"))
                props = list(((d.get("definitions") or d.get("$defs") or {})).keys())
                print("  定义数量: %d" % len(props))
                for k in props:
                    if re.search(r"Tool|Resource|Prompt|Elicit|Progress|Cancel",
                                 k, re.I):
                        print("     · %s" % k)
            except Exception as exc:
                print("  JSON 解析失败 %s" % exc)
            print()
            continue
        t = text_of(body)
        io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\mcp_%s.txt"
                % re.sub(r"\W+", "_", label)[:24], "w", encoding="utf-8").write(t)
        print("  正文 %d 字" % len(t))
        # 打印前若干行
        lines = [x for x in t.splitlines() if x.strip()]
        print("\n".join(lines[:24]))
    except Exception as exc:
        print("  异常 %s" % str(exc)[:120])
    print()
