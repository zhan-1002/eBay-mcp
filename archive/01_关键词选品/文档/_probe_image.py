# -*- coding: utf-8 -*-
"""看搜索页卡片里主图 URL 的存放结构（用已 dump 的 HTML，不联网）。"""
import glob
import os
import re

DOM = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\输出\_dom"
cands = sorted(glob.glob(os.path.join(DOM, "*.html")))
print("可用 dump：")
for c in cands:
    print("   %-42s %.1f MB" % (os.path.basename(c), os.path.getsize(c) / 1e6))

# 优先用搜索页 dump（cards_*.html 是搜索页）
search = [c for c in cands if "cards_" in os.path.basename(c)] or cands
p = search[-1]
print("\n分析: %s" % os.path.basename(p))
html = open(p, encoding="utf-8", errors="replace").read()
print("HTML 长度 %.1f MB" % (len(html) / 1e6))

print("\n=== 1. <img> 标签统计（src 域名分布）===")
doms = {}
imgs = re.findall(r"<img\b[^>]*>", html)
print("img 标签数: %d" % len(imgs))
for tag in imgs:
    m = re.search(r'src="([^"]+)"', tag)
    if not m:
        continue
    u = m.group(1)
    d = re.sub(r"^(https?://[^/]+).*", r"\1", u)
    doms[d] = doms.get(d, 0) + 1
for d, c in sorted(doms.items(), key=lambda kv: -kv[1])[:8]:
    print("   %-42s %d" % (d, c))

print("\n=== 2. 前 3 个 imgs.ebayimg.com 的 img 标签原文 ===")
n = 0
for tag in imgs:
    if "ebayimg" not in tag:
        continue
    print("   %s" % tag[:300])
    n += 1
    if n >= 3:
        break

print("\n=== 3. 卡片容器里的图（li.s-card 内）===")
cards = re.split(r'<li[^>]*class="[^"]*s-card', html)
print("切出的卡片片段数: %d" % (len(cards) - 1))
for i, seg in enumerate(cards[1:4], 1):
    seg = seg[:6000]
    im = re.findall(r'<img\b[^>]*>', seg)
    print("  卡片 #%d 里的 img 数: %d" % (i, len(im)))
    for t in im[:2]:
        print("     %s" % t[:260])

print("\n=== 4. srcset / data-src 等懒加载属性是否出现 ===")
for attr in ("data-src", "srcset", "data-image", "loading=", "data-defer-load"):
    print("   %-16s 出现 %d 次" % (attr, html.count(attr)))
