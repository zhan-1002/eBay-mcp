# -*- coding: utf-8 -*-
"""收尾：找出测试开的 cmd 窗口（命令行里带本 bat 的），只杀这几个。"""
import subprocess

QUERY = ("Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | "
         "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }")

p = subprocess.run(["powershell", "-NoProfile", "-Command", QUERY],
                   capture_output=True, timeout=120)
rows = [l for l in (p.stdout or b"").decode("utf-8", "replace").splitlines() if l.strip()]

mine = [r for r in rows if "关键词选品采集.bat" in r or "kw_menu.py" in r
        or "keyword_research" in r]
print("cmd.exe 进程共 %d 个；其中属于本次测试的 %d 个：" % (len(rows), len(mine)))
for r in mine:
    print("   %s" % r.strip()[:150])
for r in mine:
    pid = r.split("|")[0].strip()
    subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    print("   已结束 %s" % pid)
if not mine:
    print("   （无残留，测试窗口已随之关闭）")
