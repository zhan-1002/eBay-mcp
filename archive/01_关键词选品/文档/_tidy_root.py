# -*- coding: utf-8 -*-
"""整理根目录 —— 把本轮调研抓取的资料移进 文档/调研资料/。

这些全是本次调查过程中我下载的原始资料（费率表、MCP 规范、EPN 协议、Terapeak PPT…），
堆在项目根目录很乱。移动后同步修正文档目录里诊断脚本的引用路径。
"""
import io
import os
import re
import shutil

ROOT = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay"
DST = os.path.join(ROOT, "01_关键词选品", "文档", "调研资料")
os.makedirs(DST, exist_ok=True)

# 我抓下来的调研资料（不动用户的任何文件）
MINE = [
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\apisguru_list.json", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\rate_limits.json", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\feedback_spec.ts", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mi_spec.ts",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_api.pdf", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_api.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\terapeak_mcp_readme.md",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\wb_article.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\wb_doc.md", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\wb_EPN_网络协议_准入条件相关_.txt",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\wb_Terapeak_官方介绍.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\gk_article.txt",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\eBay-sold-items-documentation.md", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\openclaw-ebay-research.md",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_MCP_Python_SDK.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_MCP_工具规范.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_MCP_提示词规范.txt",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_MCP_规范目录.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_MCP_规范首页.txt", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_MCP_资源规范.txt",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_工具_Tools.md", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_工具变更记录.md", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_提示词_Prompts.md",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_文档索引_llms_txt.md", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_生命周期_初始化.md", "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_资源_Resources.md",
    "C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档\调研资料\mcp_change.md",
]

moved, skipped = [], []
for name in MINE:
    src = os.path.join(ROOT, name)
    if os.path.isfile(src):
        shutil.move(src, os.path.join(DST, name))
        moved.append((name, os.path.getsize(os.path.join(DST, name))))
    else:
        skipped.append(name)

print("已移动到 文档/调研资料/ 的文件（%d 个，合计 %.1f MB）："
      % (len(moved), sum(s for _n, s in moved) / 1024 / 1024))
for n, s in sorted(moved, key=lambda x: -x[1]):
    print("   %-46s %8.1f KB" % (n, s / 1024))
if skipped:
    print("\n根目录里没有的（跳过）：%s" % "、".join(skipped))

# 修正诊断脚本里的路径引用
DOCDIR = os.path.join(ROOT, "01_关键词选品", "文档")
fixed = []
for fn in os.listdir(DOCDIR):
    if not fn.endswith(".py"):
        continue
    p = os.path.join(DOCDIR, fn)
    t = io.open(p, encoding="utf-8").read()
    orig = t
    for name in MINE:
        # 把 紫鸟ebay\xxx  →  紫鸟ebay\01_关键词选品\文档\调研资料\xxx
        t = t.replace("紫鸟ebay\\\\%s" % name,
                      "紫鸟ebay\\\\01_关键词选品\\\\文档\\\\调研资料\\\\%s" % name)
        t = t.replace("紫鸟ebay\\%s" % name,
                      "紫鸟ebay\\01_关键词选品\\文档\\调研资料\\%s" % name)
        t = t.replace('"%s"' % name, '"%s"' % os.path.join(DST, name))
    if t != orig:
        io.open(p, "w", encoding="utf-8").write(t)
        fixed.append(fn)
print("\n路径引用已修正的脚本（%d 个）：%s" % (len(fixed), "、".join(fixed) or "无"))

print("\n=== 清理后的根目录 ===")
for x in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, x)
    tag = "DIR " if os.path.isdir(p) else "    "
    size = "" if os.path.isdir(p) else "%8.1f KB" % (os.path.getsize(p) / 1024)
    print("  %s%-40s %s" % (tag, x, size))
