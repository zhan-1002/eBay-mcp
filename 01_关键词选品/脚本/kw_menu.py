# -*- coding: utf-8 -*-
"""关键词选品 —— 交互式壳程序（在 bat 窗口里运行）。

## 为什么交互菜单放在 Python，而不是写在 .bat 里

`bat` 文件里的中文会被 cmd 按**当前代码页**解读：存成 GBK(936) 时，在代码页不是 936 的
机器上（例如某些终端把控制台设成 65001/UTF-8），bat 里的中文路径会直接解析成乱码，
`if exist` 找不到文件 —— 实测踩到过：控制台 65001 下，bat 报"找不到采集脚本"，
而文件明明就在那儿。

Python 3.6+ 在 Windows 控制台走 `WriteConsoleW`（PEP 528），
中文输入输出与代码页无关。所以：**bat 只做转发（内容纯 ASCII）**，
菜单 / 参数确认 / 详细日志全部在这里。

## 用法

    kw_menu.py                      交互式（填关键词 → 选站点 → 跑 → 问是否继续）
    kw_menu.py "wireless earbuds" uk                    带参数：跳过交互跑一次
    kw_menu.py "wireless earbuds,phone case" "uk us"    多关键词 × 多站点
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MODULE_ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(MODULE_ROOT, "输出")
LOG_DIR = os.path.join(MODULE_ROOT, "日志")

SITE_MENU = [
    ("1", "uk", "英国"),
    ("2", "us", "美国"),
    ("3", "de", "德国"),
    ("4", "au", "澳大利亚"),
    ("5", "fr", "法国"),
    ("6", "es", "西班牙"),
    ("7", "it", "意大利"),
    ("8", "ca", "加拿大"),
    ("9", "hk", "香港"),
]
LINE = "-" * 64


def _hr(ch="="):
    print(ch * 64)


def _ask_keywords(sites):
    """返回关键词列表；用户输入 Q 返回 None 表示退出。

    顺序上**站点先选、关键词后填**（用户要求）：先定站点，再让用户对着
    "当前站点"填关键词，心里有数。
    """
    while True:
        print()
        _hr()
        print("  当前站点：%s（%d 个）" % ("、".join(s.upper() for s in sites), len(sites)))
        print("  请输入要采集的关键词")
        print("    · 多个关键词用【逗号】分隔，例如：wireless earbuds,phone case")
        print("    · 多词关键词直接写，空格不会被拆开")
        print("      （wireless earbuds 是【一个】关键词，不是两个）")
        print("    · 输入 Q 退出")
        _hr()
        raw = _input("关键词: ")
        if raw is None:
            return None
        raw = raw.strip()
        if raw.upper() == "Q":
            return None
        if not raw:
            print("\n[提示] 关键词不能为空，请重新输入。\n")
            continue
        from run_keyword_research import _split_keywords
        kws = _split_keywords(raw)
        if not kws:
            print("\n[提示] 没解析出关键词，请重新输入。\n")
            continue
        if len(kws) > 1:
            print("\n识别到 %d 个关键词：%s" % (len(kws), "、".join(kws)))
        return kws


_EOF_HINTED = False


def _input(prompt):
    """统一封装的 input()：拿不到键盘输入时给一句能付诸行动的话，而不是静默退出。

    注意：`cmd /c bat` 配**重定向 stdin** 时子进程会立刻 EOF（Windows 行为，
    连两行最小 bat 都能复现）；但**双击时 stdin 是真实控制台，键盘输入正常**。
    所以这里只是把"非交互场景"讲清楚，不影响双击使用。

    Ctrl+C 也在这里兜住，避免用户在菜单上按了中断还看到一堆 traceback。
    """
    global _EOF_HINTED
    try:
        return input(prompt)
    except EOFError:
        if not _EOF_HINTED:
            _EOF_HINTED = True
            print()
            print("[提示] 这个窗口拿不到键盘输入（stdin 不是控制台）。")
            print("       直接双击 关键词选品采集.bat 是可以输入的；")
            print("       如果你是用重定向/管道跑的，请改成带参数方式：")
            print('         关键词选品采集.bat "wireless earbuds" uk')
        return None
    except KeyboardInterrupt:
        print()
        print("[中断] 已取消。")
        return None


def _ask_sites():
    """返回站点码列表；用户输入 Q 返回 None 表示退出。"""
    while True:
        print()
        _hr()
        print("  第 1 步 / 共 2 步：请选择本次采集使用到的站点")
        print("    · 可单选，也可多选（输入多个编号，用空格分隔，例如：1 3 5）")
        print()
        row = "   "
        for i, (num, code, cn) in enumerate(SITE_MENU):
            row += "%s) %-2s %-9s" % (num, code, cn)
            if i % 3 == 2:
                print(row)
                row = "   "
        if row.strip():
            print(row)
        print("    A) 全部 9 个站点          Q) 退出")
        _hr()
        raw = _input("站点编号: ")
        if raw is None:
            return None
        raw = raw.strip()
        if raw.upper() == "Q":
            return None
        if not raw:
            print("\n[提示] 请至少选择一个站点。\n")
            continue
        picked, bad = [], []
        for tok in raw.replace(",", " ").split():
            if tok.upper() == "A":
                picked = [c for _, c, _ in SITE_MENU]
                break
            hit = [c for n, c, _ in SITE_MENU if n == tok]
            if hit:
                if hit[0] not in picked:
                    picked.append(hit[0])
            else:
                bad.append(tok)
        if bad:
            print("\n[错误] 无法识别的编号：%s（只能是 1-9 或 A）\n" % " ".join(bad))
            continue
        if not picked:
            print("\n[提示] 请至少选择一个站点。\n")
            continue
        return picked


def _list_newest(limit=10):
    if not os.path.isdir(OUT_DIR):
        return []
    files = [f for f in os.listdir(OUT_DIR) if f.lower().endswith(".xlsx")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)), reverse=True)
    return files[:limit]


def _run(pairs_keywords, sites):
    """调主程序跑一遍。返回退出码。"""
    import run_keyword_research as R
    argv = ["--mode", "api",
            "--keyword", ",".join(pairs_keywords),
            "--sites", ",".join(sites),
            "--max", "200",
            "--out-dir", OUT_DIR,
            "--log-dir", LOG_DIR]
    try:
        return R.main(argv)
    except KeyboardInterrupt:
        print("\n[中断] 用户按了 Ctrl+C，已完成的产物不受影响。")
        return 130
    except Exception as exc:
        import traceback
        print("\n[异常] %s" % exc)
        print(traceback.format_exc())
        print("把这个窗口的内容截图，或把 日志\\ 里最新的 txt 发出来就能定位。")
        return 1


def _summary(rc):
    print()
    _hr("=")
    print("  运行结束 ｜ 退出码 %s ｜ %s" % (rc, "成功" if rc == 0 else "有失败，见上面日志"))
    print("  结束时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    _hr("=")
    newest = _list_newest()
    print("  最新产物（最多 10 个）：")
    if newest:
        for f in newest:
            size = os.path.getsize(os.path.join(OUT_DIR, f)) / 1024.0
            print("    %s  （%.0f KB）" % (f, size))
    else:
        print("    （产物目录里还没有 xlsx）")
    print()
    print("  产物目录：%s" % OUT_DIR)
    print("  完整日志：%s" % LOG_DIR)
    _hr("=")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    print()
    _hr("=")
    print("  eBay 关键词选品")
    print("  流程：① 选站点（可多选）→ ② 填关键词（可多个）→ ③ 确认后采集")
    print("  产物：<关键词>_<时间>_<站点>.xlsx —— 每份含 5 张子表")
    print("  （市场概况与价格 / 品牌壁垒 / 关键词与标题 / 基础统计 / 采集明细）")
    _hr("=")

    # 带参数：跳过交互，跑一次就退出（自动化 / 自测用）
    if argv:
        first = argv[0].strip().lower()
        # 凭据体检（共享盘上出问题时，先跑这个）
        if first in ("check", "--check", "-check", "自检"):
            import ebay_auth
            return ebay_auth.main(["--check"])
        keyword = argv[0]
        sites = argv[1].replace(",", " ").split() if len(argv) > 1 and argv[1] else ["uk"]
        from run_keyword_research import _split_keywords
        kws = _split_keywords(keyword)
        print("\n[带参数模式] 关键词 %s ｜ 站点 %s" % ("、".join(kws),
                                                  "、".join(s.upper() for s in sites)))
        rc = _run(kws, sites)
        _summary(rc)
        return rc

    # 交互模式：**先选站点，再填关键词**（用户要求）
    sites = _ask_sites()
    if sites is None:
        print("\n已退出。")
        return 0

    while True:
        kws = _ask_keywords(sites)
        if kws is None:
            print("\n已退出。")
            return 0

        print()
        _hr("=")
        print("  本次采集参数确认")
        _hr()
        print("  站点      : %s（%d 个）" % ("、".join(s.upper() for s in sites), len(sites)))
        print("  关键词    : %s（%d 个）" % ("、".join(kws), len(kws)))
        print("  组合数    : %d 个（%d 关键词 × %d 站点）" % (len(kws) * len(sites),
                                                          len(kws), len(sites)))
        print("  每个组合  : 200 条（eBay 单页上限，一次请求拿满，含详情与 item specifics）")
        print("  产物目录  : %s" % OUT_DIR)
        print("  预计耗时  : 每个组合约 20~30 秒（视网络与 LLM 而定）")
        print("  预计费用  : 每个组合约 ¥0.01（DeepSeek）")
        _hr("=")
        go = _input("确认开始？[Y/n]: ")
        if go is None:
            print("\n已退出。")
            return 0
        if go.strip().lower() not in ("", "y", "yes"):
            print("\n已取消，重新填写关键词。\n")
            continue

        rc = _run(kws, sites)
        _summary(rc)

        print()
        print("  下一步：")
        print("    Y = 继续采集其它关键词（站点不变：%s）" % "、".join(s.upper() for s in sites))
        print("    S = 换站点")
        print("    N = 退出")
        nxt = _input("请选择 [Y/S/N]: ")
        if nxt is None:
            print("\n已退出。")
            return rc
        nxt = nxt.strip().lower()
        if nxt == "s":
            new_sites = _ask_sites()
            if new_sites is None:
                print("\n已退出。")
                return rc
            sites = new_sites
        elif nxt not in ("", "y", "yes"):
            print("\n已退出。")
            return rc


if __name__ == "__main__":
    raise SystemExit(main())
