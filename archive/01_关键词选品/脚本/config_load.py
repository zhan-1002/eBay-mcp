# -*- coding: utf-8 -*-
"""读 config.local.json 或环境变量。密码不写进脚本。"""

import json
import os

from common_path import project_root


def _read_local_json():
    path = os.path.join(project_root(), "config.local.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ziniao_creds():
    data = _read_local_json()
    z = data.get("ziniao") or {}
    company = os.environ.get("ZINIAO_COMPANY") or z.get("company") or ""
    username = os.environ.get("ZINIAO_USERNAME") or z.get("username") or ""
    password = os.environ.get("ZINIAO_PASSWORD") or z.get("password") or ""
    if not (company and username and password):
        raise RuntimeError(
            "缺少紫鸟账号。请复制 config.example.json 为 config.local.json 并填写 ziniao。"
        )
    return {"company": company, "username": username, "password": password}


def ebay_api_creds(environment=None):
    data = _read_local_json()
    api = data.get("ebay_api") or {}
    env = (environment
           or os.environ.get("EBAY_API_ENV")
           or api.get("environment")
           or "sandbox")
    env = str(env).strip().lower()
    if env not in ("sandbox", "production"):
        raise RuntimeError("ebay_api.environment 只能是 sandbox 或 production，当前: %s" % env)
    client_id = os.environ.get("EBAY_CLIENT_ID") or api.get("client_id") or ""
    client_secret = os.environ.get("EBAY_CLIENT_SECRET") or api.get("client_secret") or ""
    if not (client_id and client_secret):
        raise RuntimeError(
            "缺少 eBay API 密钥。请在 config.local.json 的 ebay_api 填 client_id / client_secret，"
            "或设置环境变量 EBAY_CLIENT_ID / EBAY_CLIENT_SECRET。"
        )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "environment": env,
    }
