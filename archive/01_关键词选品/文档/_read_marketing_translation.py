# -*- coding: utf-8 -*-
"""① 读 Buy Marketing / Translation 规格，拿到准确路径与请求体格式
   ② 用正确格式把翻译 API 打通（400 → 200）
"""
import json
import sys

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
API = "https://api.ebay.com"

sys.path.insert(0, r"\\192.168.120.11\Ebay部门\ebay看板\keyword_research\scripts")
import ebay_auth  # noqa: E402

tok = ebay_auth.EbayAuth(verbose=False).token()
A = {"Authorization": "Bearer " + tok, "Accept": "application/json",
     "Content-Type": "application/json", "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}

SPECS = {
    "Buy Marketing": "https://api.apis.guru/v2/specs/ebay.com/buy-marketing/v1_beta.1.0/swagger.json",
    "Translation": "https://api.apis.guru/v2/specs/ebay.com/commerce-translation/1/openapi.json",
}
for name, url in SPECS.items():
    print("=" * 96)
    print("【%s】%s" % (name, url))
    print("=" * 96)
    try:
        s = requests.get(url, headers=H, timeout=60).json()
        srv = (s.get("servers") or [{}])[0]
        base = ((srv.get("variables") or {}).get("basePath") or {}).get("default", "")
        print("host=%s basePath=%s" % (srv.get("url", "-"), base))
        for p, ops in (s.get("paths") or {}).items():
            for m, op in ops.items():
                if m not in ("get", "post", "put", "delete"):
                    continue
                print("  %-46s %-5s %s" % (p, m.upper(), (op.get("summary") or "")[:56]))
                if name == "Translation":
                    rb = (op.get("requestBody") or {}).get("content") or {}
                    for ct, spec in rb.items():
                        sch = spec.get("schema") or {}
                        print("      body(%s): %s" % (ct, json.dumps(sch, ensure_ascii=False)[:300]))
                params = op.get("parameters") or []
                need = [x.get("name") for x in params if x.get("required")]
                if need:
                    print("      必填参数: %s" % need)
    except Exception as exc:
        print("  取规格失败 %s" % str(exc)[:110])
    print()

print("=" * 96)
print("用规格里的格式重试翻译 API")
print("=" * 96)
VARIANTS = [
    ("text 为字符串数组 / 带 context", 
     {"from": "en", "to": "de", "text": ["wireless earbuds bluetooth 5.4"]}),
    ("translationContext 字段",
     {"from": "en", "to": "de", "text": ["wireless earbuds"],
      "translationContext": "ITEM_TITLE"}),
    ("只有 text（不带 from/to）", {"text": ["wireless earbuds"]}),
]
for label, body in VARIANTS:
    r = requests.post(API + "/commerce/translation/v1_beta/translate",
                      headers=A, json=body, timeout=35)
    print("  %-32s HTTP %s ｜ %s" % (label, r.status_code,
                                    r.text[:170].replace("\n", " ")))
