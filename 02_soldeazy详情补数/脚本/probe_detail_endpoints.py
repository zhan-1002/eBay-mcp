# -*- coding: utf-8 -*-
"""试出 dsheet 详情的真实 URL / 接口（只读 GET，不改数据）。"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from soldeazy_client import SessionExpired, SoldeazyClient  # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "输出", "探查"))
ROW = "4153428"

CANDIDATES = [
    ("desclist", "/app/soldeazy/datasheet_ajax/desc_preview", {"dsheet_row_id": ROW}),
    ("datasheet_get", "/app/soldeazy/datasheet", {"dsheet_row_id": ROW}),
    ("datasheet_mode", "/app/soldeazy/datasheet", {"mode": "dsheet_detail", "dsheet_row_id": ROW}),
    ("createidx", "/app/soldeazy/datasheet-create/index", {"dsheet_row_id": ROW}),
    ("ajax_dsheet", "/app/soldeazy/datasheet_ajax", {"dsheet_row_id": ROW}),
]

c = SoldeazyClient()


def strip(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


for tag, path, params in CANDIDATES:
    print("\n" + "=" * 78)
    print("GET %s  params=%s" % (path, params))
    print("=" * 78)
    try:
        r = c.get(path, params=params, allow_redirects=True)
    except SessionExpired as exc:
        print("  [会话过期] %s" % exc)
        sys.exit(3)
    except Exception as exc:
        print("  请求异常: %s" % str(exc)[:120])
        continue
    body = r.text
    print("  HTTP %s | 最终 URL %s | 长度 %d" % (r.status_code, r.url[:100], len(body)))
    ct = r.headers.get("content-type", "")
    print("  content-type: %s" % ct[:60])

    if body.strip().startswith(("{", "[")):
        print("  → 返回 JSON:")
        print("    %s" % body[:600])
        p = os.path.join(OUT, "detail_%s.json" % tag)
    else:
        txt = strip(body)
        print("  可见文本前 300: %s" % txt[:300])
        p = os.path.join(OUT, "detail_%s.html" % tag)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    print("  已存: %s" % os.path.basename(p))

    # 关键字段探测
    for key in ("Brand", "品牌", "MPN", "EAN", "Color", "Colour", "Model", "型号",
                "Title", "标题", "描述", "Description"):
        n = len(re.findall(re.escape(key), body))
        if n:
            print("    含 %-12s %d 次" % (key, n))
