# -*- coding: utf-8 -*-
"""把关键词选品部署到部门共享目录（ASCII 目录名 + ASCII 内容的 bat）。

## 为什么目录名用 ASCII、bat 内容也纯 ASCII

踩过的坑：第一版把代码放在 `关键词选品\\脚本\\`、bat 里写中文路径。
在**控制台代码页不是 936** 的机器上（实测 65001/UTF-8），
bat 里的中文路径被按错误代码页解析，`if exist` 判不存在，
双击直接报"找不到采集脚本" —— 文件明明在那儿。

bat 的中文完全受 cmd 代码页支配，没法保证每台机器都一样；
而 Python 在 Windows 控制台走 WriteConsoleW（PEP 528），中文与代码页无关。
所以：**bat 只做转发（路径与文本全 ASCII）**，中文菜单与日志交给
`scripts\\kw_menu.py`。

目录（共享目录里只新增这两项，不动任何既有文件）：

  \\\\192.168.120.11\\Ebay部门\\ebay看板\\
      关键词选品采集.bat          ← 入口（文件名可以中文，内容纯 ASCII）
      keyword_research\\
          scripts\\  *.py + config.json
          输出\\     产物：<关键词>_<时间>_<站点>.xlsx
          日志\\     每次运行一个 txt
          README_使用说明.txt
"""
import io
import json
import os
import shutil

SHARE = r"\\192.168.120.11\Ebay部门\ebay看板"
LOCAL_SRC = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\脚本"
LOCAL_CFG = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\config.local.json"

APP_NAME = "keyword_research"          # ASCII，bat 依赖它
APP = os.path.join(SHARE, APP_NAME)
SCRIPTS_DST = os.path.join(APP, "scripts")
OUT_DST = os.path.join(APP, "输出")
LOG_DST = os.path.join(APP, "日志")
BAT = os.path.join(SHARE, "关键词选品采集.bat")

SCRIPT_FILES = [
    "kw_menu.py",                # 交互壳程序（菜单/日志）
    "run_keyword_research.py",   # 入口：多关键词 × 多站点
    "collect_ebay_api.py",       # eBay 官方 Browse API 采集
    "ebay_auth.py",              # 凭据缓存 + 自动续期
    "analyze.py",                # 基础统计
    "report_market.py",          # 市场分析段（价格/品牌/关键词/广告位）
    "llm_titles.py",             # DeepSeek 生成标题
    "sites.py",                  # 站点定义
    "common_path.py",            # 路径
    "config_load.py",
    "collect_api.py",
    "check_ebay_api.py",
]

# bat 内容：纯 ASCII，只负责转发到 kw_menu.py
BAT_CONTENT = r"""@echo off
rem ===========================================================
rem  eBay Keyword Research launcher (ASCII only on purpose)
rem  Chinese text lives in scripts\kw_menu.py: cmd reads .bat
rem  bytes using the console code page, so Chinese paths here
rem  break on machines whose code page is not 936.
rem ===========================================================
setlocal
set "BASE=%~dp0"
set "BASE=%BASE:~0,-1%"
set "APP=%BASE%\keyword_research"
set "PY=%BASE%\runtime\python.exe"
set "MENU=%APP%\scripts\kw_menu.py"

rem Running from a UNC path: cmd cannot use it as CWD and falls back to
rem C:\Windows (with a scary warning). pushd maps a temporary drive letter
rem instead, so everything below runs on the share cleanly.
pushd "%BASE%" 2>nul

if not exist "%PY%" (
    echo [ERROR] Python runtime not found:
    echo         %PY%
    echo         Keep this .bat next to the "runtime" folder.
    echo.
    popd 2>nul
    pause
    exit /b 1
)
if not exist "%MENU%" (
    echo [ERROR] Menu script not found:
    echo         %MENU%
    echo.
    popd 2>nul
    pause
    exit /b 1
)

set "PYTHONPATH=%APP%\scripts"
set "PYTHONIOENCODING=utf-8"

"%PY%" "%MENU%" %*
set "RC=%errorlevel%"

popd 2>nul

if "%~1"=="" (
    echo.
    echo [Done] exit code = %RC%
    pause
)
exit /b %RC%
"""


def main():
    for d in (APP, SCRIPTS_DST, OUT_DST, LOG_DST):
        os.makedirs(d, exist_ok=True)
        print("目录 OK  %s" % d)

    copied = []
    for name in SCRIPT_FILES:
        src = os.path.join(LOCAL_SRC, name)
        if not os.path.isfile(src):
            print("  [跳过] 本地没有 %s" % name)
            continue
        shutil.copy2(src, os.path.join(SCRIPTS_DST, name))
        copied.append(name)
    print("已复制 %d 个脚本 → %s" % (len(copied), SCRIPTS_DST))

    with io.open(LOCAL_CFG, encoding="utf-8") as f:
        local = json.load(f)
    cfg = {
        "ebay_api": {
            "env": "production",
            "client_id": (local.get("ebay_api") or {}).get("client_id", ""),
            "client_secret": (local.get("ebay_api") or {}).get("client_secret", ""),
            # 令牌缓存放程序目录内，别散落到共享目录根
            "token_cache": os.path.join(SCRIPTS_DST, "token.local.json"),
            "token_file": os.path.join(SCRIPTS_DST, "token.local.txt"),
        },
        "deepseek": {
            "api_key": (local.get("deepseek") or {}).get("api_key", ""),
            "base_url": (local.get("deepseek") or {}).get(
                "base_url", "https://api.deepseek.com/chat/completions"),
            "model": (local.get("deepseek") or {}).get("model", "deepseek-chat"),
            "price": {"cache_hit": 0.02, "cache_miss": 1.0, "output": 3.0},
        },
    }
    cfg_path = os.path.join(SCRIPTS_DST, "config.json")
    with io.open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("已写凭据 → %s" % cfg_path)

    # 清掉测试/旧版留下的东西
    for stale in ("token.local.json", "token.local.expired.txt"):
        p = os.path.join(SCRIPTS_DST, stale)
        if os.path.isfile(p):
            os.remove(p)
            print("清掉 %s" % stale)
    old_app = os.path.join(SHARE, "关键词选品")
    if os.path.isdir(old_app):
        shutil.rmtree(old_app)
        print("已删除上一版的目录（ASCII 目录名替代）：%s" % old_app)

    with io.open(BAT, "w", encoding="ascii", newline="") as f:
        f.write(BAT_CONTENT.replace("\n", "\r\n"))
    print("已写入口 bat → %s（ASCII）" % BAT)

    readme = os.path.join(APP, "README_使用说明.txt")
    with io.open(readme, "w", encoding="utf-8") as f:
        f.write(
            "eBay 关键词选品 —— 使用说明\n"
            "=" * 62 + "\n\n"
            "怎么跑：双击上一层目录的「关键词选品采集.bat」，按提示操作。\n\n"
            "操作顺序（两步）：\n"
            "  第 1 步  选择本次采集使用到的站点：可单选，也可多选\n"
            "           （输入多个编号用空格分隔，例如 1 3 5；A = 全部 9 个站点）\n"
            "  第 2 步  填写要采集的关键词：多个用【逗号】分隔\n"
            "           （例如 wireless earbuds,phone case）\n"
            "           多词关键词直接写，空格不会被拆开 —— wireless earbuds 是一个关键词\n"
            "  然后确认参数即开始采集；跑完会问：\n"
            "     Y = 继续填其它关键词（站点不变）   S = 换站点   N = 退出\n\n"
            "目录：\n"
            "  scripts\\        程序代码（别改）\n"
            "  scripts\\config.json  凭据与参数（含 eBay Cert ID、DeepSeek 密钥，勿外发）\n"
            "  输出\\           产物：<关键词>_<时间>_<站点>.xlsx（同名 .json 是原始数据）\n"
            "  日志\\           每次运行的完整日志 txt\n\n"
            "产物怎么看（每份 xlsx 有 5 张子表）：\n"
            "  1. 市场概况与价格  价格区间与占比 / 各价格带广告位占比 / 广告位位置分布 / 价格分位\n"
            "  2. 品牌壁垒        真品牌占位率（官方 brand 字段）/ 各品牌份额 / 白牌切入口\n"
            "  3. 关键词与标题    高频关键词评分 / 修饰词分类 / 结构模板 / 30 条推荐标题 / 策略建议\n"
            "  4. 基础统计        标题重复、词频、属性词频、类目\n"
            "  5. 采集明细        每个商品明细（是否广告位、标记来源、item specifics）\n\n"
            "多关键词 / 多站点：\n"
            "  关键词多个用【逗号】分隔（wireless earbuds,phone case）；\n"
            "  多词关键词直接写，空格不会被拆（wireless earbuds 是一个关键词）。\n"
            "  站点可单选也可多选；2 关键词 × 3 站点 = 6 份产物，各自独立成文件。\n\n"
            "费用：\n"
            "  eBay API 免费；DeepSeek 每份产物约 ¥0.005（半分钱），100 个关键词约 ¥0.5。\n\n"
            "出问题先看：\n"
            "  1. 日志\\ 里最新的 txt（报错原因都在里面）\n"
            "  2. 凭据体检：在本目录开 cmd，跑\n"
            "       ..\\runtime\\python.exe keyword_research\\scripts\\kw_menu.py check\n"
            "     或直接把启动命令当参数传：\n"
            "       关键词选品采集.bat check\n"
        )
    print("已写说明 → %s" % readme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
