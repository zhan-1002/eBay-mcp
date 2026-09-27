# -*- coding: utf-8 -*-
"""找 a.dsrid / Detail 的确切处理逻辑（决定详情怎么取）。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.normpath(os.path.join(HERE, "..", "输出", "探查", "search_rowid_uk.html"))
html = open(P, encoding="utf-8", errors="replace").read()

print("=== ① 含 'dsrid' 的所有片段（去重、去 CSS）===")
seen = set()
for m in re.finditer(r"dsrid", html):
    i = m.start()
    seg = re.sub(r"\s+", " ", html[max(0, i - 400):i + 400])
    if seg in seen:
        continue
    seen.add(seg)
    if "<style" in seg[:200] and "{" in seg:
        continue
    print("\n  …%s…" % seg[:700])

print("\n\n=== ② 含 'dsheet_row_id' 的所有 JS 用法 ===")
seen2 = set()
for m in re.finditer(r"dsheet_row_id", html):
    i = m.start()
    seg = re.sub(r"\s+", " ", html[max(0, i - 260):i + 300])
    if seg in seen2:
        continue
    seen2.add(seg)
    if "$" in seg or "href" in seg or "post" in seg or "get" in seg:
        print("\n  …%s…" % seg[:560])

print("\n\n=== ③ 页面里所有 /app/soldeazy/... 形式的 href（排除 css/img/js）===")
hrefs = set()
for m in re.finditer(r"""href=['"]([^'"]+)['"]""", html):
    u = m.group(1)
    if "/app/soldeazy/" in u and not any(u.endswith(x) for x in (".css", ".js", ".png", ".jpg")):
        hrefs.add(u.split("?")[0])
for u in sorted(hrefs):
    print("   %s" % u)

print("\n\n=== ④ general_js.js / datatable.js 里的 action-btn detail 处理 ===")
import requests
s = requests.Session()
for js in ("/app/js/datatable.js", "/app/js/general_js.js"):
    try:
        r = s.get("https://stiger.soldeazy.com" + js, timeout=20, verify=False)
    except Exception as exc:
        print("  %s 拉取失败 %s" % (js, exc))
        continue
    t = r.text
    print("\n  --- %s (%d 字节) ---" % (js, len(t)))
    for pat in (r"dsrid", r"action-btn", r"detail"):
        for m in re.finditer(pat, t):
            i = m.start()
            seg = re.sub(r"\s+", " ", t[max(0, i - 200):i + 240])
            if "$" in seg or "on(" in seg or "href" in seg or "click" in seg:
                print("     [%s] …%s…" % (pat, seg[:300]))
                break
