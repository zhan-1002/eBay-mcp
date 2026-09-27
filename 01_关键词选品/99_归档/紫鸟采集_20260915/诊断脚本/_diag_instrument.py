# -*- coding: utf-8 -*-
"""真跑一次 collect_on_page，并同时统计跳过原因 + 详情落地情况（不写产物）。

用 monkeypatch 观测真实调用路径，不修改项目文件。
"""
import json
import os
import shutil
import sys
import time
from collections import Counter

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)
shutil.rmtree(os.path.join(SCRIPTS, "__pycache__"), ignore_errors=True)

import collect_ziniao as cz  # noqa: E402
from ziniao_runtime import (  # noqa: E402
    exit_ziniao, get_browser_list, kill_ziniao, match_store, open_store,
    start_ziniao, wait_for_server,
)

STORE, SITE, KW, MAXN, DETAIL = "haihu_8075", "uk", "wireless earbuds", 120, 10

# --- 观测打桩 ---
STAT = Counter()
_orig_title = cz._card_title
_orig_detail = cz.fetch_item_detail


def patched_title(card):
    t = _orig_title(card)
    if not t:
        STAT["标题为空"] += 1
    elif t.lower() in {x.lower() for x in cz.PLACEHOLDER_TITLES}:
        STAT["标题=占位"] += 1
    return t


def patched_detail(page, item, host):
    before = len(item.get("item_specifics") or [])
    _orig_detail(page, item, host)
    after = len(item.get("item_specifics") or [])
    STAT["详情调用"] += 1
    if after > before:
        STAT["详情成功"] += 1
    else:
        STAT["详情失败(空)"] += 1
        print("   [观测] #%s 详情后仍为空: %s"
              % (item.get("position"), (item.get("title") or "")[:44]))


cz._card_title = patched_title
cz.fetch_item_detail = patched_detail

api_port = None
try:
    kill_ziniao()
    api_port = start_ziniao()
    assert wait_for_server(api_port), "服务未就绪"
    stores = get_browser_list(api_port)
    zn = match_store(stores, STORE)
    info = {s.get("browserName"): s for s in stores}[zn]
    dport = open_store(api_port, info.get("browserOauth", "")).get("debuggingPort")
    print("店铺=%s port=%s" % (zn, dport))
    time.sleep(10)

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    for attempt in range(1, 6):
        try:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % dport)
            break
        except Exception as exc:
            print("CDP 第%d次失败 %s" % (attempt, str(exc)[:60]))
            time.sleep(5)
    page = browser.contexts[0].pages[0]

    payload = cz.collect_on_page(page, KW, SITE, MAXN, DETAIL)
    its = payload["items"]

    print("\n" + "=" * 70)
    print("观测统计:")
    for k, v in STAT.most_common():
        print("   %-14s %d" % (k, v))
    print("=" * 70)
    print("collect_on_page 返回 %d 条" % len(its))
    print("有 specifics 的位置 = %s" % [it["position"] for it in its if it.get("item_specifics")])
    print("title 带 a11y 尾巴 = %d 条"
          % sum(1 for it in its if "opens in a new window" in (it["title"] or "").lower()))
    print("categories 非空 = %d 条" % sum(1 for it in its if it.get("categories")))
    print()
    for it in its[:10]:
        print("   #%-3d specs=%-3d promoted=%-5s leaf=%-12s %s"
              % (it["position"], len(it.get("item_specifics") or []), it["is_sponsored"],
                 it.get("leaf_category_ids"), (it["title"] or "")[:46]))

    try:
        browser.close()
    except Exception:
        pass
finally:
    if api_port:
        try:
            exit_ziniao(api_port)
        except Exception:
            pass
        kill_ziniao()
