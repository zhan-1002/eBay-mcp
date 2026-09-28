# -*- coding: utf-8 -*-
"""查 Terapeak 到底有没有 API。

三条线索：
  1. eBay Connect 2021 有个《Terapeak API》PDF（ebay.cn）→ 看它是什么性质、对谁开放
  2. npm 上有第三方 eBay/Terapeak MCP 包 → 看它们是怎么拿数据的（官方 API 还是爬页面）
  3. 结论要能回答：我们能不能拿到 Terapeak 的数据、代价是什么
"""
import io
import re
import zlib

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

print("=" * 92)
print("一、eBay Connect 2021《Terapeak API》PDF")
print("=" * 92)
pdf_url = "https://www.ebay.cn/uploadfile/pdf/eBayConnectGC2021-TerapeakAPI.pdf"
try:
    r = requests.get(pdf_url, headers=H, timeout=60)
    print("HTTP %s ｜ %d 字节 ｜ content-type=%s"
          % (r.status_code, len(r.content), r.headers.get("content-type")))
    if r.status_code == 200 and r.content[:4] == b"%PDF":
        io.open("C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_api.pdf", "wb").write(r.content)
        # 试着把 PDF 里的文本流解出来（FlateDecode）
        chunks = []
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", r.content, re.S):
            raw = m.group(1)
            try:
                dec = zlib.decompress(raw)
            except Exception:
                continue
            # 提取括号里的文本
            for t in re.findall(rb"\((?:\\.|[^\\()])*\)", dec):
                s = t[1:-1]
                s = s.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
                try:
                    chunks.append(s.decode("utf-8", "ignore"))
                except Exception:
                    pass
        txt = " ".join(chunks)
        txt = re.sub(r"\s+", " ", txt).strip()
        print("PDF 文本提取长度: %d" % len(txt))
        if txt:
            io.open("C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_api.txt", "w", encoding="utf-8").write(txt)
            print("前 1800 字：\n%s" % txt[:1800])
        else:
            print("（没解出文本 —— 可能是图片型 PDF 或用了对象流压缩）")
    else:
        print("不是 PDF 或抓不到：%s" % r.content[:120])
except Exception as exc:
    print("异常 %s" % str(exc)[:150])

print()
print("=" * 92)
print("二、第三方 MCP 包是怎么拿 Terapeak 数据的")
print("=" * 92)
for pkg in ("@bintangtimurlangit/ebay-terapeak-mcp", "ebay-mcp-remote-edition"):
    url = "https://registry.npmjs.org/" + pkg.replace("/", "%2F")
    try:
        r = requests.get(url, headers=H, timeout=40)
        if r.status_code != 200:
            print("%-42s HTTP %s" % (pkg, r.status_code))
            continue
        d = r.json()
        latest = (d.get("dist-tags") or {}).get("latest")
        print("%-42s ✅ v%s ｜ %s" % (pkg, latest, (d.get("description") or "")[:80]))
        rd = d.get("readme") or ""
        if rd:
            low = rd.lower()
            for kw in ("api", "browser", "scrape", "cookie", "login", "playwright",
                       "session", "official"):
                i = low.find(kw)
                if i >= 0:
                    print("     [%s] …%s…" % (kw, re.sub(r"\s+", " ", rd[max(0, i - 90):i + 150])))
        print()
    except Exception as exc:
        print("%-42s 异常 %s" % (pkg, str(exc)[:80]))
