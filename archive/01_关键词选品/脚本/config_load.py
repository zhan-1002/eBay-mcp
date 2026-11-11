# -*- coding: utf-8 -*-
"""读 .env 或 config.local.json 里的凭据。密码不写进脚本。

优先级：环境变量 > .env > config.local.json。
2026-11-11 起明文凭据统一放在仓库根的 .env（已在 .gitignore），
config.local.json 只留非敏感配置；这里补一层 .env 读取，旧脚本不用改调用方式。
"""

import json
import os

from common_path import project_root

try:  # 没装 python-dotenv 时退回纯环境变量，不阻断脚本
    from dotenv import load_dotenv

    def _find_env_file():
        """从脚本所在层级往上找仓库根的 .env。

        归档脚本的 PROJECT_ROOT 指向 archive/，不是仓库根，直接拼会找错地方。
        """
        here = project_root()
        for _ in range(4):
            candidate = os.path.join(here, ".env")
            if os.path.isfile(candidate):
                return candidate
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
        return ""

    _env_file = _find_env_file()
    if _env_file:
        load_dotenv(_env_file, override=False)
except ImportError:  # pragma: no cover - 取决于环境
    pass


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
            "缺少紫鸟账号。请在仓库根 .env 填 ZINIAO_COMPANY / ZINIAO_USERNAME / "
            "ZINIAO_PASSWORD（推荐），或设置同名环境变量。"
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
            "缺少 eBay API 密钥。请在仓库根 .env 填 EBAY_CLIENT_ID / EBAY_CLIENT_SECRET"
            "（推荐），或设置同名环境变量。"
        )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "environment": env,
    }
