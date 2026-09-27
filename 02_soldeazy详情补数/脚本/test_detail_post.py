# -*- coding: utf-8 -*-
"""复刻 a.detail 的 POST（table_action=detail&mode=dsheet_datatable），抓详情页字段。"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
ROW = "4153428"

# 先看浏览器抓到的完整 body 有哪些字段
clicked = sorted(__import__("glob").glob(os.path.join(OUT, "click_detail_*.html")))[-1]
print("参考的点击后页面: %s" % os.path.basename(clicked))

# 完整表单字段（从 dsheet_list 页面里抄全，保证服务端拿得到上下文）
FORM_FIELDS = [
    "txtproductcode", "txtdsheetrowid", "listsite", "listformat", "listduration",
    "txtitemid", "listactive", "listitemcountry", "listisvariation", "listattrgroup",
    "txtattrval", "listattrkey", "listtemplate", "listpromotion", "listpromotelisting",
    "listfitment", "listbizprofile", "txtshopcategory", "txtebaycategory",
    "listwarehouse", "listschedule", "txtskuvendor", "txttag", "txtfilename",
    "listdate", "listsortby", "listmachinetranslated", "listtranslated", "fontsize",
    "limit", "page",
]

c = SoldeazyClient()
data = {k: "" for k in FORM_FIELDS}
data.update({
    "table_action": "detail",
    "mode": "dsheet_datatable",
    "second_mode": "dsheet_list",
    "txtdsheetrowid": ROW,
    "btn_search": "搜索",
    "page": "1",
    "limit": "50",
})
print("\nPOST /app/soldeazy/datasheet  (table_action=detail)")
try:
    r = c.post("/app/soldeazy/datasheet", data=data)
except SessionExpired as exc:
    print("[会话过期] %s" % exc)
    sys.exit(3)
html = r.text
print("HTTP %s | 长度 %d | content-type %s"
      % (r.status_code, len(html), r.headers.get("content-type", "")[:40]))
p = os.path.join(OUT, "detail_page_%s.html" % ROW)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(html)
print("已存: %s" % os.path.basename(p))


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


print("\n=== 可见文本前 700 字 ===")
print("  %s" % strip(html)[:700])

print("\n=== 是否为详情页（判断标志）===")
flags = {
    "含 form action=datasheet-create": bool(re.search(r"datasheet-create", html)),
    "含 item specific 类字段": bool(re.search(r"(?i)item.?specific", html)),
    "含 'Brand' 标签": len(re.findall(r"Brand", html)),
    "含 'EAN' ": len(re.findall(r"EAN", html)),
    "含 '品牌'": len(re.findall(r"品牌", html)),
    "含 物品编号": len(re.findall(r"物品编号", html)),
    "含 dsheet_row_id 值": len(re.findall(re.escape(ROW), html)),
}
for k, v in flags.items():
    print("  %-32s %s" % (k, v))

print("\n=== 找出所有 input/select/textarea 的 name（前 60）===")
names = []
for m in re.finditer(r"<(input|select|textarea)\b[^>]*name=['\"]([^'\"]+)['\"][^>]*>", html, re.I):
    tag, nm = m.group(1).lower(), m.group(2)
    if nm not in names:
        names.append(nm)
print("  共 %d 个：" % len(names))
for i in range(0, min(len(names), 60), 5):
    print("    %s" % names[i:i + 5])

print("\n=== 找字段值（label 附近的 input value）===")
for key in ("Brand", "MPN", "EAN", "Colour", "Color", "Model", "Type"):
    for m in re.finditer(r"<input[^>]*name=['\"]([^'\"]*%s[^'\"]*)['\"][^>]*>" % key, html, re.I):
        print("  %-8s → %s" % (key, m.group(0)[:200]))
