# -*- coding: utf-8 -*-
"""取出 WorkBuddy 的 MCP 配置格式（官方文章关键段 + 现成包的 mcp.json 示例）。"""
import glob
import io
import os
import re
import json

import requests

H = {"User-Agent": "Mozilla/5.0"}

# 找到上一次抓下来的文章正文
cands = glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\wb_article.txt")
cands += glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\**\wb_article.txt",
                   recursive=True)
print("文章正文文件: %s" % (cands or "没找到，下面重新抓"))

text = ""
if cands:
    text = io.open(cands[0], encoding="utf-8").read()
else:
    r = requests.get("https://cloud.tencent.com.cn/developer/article/2698011",
                     headers=H, timeout=45)
    h = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", r.text)
    h = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|pre)>", "\n", h)
    text = re.sub(r"(?s)<[^>]+>", " ", h)

# 去掉文章头部导航噪音：从"摘要"开始
i = text.find("摘要")
body = text[i:] if i > 0 else text
body = re.sub(r"\s+", " ", body)

print()
print("=" * 94)
print("腾讯云官方文章（WorkBuddy 连接器 = MCP）关键内容")
print("=" * 94)
for kw in ["一、WorkBuddy 的连接器", "1.1", "1.2", "配置自定义", "步骤", "mcp.json",
           "stdio", "SSE", "HTTP", "命令", "参数", "npx"]:
    for m in re.finditer(re.escape(kw), body):
        s = max(0, m.start() - 80)
        print("  · %s" % body[s:m.start() + 260].strip()[:330])
        break

print()
print("=" * 94)
print("baitong-mcp-remote 的 WorkBuddy 配置示例（能证明走 stdio + mcp.json）")
print("=" * 94)
d = requests.get("https://registry.npmjs.org/baitong-mcp-remote", headers=H, timeout=40).json()
print(d.get("readme") or "(无 readme)")
