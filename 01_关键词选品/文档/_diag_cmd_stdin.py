# -*- coding: utf-8 -*-
"""最小复现：cmd /c 跑 bat 时 stdin 会被谁吃掉？

bat 内容全部 ASCII（中文路径用映射盘符绕开，否则 bat 本身编码又会干扰结论）。
用本机 py310（ASCII 路径）做隔离，只测"cmd + bat 结构"对 stdin 的影响。
"""
import io
import os
import subprocess
import tempfile

TMP = tempfile.mkdtemp()
IN = os.path.join(TMP, "in.txt")
with io.open(IN, "w", encoding="utf-8", newline="\r\n") as f:
    f.write("LINE-1\nLINE-2\nLINE-3\n")

PY = r"D:\anaconda3\envs\py310\python.exe"
CODE = "import sys;print('GOT:',repr(sys.stdin.readline()))"
STD = 'set "PYTHONIOENCODING=utf-8"'


def make(name, body):
    p = os.path.join(TMP, name)
    with io.open(p, "w", encoding="ascii", newline="") as f:
        f.write(body.replace("\n", "\r\n"))
    return p


cases = [
    ("1) 直接 python", None, [PY, "-c", CODE]),
    ("2) cmd /c 最小 bat", make("a.bat",
        '@echo off\n%s\n"%s" -c "%s"\n' % (STD, PY, CODE)), None),
    ("3) cmd /c + setlocal", make("b.bat",
        '@echo off\nsetlocal\n%s\n"%s" -c "%s"\n' % (STD, PY, CODE)), None),
    ("4) cmd /c + pushd 本地", make("c.bat",
        '@echo off\nsetlocal\npushd "%%TEMP%%" 2>nul\n%s\n"%s" -c "%s"\npopd 2>nul\n'
        % (STD, PY, CODE)), None),
    ("5) cmd /c + pushd 后带 pause", make("d.bat",
        '@echo off\nsetlocal\npushd "%%TEMP%%" 2>nul\n%s\n"%s" -c "%s"\npopd 2>nul\n'
        'echo [Done]\npause\n' % (STD, PY, CODE)), None),
    ("6) cmd /c bat + 参数为空判断", make("e.bat",
        '@echo off\nsetlocal\n%s\n"%s" -c "%s"\n'
        'if "%%~1"=="" (\n  echo.\n  echo [Done]\n  pause\n)\n' % (STD, PY, CODE)), None),
]

for label, bat, cmd in cases:
    argv = cmd or ["cmd", "/c", bat]
    with io.open(IN, "r", encoding="utf-8") as fin:
        p = subprocess.run(argv, stdin=fin, capture_output=True, text=True, timeout=120)
    got = [x for x in (p.stdout or "").splitlines() if "GOT:" in x]
    print("%-28s rc=%s  %s" % (label, p.returncode, got[0] if got else "❌ 没读到 stdin"))
