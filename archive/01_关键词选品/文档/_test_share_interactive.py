# -*- coding: utf-8 -*-
"""从共享盘跑交互式流程的受控测试（模拟双击后的输入）。

用 Python 写输入文件（**不带 BOM**）—— 上一次用 PowerShell 管道喂输入，
PowerShell 往第一行前面塞了个 U+FEFF，于是"空关键词"变成"1 个隐形关键词"，
把关键词喂给了站点选择，看起来像程序 bug。这次用文件重定向，输入完全可控。

输入序列：
    1) 空行            → 应触发"关键词不能为空，请重新输入"
    2) wireless earbuds → 关键词
    3) 1               → 站点 uk
    4) y               → 确认开始
    5) n               → 跑完不再继续
"""
import io
import os
import subprocess
import sys

BAT = r"\\192.168.120.11\Ebay部门\ebay看板\关键词选品采集.bat"
IN = os.path.join(os.environ["TEMP"], "kw_in.txt")
OUT = os.path.join(os.environ["TEMP"], "kw_interactive.txt")

with io.open(IN, "w", encoding="utf-8", newline="\r\n") as f:
    f.write("\n")                      # 1) 空行
    f.write("wireless earbuds\n")      # 2) 关键词
    f.write("1\n")                     # 3) 站点
    f.write("y\n")                     # 4) 确认
    f.write("n\n")                     # 5) 不再继续

print("输入文件 %s（%d 字节）" % (IN, os.path.getsize(IN)))
with io.open(IN, "rb") as f:
    print("前 16 字节: %r" % f.read(16))

# 从中性目录启动，证明不依赖本机工程目录
os.chdir(os.environ.get("TEMP", "C:\\"))
with io.open(OUT, "w", encoding="utf-8") as out, io.open(IN, "r", encoding="utf-8") as fin:
    rc = subprocess.call(["cmd", "/c", BAT], stdin=fin, stdout=out, stderr=subprocess.STDOUT)
print("退出码 = %s" % rc)
print("输出文件 %s" % OUT)
