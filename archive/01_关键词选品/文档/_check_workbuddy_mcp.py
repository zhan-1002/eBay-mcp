# -*- coding: utf-8 -*-
"""查 WorkBuddy 对 MCP 的支持情况（抓官方说明 + npm 包文档，不靠搜索摘要）。

要回答：
  1. WorkBuddy 支不支持 MCP Server？
  2. 支持哪些传输方式（本地 stdio / 远程 HTTP-SSE）？
  3. 配置格式长什么样？能不能挂"本地命令 + 参数"这种 stdio server（我们要用 Python）？
"""
import json
import re
import io

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}


def text_of(html):
    """粗暴去标签，保留可读文本。"""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|pre|code)>", "\n", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'")):
        txt = txt.replace(a, b)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def grep(txt, keys, ctx=160, limit=6):
    """按关键词找上下文片段。"""
    out = []
    low = txt.lower()
    for k in keys:
        for m in re.finditer(re.escape(k.lower()), low):
            s = max(0, m.start() - ctx)
            out.append("[%s] …%s…" % (k, txt[s:m.start() + ctx].replace("\n", " ")))
            if len(out) >= limit:
                return out
    return out


# ---------- 1. npm registry：workbuddy-mcp 的元数据与 readme ----------
print("=" * 92)
print("一、npm 包 workbuddy-mcp")
print("=" * 92)
for pkg in ("workbuddy-mcp", "baitong-mcp-remote", "stratagate-workbuddy"):
    try:
        r = requests.get("https://registry.npmjs.org/" + pkg, headers=H, timeout=40)
        if r.status_code != 200:
            print("%-24s HTTP %s（不存在或不可访问）" % (pkg, r.status_code))
            continue
        d = r.json()
        latest = (d.get("dist-tags") or {}).get("latest")
        v = (d.get("versions") or {}).get(latest) or {}
        print("%-24s ✅ 存在 ｜ 最新版 %s ｜ %s" % (pkg, latest,
                                                 (d.get("description") or "")[:70]))
        print("     主页: %s" % (d.get("homepage") or v.get("homepage") or "-"))
        print("     仓库: %s" % ((d.get("repository") or {}).get("url") or "-"))
        readme = d.get("readme") or v.get("readme") or ""
        if readme:
            print("     readme 长度 %d，命中关键词：" % len(readme))
            for line in grep(text_of(readme), ["mcp", "stdio", "sse", "http", "json",
                                               "配置", "command", "args", "env"], 120, 8):
                print("       %s" % line[:220])
    except Exception as exc:
        print("%-24s 异常 %s" % (pkg, str(exc)[:80]))

# ---------- 2. 腾讯云那篇官方说明 ----------
print()
print("=" * 92)
print("二、腾讯云文章《如何在 WorkBuddy 中使用 MCP Server？》")
print("=" * 92)
url = "https://cloud.tencent.com.cn/developer/article/2698011"
try:
    r = requests.get(url, headers=H, timeout=45)
    print("HTTP %s ｜ 长度 %d" % (r.status_code, len(r.content)))
    if r.status_code == 200:
        t = text_of(r.text)
        io.open("C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\wb_article.txt", "w", encoding="utf-8").write(t)
        print("正文长度 %d 字（已存 wb_article.txt）" % len(t))
        print()
        print("关键词命中：")
        for line in grep(t, ["MCP", "stdio", "SSE", "HTTP", "配置", "命令", "npx",
                             "uvx", "python", "本地", "json"], 200, 14):
            print("  %s" % line[:300])
    else:
        print("被拦或需登录，正文如下：%s" % r.text[:200])
except Exception as exc:
    print("异常 %s" % str(exc)[:120])
