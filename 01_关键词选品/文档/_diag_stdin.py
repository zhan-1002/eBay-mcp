# -*- coding: utf-8 -*-
"""定位 stdin 重定向为什么 EOF（三种传法对比）。"""
import io
import os
import subprocess
import sys

IN = os.path.join(os.environ["TEMP"], "kw_in2.txt")
with io.open(IN, "w", encoding="utf-8", newline="\r\n") as f:
    f.write("first line\nsecond line\n")

PY = r"\\192.168.120.11\Ebay部门\ebay看板\runtime\python.exe"
CODE = "import sys;print('GOT:',repr(sys.stdin.readline()));print('GOT2:',repr(sys.stdin.readline()))"

print("输入文件字节:", open(IN, "rb").read())


def run(label, **kw):
    print("\n--- %s ---" % label)
    try:
        p = subprocess.run([PY, "-c", CODE], capture_output=True, text=True, timeout=60, **kw)
        print("rc=%s" % p.returncode)
        print(p.stdout.strip() or "(空)")
        if p.stderr.strip():
            print("stderr:", p.stderr.strip()[:300])
    except Exception as exc:
        print("异常: %s" % exc)


# a) 文本模式文件对象（上一次用的方式）
run("a) stdin=文本模式文件对象", stdin=io.open(IN, "r", encoding="utf-8"))
# b) 二进制文件对象
run("b) stdin=二进制文件对象", stdin=open(IN, "rb"))
# c) 由 shell 自己做重定向
run("c) shell 重定向", shell=True) if False else None
p = subprocess.run('"%s" -c "%s" < "%s"' % (PY, CODE, IN), shell=True,
                   capture_output=True, text=True, timeout=60)
print("\n--- c) shell 重定向 ---\nrc=%s" % p.returncode)
print(p.stdout.strip() or "(空)")
if p.stderr.strip():
    print("stderr:", p.stderr.strip()[:300])
