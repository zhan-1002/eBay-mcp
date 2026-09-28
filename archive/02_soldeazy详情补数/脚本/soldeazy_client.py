# -*- coding: utf-8 -*-
"""Soldeazy 会话客户端：复用登录保存的 cookie，走 requests 取数（不开浏览器）。

用法:
    c = SoldeazyClient()
    html = c.get_text("/app/soldeazy/datasheet/dsheet_list")
    data = c.get_json("/app/soldeazy/xxx/yyy", params={...})
"""

import json
import os
import re
import time

import requests

BASE = "https://stiger.soldeazy.com"
TARGET_PATH = "/app/soldeazy/datasheet/dsheet_list"
LOGIN_PATH = "/app/soldeazy/login"

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
SESSION_FILE = os.path.join(PROJ, "输出", "_session", "soldeazy_session.json")


class SessionExpired(RuntimeError):
    """会话失效（被踢回登录页）——调用方应提示重跑 soldeazy_login.py。"""


class SoldeazyClient:
    def __init__(self, session_file=None, timeout=(15, 60)):
        self.session_file = session_file or SESSION_FILE
        self.timeout = timeout
        if not os.path.isfile(self.session_file):
            raise SessionExpired("没有会话文件 %s，请先跑 soldeazy_login.py" % self.session_file)
        state = json.load(open(self.session_file, encoding="utf-8"))
        self.state = state
        self.s = requests.Session()
        for c in state.get("cookies") or []:
            try:
                self.s.cookies.set(c.get("name"), c.get("value"),
                                   domain=c.get("domain"), path=c.get("path") or "/")
            except Exception:
                pass
        ua = state.get("user_agent") or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
        self.s.headers.update({
            "User-Agent": ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.saved_at = state.get("saved_at")

    # ---------- 基础请求 ----------
    def _check(self, resp):
        if "/login" in (resp.url or "") and LOGIN_PATH in (resp.url or ""):
            raise SessionExpired("被踢回登录页，会话已过期（保存于 %s）" % self.saved_at)
        return resp

    def get(self, path, params=None, headers=None, allow_redirects=True):
        url = path if path.startswith("http") else (BASE + path)
        resp = self.s.get(url, params=params, headers=headers,
                          timeout=self.timeout, verify=False,
                          allow_redirects=allow_redirects)
        return self._check(resp)

    def post(self, path, data=None, json_body=None, headers=None):
        url = path if path.startswith("http") else (BASE + path)
        resp = self.s.post(url, data=data, json=json_body, headers=headers,
                           timeout=self.timeout, verify=False)
        return self._check(resp)

    def get_text(self, path, params=None, headers=None):
        r = self.get(path, params=params, headers=headers)
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text

    def get_json(self, path, params=None, headers=None):
        r = self.get(path, params=params, headers=headers)
        txt = r.text.strip()
        try:
            return r.json()
        except Exception:
            # 有些接口返回 JSON 但 content-type 不对，或 JSON 里混了前缀
            m = re.search(r"(\{.*\}|\[.*\])", txt, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
            raise RuntimeError("返回不是 JSON（HTTP %s，前 200 字: %s）"
                               % (r.status_code, txt[:200]))

    def csrf_token(self):
        """从任意页面里取 csrf token（本站在用 oriCsrfToken 之类时可得）。"""
        html = self.get_text(TARGET_PATH)
        for pat in (r"oriCsrfToken\.init\('X-CSRF-TOKEN',\s*'([^']+)'\)",
                    r'name="csrf[_-]?token"\s+value="([^"]+)"',
                    r'X-CSRF-TOKEN["\']?\s*[:=]\s*["\']([^"\']+)["\']'):
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return ""

    # ---------- 业务 ----------
    def dsheet_list_html(self, params=None):
        return self.get_text(TARGET_PATH, params=params)

    def alive(self):
        try:
            r = self.get(TARGET_PATH)
            return "/login" not in (r.url or "")
        except SessionExpired:
            return False
        except Exception:
            return False


def safe_name(t):
    return re.sub(r"\W+", "_", t or "x")[:40]
