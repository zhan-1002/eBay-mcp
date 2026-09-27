# -*- coding: utf-8 -*-
"""清理上次测试残留的 kw_menu 进程，并列出当前 python.exe 情况。"""
import subprocess

QUERY = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }")


def cim():
    p = subprocess.run(["powershell", "-NoProfile", "-Command", QUERY],
                       capture_output=True, timeout=120)
    return (p.stdout or b"").decode("utf-8", "replace").splitlines()


def tasklist():
    p = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"],
                       capture_output=True, timeout=60)
    return [l for l in (p.stdout or b"").decode("utf-8", "replace").splitlines()
            if "python" in l.lower()]


rows = cim()
print("当前 python.exe 进程（CIM 视角，共 %d）:" % len([r for r in rows if r.strip()]))
for r in rows:
    if r.strip():
        print("   %s" % r.strip()[:140])

targets = [r for r in rows if "kw_menu.py" in r]
print("\n其中 kw_menu 进程: %d" % len(targets))
for r in targets:
    pid = r.split("|")[0].strip()
    subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    print("   已结束 PID %s" % pid)

print("\ntasklist 里 python 行数: %d" % len(tasklist()))
