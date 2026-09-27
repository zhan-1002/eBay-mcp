# -*- coding: utf-8 -*-
"""诊断：直接拉起 ziniao.exe web_driver，观察进程存活/端口监听/输出。只读式诊断。

不修改项目任何文件；需要提权是因为控制台日志写在项目目录外。
"""
import os
import socket
import subprocess
import sys
import time

EXE = r"D:\ziniao\ziniao.exe"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 17321
LOG_DIR = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档"
OUT = os.path.join(LOG_DIR, "_ziniao_probe_out.log")
ERR = os.path.join(LOG_DIR, "_ziniao_probe_err.log")


def listening(port):
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def main():
    print("exe  =", EXE, "| exists:", os.path.isfile(EXE))
    print("port =", PORT)
    args = [EXE, "--run_type=web_driver", "--ipc_type=http", "--port=%d" % PORT]
    print("argv =", args)

    fo = open(OUT, "wb")
    fe = open(ERR, "wb")
    p = subprocess.Popen(args, stdout=fo, stderr=fe)
    print("pid  =", p.pid)

    rc = None
    for i in range(20):
        time.sleep(3)
        rc = p.poll()
        print("t=%2ds  存活=%s  端口在听=%s" % ((i + 1) * 3, rc is None, listening(PORT)))
        if rc is not None:
            print("进程已退出, returncode =", rc)
            break

    fo.flush()
    fe.flush()
    fo.close()
    fe.close()
    for f in (OUT, ERR):
        size = os.path.getsize(f) if os.path.isfile(f) else -1
        print("\n### %s  (%d bytes)" % (os.path.basename(f), size))
        if os.path.isfile(f):
            with open(f, "rb") as fh:
                data = fh.read()
            text = data.decode("utf-8", "replace").strip()
            print(text[:3000] if text else "(空)")

    if p.poll() is None:
        print("\n结论: 进程仍在运行 -> 主动终止")
        p.kill()
    else:
        print("\n结论: 进程自行退出，上面 returncode/log 是关键")


if __name__ == "__main__":
    main()
