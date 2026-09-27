# -*- coding: utf-8 -*-
"""第一步探针：只做「检测店铺 -> 打开店铺 -> 打印 CDP 调试端口」。

不抓数据、不点配送地、不进详情页；不修改任何现有脚本。
选择器/流程问题因此不会被这一步掩盖 —— 用来确认紫鸟链路本身是通的。

用法:
  python probe_store.py --store haihu_8075
  python probe_store.py --list
  python probe_store.py --store haihu_8075 --keep   （保留紫鸟窗口，便于看现场/跑后续调试）
"""

import argparse
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "脚本"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

try:
    from ziniao_runtime import (
        EXE_PATH, exit_ziniao, get_browser_list, kill_ziniao, match_store,
        open_store, start_ziniao, wait_for_server, z_post,
    )
    from config_load import ziniao_creds
    from common_path import project_root, output_dir
except Exception as exc:  # 依赖/路径问题要说得清楚，而不是裸 traceback
    print("[错误] 加载项目模块失败: %s" % exc)
    print("       脚本目录: %s" % SCRIPTS)
    raise SystemExit(2)


def show_config():
    cfg = os.path.join(project_root(), "config.local.json")
    print("  config.local.json : %s" % cfg)
    print("  文件存在          : %s" % os.path.isfile(cfg))
    try:
        creds = ziniao_creds()
    except Exception as exc:
        print("  凭证读取          : 失败 -> %s" % exc)
        return False
    print("  凭证读取          : OK  company=%s  username=%s  password=%s"
          % (creds["company"], creds["username"], "***"))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="haihu_8075")
    ap.add_argument("--list", action="store_true", help="只列店铺，不开店")
    ap.add_argument("--keep", action="store_true", help="结束时保留紫鸟窗口")
    args = ap.parse_args(argv)

    print("=" * 70)
    print("紫鸟第一步探针")
    print("=" * 70)
    print("[0] 环境")
    print("  解释器            : %s" % sys.executable)
    print("  python            : %s" % sys.version.split()[0])
    print("  EXE_PATH          : %s (存在=%s)" % (EXE_PATH, os.path.isfile(EXE_PATH)))

    if not show_config():
        print("\n结论: 缺少紫鸟凭证，无法登录紫鸟 —— 停在这一步。")
        print("      请复制 config.example.json 为 config.local.json 填 ziniao，")
        print("      或设置环境变量 ZINIAO_COMPANY / ZINIAO_USERNAME / ZINIAO_PASSWORD。")
        return 2

    api_port = None
    ok = False
    try:
        print("\n[1] 关闭现有紫鸟进程")
        kill_ziniao()

        print("[2] 启动紫鸟 webdriver 模式")
        api_port = start_ziniao()
        print("  api_port          : %d" % api_port)

        print("[3] 等待紫鸟服务就绪")
        if not wait_for_server(api_port):
            print("  等待失败: 服务未就绪（80s 超时）")
            return 3
        print("  服务就绪")

        print("[4] 拉店铺列表")
        stores = get_browser_list(api_port)
        names = [s.get("browserName") for s in stores]
        print("  店铺数            : %d" % len(stores))
        for s in stores:
            print("    - %s  (platform=%s, oauth=%s)"
                  % (s.get("browserName"), s.get("platform_name", "?"),
                     (s.get("browserOauth") or "")[:8] + "..."))

        if args.list:
            print("\n结论: --list 模式，店铺列表已取得。")
            ok = True
            return 0

        print("\n[5] 匹配店铺: %s" % args.store)
        zn_name = match_store(stores, args.store)
        if not zn_name:
            print("  未命中。现有店铺: %s" % ", ".join(sorted(n for n in names if n)))
            return 4
        store_info = {s.get("browserName"): s for s in stores}[zn_name]
        print("  命中              : %s" % zn_name)

        print("\n[6] 打开店铺")
        t0 = time.time()
        result = open_store(api_port, store_info.get("browserOauth", ""))
        debugging_port = result.get("debuggingPort")
        print("  耗时              : %.1fs" % (time.time() - t0))
        print("  statusCode        : %s" % result.get("statusCode"))
        print("  debuggingPort     : %s" % debugging_port)
        if not debugging_port:
            print("  未拿到 debuggingPort，打开失败")
            return 5

        print("\n[7] 探测 CDP 端点")
        try:
            import requests
            for _ in range(20):
                try:
                    r = requests.get("http://127.0.0.1:%s/json/version" % debugging_port, timeout=5)
                    if r.status_code == 200:
                        print("  /json/version     : %s" % r.json().get("Browser"))
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                print("  /json/version     : 20s 内没探到（不一定致命，playwright 可能仍能接管）")
        except Exception as exc:
            print("  CDP 探测异常      : %s" % exc)

        print("\n" + "=" * 70)
        print("结论: 检测到店铺并成功打开 -> %s (debuggingPort=%s)" % (zn_name, debugging_port))
        print("=" * 70)
        if args.keep:
            print("\n--keep: 紫鸟窗口保留，按回车后再清理...")
            try:
                input()
            except Exception:
                time.sleep(30)
        ok = True
        return 0

    except KeyboardInterrupt:
        print("\n用户中断")
        return 130
    except Exception as exc:
        print("\n异常: %s" % exc)
        print(traceback.format_exc())
        return 1
    finally:
        if api_port:
            print("\n[8] 清理：停止店铺 / 退出紫鸟 / 关进程")
            if ok and not args.keep:
                try:
                    exit_ziniao(api_port)
                except Exception:
                    pass
                print("  已清理（若想保留现场，用 --keep 重跑）")
            elif args.keep:
                print("  --keep 生效，不清理紫鸟窗口")
            else:
                print("  未成功，保留日志；如需现场请用 --keep 重跑")


if __name__ == "__main__":
    sys.exit(main())
