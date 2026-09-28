# -*- coding: utf-8 -*-
"""紫鸟启停、开店、店铺名匹配。账号从 config.local.json 读。"""

import os
import random
import time
import uuid
import winreg
import subprocess

import psutil
import requests

from config_load import ziniao_creds


def find_ziniao_exe():
    uninstall_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, reg_path in uninstall_paths:
        try:
            key = winreg.OpenKey(hive, reg_path)
        except FileNotFoundError:
            continue
        idx = 0
        while True:
            try:
                sub = winreg.EnumKey(key, idx)
                idx += 1
            except OSError:
                break
            try:
                sk = winreg.OpenKey(key, sub)
                try:
                    icon, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                except FileNotFoundError:
                    continue
                if "ziniao.exe" in icon.lower():
                    exe = icon.split(",")[0].strip().strip('"')
                    if os.path.isfile(exe):
                        return exe
            except Exception:
                pass
    return r"D:\ziniao\ziniao.exe"


EXE_PATH = find_ziniao_exe()


def get_random_port():
    port = random.randint(15000, 20000)
    try:
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                return get_random_port()
    except Exception:
        pass
    return port


def kill_ziniao(wait=8):
    """杀掉紫鸟相关进程，并**确认**杀干净。

    实测教训：只 kill 一次 + sleep(3) 不够 —— 残留进程会占住紫鸟的单实例锁，
    导致紧接着 start_ziniao 起不来（"紫鸟服务启动超时"）。
    """
    names = ("ziniao.exe", "superbrowser.exe")
    deadline = time.time() + wait
    while True:
        procs = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if (proc.info.get("name") or "").lower() in names:
                    procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not procs:
            return True
        for proc in procs:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        try:
            psutil.wait_procs(procs, timeout=3)
        except Exception:
            pass
        if time.time() >= deadline:
            left = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if (proc.info.get("name") or "").lower() in names:
                        left.append(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if left:
                print("  [警告] 仍有紫鸟进程未退出: %s（可能占住单实例锁，导致启动失败）" % left)
            return not left
        time.sleep(1)


def start_ziniao():
    port = get_random_port()
    subprocess.Popen([EXE_PATH, "--run_type=web_driver", "--ipc_type=http", "--port=%d" % port])
    time.sleep(5)
    return port


def z_post(port, data, timeout=120):
    url = "http://127.0.0.1:%d" % port
    r = requests.post(url, json=data, timeout=timeout)
    r.encoding = "utf-8"
    return r.json()


def wait_for_server(port, max_wait=80):
    for _ in range(0, max_wait, 2):
        try:
            data = {"action": "getBrowserList", "requestId": str(uuid.uuid4()), **ziniao_creds()}
            r = requests.post("http://127.0.0.1:%d" % port, json=data, timeout=10)
            if r.status_code == 200 and str(r.json().get("statusCode")) == "0":
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def wait_for_cdp(port, timeout=60):
    """等 CDP 调试端口真正可连。

    open_store 返回 debuggingPort 之后，浏览器窗口不一定是马上可连的：
    实测连续开关店铺时，立刻 connect_over_cdp 会 ECONNREFUSED（5 次重试全失败），
    必须轮询等端口起来再连。
    """
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket()
        s.settimeout(1)
        try:
            if s.connect_ex(("127.0.0.1", int(port))) == 0:
                return True
        finally:
            s.close()
        time.sleep(1)
    return False


def connect_cdp(pw, debugging_port, timeout=90):
    """带就绪等待的 CDP 接管，返回 browser。"""
    if not debugging_port:
        raise RuntimeError("没有 debuggingPort，无法接管")
    if not wait_for_cdp(debugging_port, timeout=max(30, timeout // 3)):
        print("  CDP 端口 %s 在等待期内没起来" % debugging_port)
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % int(debugging_port))
        except Exception as exc:
            last = exc
            time.sleep(3)
    raise RuntimeError("CDP 接管失败（%ss 内）: %s" % (timeout, str(last)[:200]))


def get_browser_list(port):
    return z_post(
        port,
        {"action": "getBrowserList", "requestId": str(uuid.uuid4()), **ziniao_creds()},
        30,
    ).get("browserList", [])


def match_store(all_stores, store):
    ziniao_names = {s.get("browserName") for s in all_stores}
    target_hyphen = store.replace("_", "-")
    if store in ziniao_names:
        return store
    if target_hyphen in ziniao_names:
        return target_hyphen
    for zn in ziniao_names:
        if store in zn or target_hyphen in zn:
            return zn
    return None


def open_store(port, browser_oauth):
    result = z_post(port, {
        "action": "startBrowser",
        "browserOauth": browser_oauth,
        "isWaitPluginUpdate": False,
        "isHeadless": 0,
        "requestId": str(uuid.uuid4()),
        "isWebDriverReadOnlyMode": 0,
        "cookieTypeLoad": 0,
        "cookieTypeSave": 0,
        "runMode": "1",
        "isLoadUserPlugin": True,
        "pluginIdType": 1,
        "privacyMode": 0,
        "notPromptForDownload": 1,
        **ziniao_creds(),
    }, 120)
    if str(result.get("statusCode")) != "0":
        raise RuntimeError("打开店铺失败: statusCode=%s" % result.get("statusCode"))
    return result


def stop_store(port, browser_oauth):
    try:
        z_post(port, {
            "action": "stopBrowser",
            "browserOauth": browser_oauth,
            "duplicate": 0,
            "requestId": str(uuid.uuid4()),
            **ziniao_creds(),
        }, 30)
    except Exception:
        pass


def exit_ziniao(port):
    try:
        z_post(port, {"action": "exit", "requestId": str(uuid.uuid4()), **ziniao_creds()}, 10)
    except Exception:
        pass


def close_browser(api_port, browser_oauth, browser):
    stop_store(api_port, browser_oauth)
    try:
        browser.close()
    except Exception:
        pass
