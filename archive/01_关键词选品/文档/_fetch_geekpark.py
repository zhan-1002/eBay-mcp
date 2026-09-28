# -*- coding: utf-8 -*-
"""抓取用户给的链接正文（极客公园），提取可读文本。"""
import io
import re

import requests

URL = "https://www.geekpark.net/news/286803"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

r = requests.get(URL, headers=H, timeout=45)
print("HTTP %s ｜ %d 字节 ｜ %s" % (r.status_code, len(r.content),
                                 r.headers.get("content-type")))
r.encoding = r.apparent_encoding or "utf-8"
html = r.text

# 标题
m = re.search(r"(?is)<title>(.*?)</title>", html)
print("页面标题: %s" % (m.group(1).strip() if m else "-"))

# 正文：极客公园的文章通常在 <div class="article-content"> 或 <article>
body = ""
for pat in (r'(?is)<div[^>]*class="[^"]*article[-_]?content[^"]*"[^>]*>(.*?)</div>\s*</div>',
            r"(?is)<article[^>]*>(.*?)</article>",
            r'(?is)<div[^>]*class="[^"]*post[-_]?content[^"]*"[^>]*>(.*?)</div>'):
    mm = re.search(pat, html)
    if mm and len(mm.group(1)) > 400:
        body = mm.group(1)
        break
if not body:
    body = html

body = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", body)
body = re.sub(r"(?is)<br\s*/?>", "\n", body)
body = re.sub(r"(?is)</(p|div|li|h[1-6])>", "\n", body)
text = re.sub(r"(?s)<[^>]+>", " ", body)
for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
             ("&quot;", '"'), ("&#39;", "'"), ("&ldquo;", "“"), ("&rdquo;", "”")):
    text = text.replace(a, b)
text = re.sub(r"[ \t]+", " ", text)
text = re.sub(r"\n\s*\n+", "\n", text).strip()

print("正文长度 %d" % len(text))
io.open(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\gk_article.txt", "w",
        encoding="utf-8").write(text)
print("=" * 90)
print(text[:3000])
