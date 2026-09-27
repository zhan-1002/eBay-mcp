# -*- coding: utf-8 -*-
"""读取新增数据表弹层的真实选项：商店 / 模板 / 档案 / 站点，为试跑做准备。"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
c = SoldeazyClient()
html = c.dsheet_list_html()
print("dsheet_list 长度: %d" % len(html))
with open(os.path.join(OUT, "dsheet_list_live.html"), "w", encoding="utf-8", newline="\n") as f:
    f.write(html)


def options_of(html, select_id):
    m = re.search(r"<select[^>]*id=['\"]%s['\"][^>]*>(.*?)</select>" % re.escape(select_id),
                  html, re.S | re.I)
    if not m:
        m = re.search(r"<select[^>]*name=['\"]%s['\"][^>]*>(.*?)</select>" % re.escape(select_id),
                      html, re.S | re.I)
    if not m:
        return None
    opts = re.findall(r"<option[^>]*value=['\"]([^'\"]*)['\"][^>]*>(.*?)</option>", m.group(1), re.S | re.I)
    out = []
    for v, t in opts:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()
        out.append((v, t))
    return out


for sel in ("listing_spy_shop", "listing_spy_template", "listing_spy_profile",
            "lstShopInit", "listingSiteInit", "listbizprofileInit"):
    opts = options_of(html, sel)
    print("\n=== %s ===" % sel)
    if opts is None:
        print("   没找到该 select")
        continue
    print("   共 %d 个选项" % len(opts))
    for v, t in opts[:60]:
        print("     value=%-8s %s" % (v, t))
    if len(opts) > 60:
        print("     ...（只显示前 60）")

print("\n=== 协议状态 ===")
m = re.search(r"listing_spy_agreement[\"'][^>]*style=['\"]([^'\"]*)", html)
print("  listing_spy_agreement style: %s" % (m.group(1) if m else "?"))
m2 = re.search(r"listing_spy_listing_form[\"'][^>]*style=['\"]([^'\"]*)", html)
print("  listing_spy_listing_form style: %s" % (m2.group(1) if m2 else "?"))

print("\n=== 模板/档案相关其它 select ===")
for m in re.finditer(r"<select[^>]*(?:id|name)=['\"]([^'\"]*(?:template|profile)[^'\"]*)['\"]", html, re.I):
    print("  %s" % m.group(1))
