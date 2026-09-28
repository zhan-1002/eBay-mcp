# -*- coding: utf-8 -*-
"""在浏览器点击后的真实页面里挖详情字段（name / label / value）。"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
P = sorted(glob.glob(os.path.join(OUT, "click_detail_*.html")))[-1]
html = open(P, encoding="utf-8", errors="replace").read()
print("文件: %s (%d 字符)\n" % (os.path.basename(P), len(html)))


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# 1) 标题验证是不是详情页
print("=== 是否含该商品标题 ===")
for kw in ("CAR WINDOW TINT", "4153428", "汽车膜-P"):
    print("  %-22s %d 次" % (kw, len(re.findall(re.escape(kw), html, re.I))))

# 2) EAN / Brand / MPN 出现的上下文
print("\n=== EAN 上下文（前 6 处）===")
n = 0
for m in re.finditer(r"EAN", html):
    i = m.start()
    seg = strip(html[max(0, i - 260):i + 320])
    if seg:
        print("  …%s…" % seg[:300])
        n += 1
    if n >= 6:
        break

print("\n=== Brand 上下文（前 5 处）===")
n = 0
for m in re.finditer(r"Brand", html):
    i = m.start()
    seg = strip(html[max(0, i - 200):i + 300])
    if seg:
        print("  …%s…" % seg[:280])
        n += 1
    if n >= 5:
        break

# 3) 属性区字段名（dsheet 字段）
print("\n=== name 里含 sku_/dsheet_/attr 的输入框（详情字段候选）===")
names = []
for m in re.finditer(r"<(input|select|textarea)\b[^>]*name=['\"]([^'\"]+)['\"][^>]*>", html, re.I):
    nm = m.group(2)
    if re.search(r"(?i)(sku_|dsheet_|attr|brand|mpn|ean|color|colour|model|specific)", nm):
        if nm not in names:
            names.append(nm)
            print("  %-40s | %s" % (nm, m.group(0)[:150]))

# 4) 页面里 label → value 结构（找 th/td 或 div 配对）
print("\n=== 找 label 文本（品牌/型号/颜色/物品描述）===")
for kw in ("品牌", "型号", "颜色", "物品描述", "商品描述", "描述", "类目", "类别"):
    for m in re.finditer(re.escape(kw), html):
        i = m.start()
        seg = strip(html[max(0, i - 120):i + 260])
        print("  [%s] …%s…" % (kw, seg[:210]))
        break

# 5) 是否是 fancybox / iframe 弹层
print("\n=== 弹层线索 ===")
for kw in ("fancybox", "iframe", "modal", "drawer", "dsheet-create"):
    print("  %-14s %d 次" % (kw, len(re.findall(kw, html, re.I))))

# 6) 脚本里切换详情视图的函数
print("\n=== 含 detail 的 JS 函数/绑定 ===")
for m in re.finditer(r"\$\('body'\)\.on\(\s*['\"]click['\"]\s*,\s*['\"]([^'\"]+)['\"]", html):
    print("  绑定: %s" % m.group(1))
for m in re.finditer(r"function\s+(\w*[Dd]etail\w*)\s*\(", html):
    print("  function %s" % m.group(1))
