# -*- coding: utf-8 -*-
"""探 Soldeazy dsheet_list 页面结构：搜索参数、表单字段、返回内容、分页。

前置：先跑 soldeazy_login.py 存下会话。
用法:
  python probe_soldeazy_atlas.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from soldeazy_client import SessionExpired, SoldeazyClient, TARGET_PATH  # noqa: E402

OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))


def dump_forms(html):
    print("\n=== <form> 与 <input>/<select> 字段 ===")
    forms = re.findall(r"<form\b[^>]*>", html, re.I)
    for f in forms:
        print("  FORM %s" % f[:200])
    if not forms:
        print("  （无 form 标签 → 可能是 ajax/JS 渲染）")
    n = 0
    for m in re.finditer(r"<(input|select|textarea)\b[^>]*>", html, re.I):
        tag = m.group(0)
        info = {"tag": m.group(1).lower()}
        for k in ("name", "id", "type", "placeholder", "value", "class"):
            mm = re.search(r'%s="([^"]*)"' % k, tag)
            if mm:
                info[k] = mm.group(1)[:50]
        if info.get("name") or info.get("id"):
            print("  %s" % info)
            n += 1
        if n > 40:
            break
    print("  （共打印 %d 个控件）" % n)


def dump_ajax(html):
    print("\n=== 页面里的 ajax / 接口 URL ===")
    pats = (r"""url\s*:\s*['"]([^'"]+)['"]""",
            r"""['"](/app/soldeazy/[A-Za-z0-9_/\-]{3,90})['"]""",
            r"""['"](/ssl/[A-Za-z0-9_/\-]{3,90})['"]""")
    found = set()
    for p in pats:
        for m in re.finditer(p, html):
            u = m.group(1)
            if any(k in u.lower() for k in ("dsheet", "datasheet", "ajax", "json",
                                             "list", "search", "export", "detail")):
                found.add(u)
    for u in sorted(found)[:40]:
        print("  %s" % u)
    if not found:
        print("  （没找到明显的接口 URL）")


def dump_tables(html):
    print("\n=== 页面里的表头线索（th / 列名）===")
    ths = re.findall(r"<th\b[^>]*>(.*?)</th>", html, re.S | re.I)
    cleaned = []
    for t in ths:
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            cleaned.append(t[:36])
    print("  th 共 %d 个: %s" % (len(cleaned), cleaned[:40]))

    print("\n=== data-* 属性里的列定义 ===")
    for m in re.finditer(r'data-\w+="[^"]{0,150}"', html):
        t = m.group(0)
        if re.search(r"(?i)column|field|key|dsheet|sku|product", t):
            print("  %s" % t[:170])


def dump_text(html):
    print("\n=== 可见文本前 500 字 ===")
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    print("  %s" % t[:500])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        c = SoldeazyClient()
    except SessionExpired as exc:
        print("[需要登录] %s" % exc)
        return 2

    print("会话保存于: %s" % c.saved_at)
    try:
        html = c.dsheet_list_html()
    except SessionExpired as exc:
        print("[会话过期] %s" % exc)
        return 3

    print("dsheet_list 页面长度: %d 字符" % len(html))
    path = os.path.join(OUT_DIR, "dsheet_list.html")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("已保存原始 HTML: %s" % path)

    t = re.search(r"<title[^>]*>([^<]*)</title>", html, re.I)
    print("title: %s" % (t.group(1).strip() if t else "(无)"))

    dump_text(html)
    dump_tables(html)
    dump_forms(html)
    dump_ajax(html)

    print("\n=== 页面内的 JS bundle ===")
    for m in re.finditer(r'<script[^>]*src="([^"]+)"', html, re.I):
        print("  %s" % m.group(1)[:130])
    return 0


if __name__ == "__main__":
    sys.exit(main())
