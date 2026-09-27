# -*- coding: utf-8 -*-
"""端到端跑真实采集（120 条 + detail 10），在每个交接点打印 specifics/标题状态，
定位"采集到但没落进 JSON"的断点。

会真机跑一次（约 2~3 分钟）。
"""
import importlib
import json
import os
import sys
import time

SCRIPTS = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
sys.path.insert(0, SCRIPTS)

# 先排掉 __pycache__ 陈旧字节码
import shutil  # noqa: E402
pc = os.path.join(SCRIPTS, "__pycache__")
if os.path.isdir(pc):
    n = len(os.listdir(pc))
    shutil.rmtree(pc, ignore_errors=True)
    print("[准备] 清掉 __pycache__（%d 个文件），避免陈旧字节码" % n)

import collect_ziniao  # noqa: E402
import analyze  # noqa: E402

print("[准备] collect_ziniao 已加载自: %s" % collect_ziniao.__file__)
print("[准备] analyze 已加载自: %s" % analyze.__file__)
print("[准备] collect_ziniao 里有 clean_listing_title: %s"
      % hasattr(collect_ziniao, "clean_listing_title"))
print("[准备] fetch_item_detail 源码含 '等待后再试一次': %s"
      % ("等待后再试一次" in __import__("inspect").getsource(collect_ziniao.fetch_item_detail)))
print()

from ziniao_runtime import (  # noqa: E402
    close_browser, exit_ziniao, get_browser_list, kill_ziniao, match_store,
    open_store, start_ziniao, wait_for_server,
)

STORE, SITE, KW, MAXN, DETAIL = "haihu_8075", "uk", "wireless earbuds", 120, 10
api_port = None
try:
    kill_ziniao()
    api_port = start_ziniao()
    assert wait_for_server(api_port), "服务未就绪"
    stores = get_browser_list(api_port)
    zn = match_store(stores, STORE)
    info = {s.get("browserName"): s for s in stores}[zn]
    res = open_store(api_port, info.get("browserOauth", ""))
    dport = res.get("debuggingPort")
    print("命中店铺=%s debuggingPort=%s" % (zn, dport))
    time.sleep(10)

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    for attempt in range(1, 6):
        try:
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % dport)
            print("  CDP 接管成功（第 %d 次尝试）" % attempt)
            break
        except Exception as exc:
            print("  CDP 第 %d 次失败: %s" % (attempt, str(exc)[:80]))
            time.sleep(5)
    if browser is None:
        raise RuntimeError("CDP 接管失败")
    page = browser.contexts[0].pages[0]

    payload = collect_ziniao.collect_on_page(page, KW, SITE, MAXN, DETAIL)

    its = payload["items"]
    print("\n=== 交接点 A：collect_on_page 返回 ===")
    print("items 条数 = %d" % len(its))
    print("有 specifics 的位置 = %s" % [it["position"] for it in its if it.get("item_specifics")])
    print("title 带 a11y 尾巴的条数 = %d"
          % sum(1 for it in its if "opens in a new window" in (it["title"] or "").lower()))
    print("categories 非空的条数 = %d" % sum(1 for it in its if it.get("categories")))
    print("leaf_category_name 非空 = %d" % sum(1 for it in its if it.get("leaf_category_name")))
    for it in its[:10]:
        print("   #%-3d specs=%-3d title干净=%-5s cat=%d"
              % (it["position"], len(it.get("item_specifics") or []),
                 "opens in a new window" not in (it["title"] or "").lower(),
                 len(it.get("categories") or [])))

    print("\n=== 交接点 B：build_report 之后 ===")
    report = analyze.build_report(KW, SITE, its, 20, DETAIL, extra_refinements=[])
    rits = report["items"]
    print("report items 条数 = %d（应与 A 相同）" % len(rits))
    print("有 specifics 的位置 = %s" % [it["position"] for it in rits if it.get("item_specifics")])
    print("categories 非空 = %d" % sum(1 for it in rits if it.get("categories")))
    print("specifics 属性块数 = %d" % len(report["specifics"]))
    print("specifics_sample_positions = %s" % report.get("specifics_sample_positions"))

    print("\n=== 交接点 C：json.dumps 之后（模拟导出） ===")
    s = json.dumps(report, ensure_ascii=False)
    back = json.loads(s)
    print("反序列化后有 specifics 的位置 = %s"
          % [it["position"] for it in back["items"] if it.get("item_specifics")])
    print("反序列化后 categories 非空 = %d"
          % sum(1 for it in back["items"] if it.get("categories")))
    print("recommended_titles = %d 条" % len(back["recommended_titles"]))

    try:
        browser.close()
    except Exception:
        pass
    close_browser(api_port, info.get("browserOauth", ""), browser)
finally:
    if api_port:
        try:
            exit_ziniao(api_port)
        except Exception:
            pass
        kill_ziniao()
