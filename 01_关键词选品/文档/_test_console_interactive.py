# -*- coding: utf-8 -*-
"""验证"真实控制台"（等同双击）下交互模式是否正常等待键盘输入。

为什么要这么绕：
  `cmd /c bat` 配**重定向 stdin** 时子进程会立刻 EOF —— Windows 行为，
  两行的最小 bat 也能复现，与程序无关。所以用重定向喂输入**测不出**双击的真实情况。

做法：用 `cmd /c start "" cmd /c <bat>` 开一个**全新控制台窗口**（stdin 指向该控制台，
不继承本进程的句柄），等 6 秒后看 python.exe 是否还活着：
  还活着 = 正阻塞在 input() 等键盘 → 双击可用
  已退出 = stdin 又 EOF 了          → 有问题

输出解码一律用 errors='replace'（进程命令行里有中文路径，text=True 会按 GBK 解码炸掉）。
"""
import re
import subprocess
import time

BAT = r"\\192.168.120.11\Ebay部门\ebay看板\关键词选品采集.bat"


def run_bytes(cmd):
    p = subprocess.run(cmd, capture_output=True, timeout=120)
    return (p.stdout or b"").decode("utf-8", "replace")


def menu_lines():
    out = run_bytes(["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                     "ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.CommandLine }"])
    return [ln for ln in out.splitlines() if "kw_menu.py" in ln]


def python_total():
    out = run_bytes(["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"])
    return len([ln for ln in out.splitlines() if "python.exe" in ln.lower()])


before_menu, before_all = menu_lines(), python_total()
print("启动前：kw_menu 进程 %d 个 ｜ python.exe 共 %d 个" % (len(before_menu), before_all))

print("\n用 start 打开全新控制台窗口运行 bat（等同双击）…")
subprocess.run(["cmd", "/c", "start", "", "cmd", "/c", BAT], capture_output=True, timeout=60)

for wait in (3, 6, 9):
    time.sleep(3)
    lines = menu_lines()
    print("  %d 秒后：kw_menu 进程 %d 个" % (wait, len(lines)))
    if lines:
        for ln in lines:
            print("     PID+cmdline: %s" % ln.strip()[:120])
        break

alive = menu_lines()
if alive:
    print("\n✅ 结论：真实控制台下进程**阻塞在等待键盘输入** —— 交互模式（先选站点再填关键词）可用")
else:
    print("\n❌ 结论：6~9 秒内进程已退出，说明没在等键盘 —— 交互模式有问题")

# 收尾：把测试开的窗口和进程关掉，别留在桌面上
killed = 0
for ln in alive:
    m = re.match(r"\s*(\d+)\s", ln)
    if m:
        subprocess.run(["taskkill", "/PID", m.group(1), "/T", "/F"], capture_output=True)
        killed += 1
print("已清理测试进程 %d 个（新开的控制台窗口随之关闭）" % killed)
