# -*- coding: utf-8 -*-
"""从已抓到的 EPN 协议里挖出：Buy API Program 定义 + 参与条件（Exhibit A）。"""
import glob
import io
import re

files = glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\wb_EPN*.txt") \
    or glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\wb_EPN*.txt") \
    or glob.glob(r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\**\wb_EPN*.txt", recursive=True)
print("匹配到的文件: %s" % files)
if not files:
    raise SystemExit("没找到 EPN 协议正文文件")

t = io.open(files[0], encoding="utf-8").read()
t = re.sub(r"\s+", " ", t)
print("正文长度 %d\n" % len(t))


def show(kw, before=120, after=900, maxn=2):
    print("=" * 96)
    print("【%s】" % kw)
    print("=" * 96)
    n = 0
    for m in re.finditer(re.escape(kw), t, re.I):
        s = max(0, m.start() - before)
        print("…%s…\n" % t[s:m.start() + after])
        n += 1
        if n >= maxn:
            return
    if n == 0:
        print("（没找到）\n")


show("Buy API Program", 60, 700)
show("EXHIBIT A", 40, 1500, 1)
show("Participation Requirements", 60, 1800, 1)
show("Marketplace Insights", 200, 500, 2)
show("must have a website", 200, 500, 1)
show("application", 100, 500, 1)
