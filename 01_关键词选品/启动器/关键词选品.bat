@echo off
setlocal
set "HERE=%~dp0"
set "SCRIPTS=%HERE%..\脚本"
set "ROOT=%HERE%..\.."
set "PY="

if exist "%ROOT%\..\ebay看板\runtime\python.exe" set "PY=%ROOT%\..\ebay看板\runtime\python.exe"
if not defined PY if exist "D:\PythonProject\ebay\runtime\python.exe" set "PY=D:\PythonProject\ebay\runtime\python.exe"
if not defined PY set "PY=python"

set "PYTHONPATH=%SCRIPTS%"
set "PYTHONIOENCODING=utf-8"

rem 交互式壳程序（填关键词 → 选站点 → 跑 → 打印详细日志）
rem   kw_menu.py 里带中文菜单，所以 bat 本身不含中文路径/文本：
rem   bat 里的中文受 cmd 代码页支配，换台机器就可能解析错乱。
rem   本机开发时用 python -m 直接看中文输出没问题（PEP 528）。
if "%~1"=="" (
    "%PY%" "%SCRIPTS%\kw_menu.py"
) else (
    "%PY%" "%SCRIPTS%\kw_menu.py" %*
)
exit /b %ERRORLEVEL%
