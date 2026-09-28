# -*- coding: utf-8 -*-
"""生成入口 bat（GBK 编码，cmd 里中文才正常显示）。

为什么要写脚本生成：bat 必须存成 **GBK/ANSI**（中文 Windows 的 cmd 用 936 代码页），
而本工程的源码都是 UTF-8。直接手写 UTF-8 的 bat，双击后中文全是乱码。

bat 支持两种用法：
  1) 双击 → 交互式：填关键词（支持多个，逗号分隔）→ 选站点（可多选）→ 跑
  2) 带参数 → 跳过交互（自动化/自测）：关键词选品采集.bat "关键词" 站点列表
"""
import io
import os

SHARE = r"\\192.168.120.11\Ebay部门\ebay看板"
BAT = os.path.join(SHARE, "关键词选品采集.bat")

CONTENT = r"""@echo off
setlocal enabledelayedexpansion
title eBay 关键词选品采集

rem ============================================================
rem  eBay 关键词选品 —— 壳程序
rem  产物： 关键词选品\输出\<关键词>_<时间>_<站点>.xlsx
rem  日志： 关键词选品\日志\关键词选品_<时间>.log
rem ============================================================

set "BASE=%~dp0"
set "BASE=%BASE:~0,-1%"
set "APP=%BASE%\关键词选品"
set "PY=%BASE%\runtime\python.exe"
set "SCRIPT=%APP%\脚本\run_keyword_research.py"
set "OUTDIR=%APP%\输出"
set "LOGDIR=%APP%\日志"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%APP%\脚本"

echo ============================================================
echo    eBay 关键词选品采集
echo ============================================================
echo.

if not exist "%PY%" (
    echo [错误] 找不到 Python 运行时：
    echo        %PY%
    echo        请确认 runtime 文件夹与本 bat 在同一目录下。
    echo.
    pause
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo [错误] 找不到采集脚本：
    echo        %SCRIPT%
    echo.
    pause
    exit /b 1
)
if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1

rem ---- 带参数直接跑（跳过交互），便于自动化与自测 ----
if not "%~1"=="" (
    set "KW=%~1"
    set "SITES=%~2"
    if "!SITES!"=="" set "SITES=uk"
    goto run
)

:askkw
echo ------------------------------------------------------------
echo  请输入要采集的关键词
echo    · 多个关键词用【逗号】分隔，例如：wireless earbuds,phone case
echo    · 多词关键词直接写，空格不会被拆开
echo      （wireless earbuds 是【一个】关键词，不是两个）
echo    · 输入 Q 退出
echo ------------------------------------------------------------
echo.
set "KW="
set /p "KW=关键词: "
if /i "%KW%"=="Q" goto quit
if "%KW%"=="" (
    echo.
    echo [提示] 关键词不能为空，请重新输入。
    echo.
    goto askkw
)

:asksite
echo.
echo ------------------------------------------------------------
echo  请选择站点（可单选，也可多选）
echo    · 多选请输入多个编号，用空格分隔，例如：1 3 5
echo.
echo    1^) uk 英国        2^) us 美国        3^) de 德国
echo    4^) au 澳大利亚    5^) fr 法国        6^) es 西班牙
echo    7^) it 意大利      8^) ca 加拿大      9^) hk 香港
echo    A^) 全部 9 个站点
echo ------------------------------------------------------------
echo.
set "SEL="
set /p "SEL=站点编号: "
if "%SEL%"=="" (
    echo.
    echo [提示] 请至少选择一个站点。
    echo.
    goto asksite
)
set "SITES="
for %%N in (%SEL%) do (
    if /i "%%N"=="A" set "SITES=uk us de au fr es it ca hk"
    if /i "%%N"=="1" set "SITES=!SITES! uk"
    if /i "%%N"=="2" set "SITES=!SITES! us"
    if /i "%%N"=="3" set "SITES=!SITES! de"
    if /i "%%N"=="4" set "SITES=!SITES! au"
    if /i "%%N"=="5" set "SITES=!SITES! fr"
    if /i "%%N"=="6" set "SITES=!SITES! es"
    if /i "%%N"=="7" set "SITES=!SITES! it"
    if /i "%%N"=="8" set "SITES=!SITES! ca"
    if /i "%%N"=="9" set "SITES=!SITES! hk"
)
if "%SITES%"=="" (
    echo.
    echo [错误] 无法识别的编号：%SEL%   （只能是 1-9 或 A）
    echo.
    goto asksite
)

:run
echo.
echo ==================== 本次采集参数 ====================
echo   关键词    : %KW%
echo   站点      : %SITES%
echo   采集条数  : 每个组合 120 条（含详情与 item specifics）
echo   产物目录  : %OUTDIR%
echo   日志目录  : %LOGDIR%
echo   开始时间  : %date% %time%
echo ====================================================
echo.
echo 正在采集，请勿关闭窗口。详细日志如下：
echo.

"%PY%" "%SCRIPT%" --mode api --keyword "%KW%" --sites "%SITES%" --max 120 --out-dir "%OUTDIR%" --log-dir "%LOGDIR%"
set "RC=%errorlevel%"

echo.
echo ==================== 运行结束 ====================
echo   退出码    : %RC%
echo   结束时间  : %date% %time%
if "%RC%"=="0" (
    echo   结果      : 成功
) else (
    echo   结果      : 有失败，请往上翻看红色报错，或打开日志目录里的最新 txt
)
echo.
echo   最新产物（按时间倒序，最多 10 个）：
set /a N=0
for /f "delims=" %%F in ('dir /b /o-d "%OUTDIR%\*.xlsx" 2^>nul') do (
    set /a N+=1
    if !N! leq 10 echo      %%F
)
if !N!==0 echo      （产物目录里还没有 xlsx）
echo.
echo   产物目录：%OUTDIR%
echo   完整日志：%LOGDIR%
echo.

rem 带参数模式跑完就退出，不留交互
if not "%~1"=="" exit /b %RC%

set "AGAIN="
set /p "AGAIN=是否继续采集其它关键词？[Y/N]: "
if /i "%AGAIN%"=="Y" (
    echo.
    goto askkw
)

:quit
echo 已退出。
timeout /t 3 >nul
exit /b 0
"""


def main():
    # 换行必须是 CRLF，否则某些 cmd 版本会出怪问题
    text = CONTENT.replace("\r\n", "\n").replace("\n", "\r\n")
    with io.open(BAT, "w", encoding="gbk", errors="replace", newline="") as f:
        f.write(text)
    print("已生成 %s（GBK 编码，%d 字节）" % (BAT, os.path.getsize(BAT)))
    # 回读验证编码
    with io.open(BAT, encoding="gbk") as f:
        head = f.read().split("\n")[:6]
    print("回读前几行：")
    for h in head:
        print("   " + h.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
