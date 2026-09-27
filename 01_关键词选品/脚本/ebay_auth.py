# -*- coding: utf-8 -*-
"""eBay OAuth 凭据持久化 —— 让脚本自己续期，不用再人工贴 token。

## 为什么要这个模块

原来 `token.local.txt` 里放的是 **access token（用户访问令牌）**。
eBay 的 access token 只有 **2 小时**寿命，而且它本身**不可续期** ——
所以每跑一次都要人去开发者后台重新生成、再贴一遍。

真正能"持久化"的只有两种东西：

| 凭据 | 寿命 | 怎么拿 | 特点 |
|---|---|---|---|
| **refresh token（刷新令牌）** | 约 18 个月 | 授权码流程（浏览器点一次同意） | 脚本每次自动换 access token；**推荐** |
| **client_id + client_secret** | 长期 | 开发者后台 App ID / Cert ID | 可直接换 app token，无需用户同意；权限范围比用户令牌小 |

access token 换完写进本地缓存（含过期时间），2 小时内复用、快过期自动换新的。

## 取 token 的顺序（从高到低，失败会逐条报告，不静默吞）

1. `EbayAuth(token=...)` 显式传入
2. 环境变量 `EBAY_USER_TOKEN` / `EBAY_ACCESS_TOKEN`（临时覆盖，调试用）
3. 缓存 `token.local.json` 里**未过期**的 access_token
4. 缓存里的 **refresh_token** → `grant_type=refresh_token` 换新的
5. 旧的 `token.local.txt`（纯文本用户令牌，兼容老用法）
6. `client_credentials`（需 client_id + client_secret 配对有效）

某条路拿到 401 后会被记进"本次跳过"名单，再取时自动往下一条走
（所以贴了个过期令牌也不会卡死整个流程）。

## 命令行

```bash
python ebay_auth.py --check              # 体检：凭据对不对、缓存里有什么、能不能调通 API
python ebay_auth.py --login               # 打印授权链接（拿 refresh token 的第一步）
python ebay_auth.py --code "<回调URL或code>"   # 把 code 换成 refresh token 并落盘
python ebay_auth.py --refresh             # 立刻刷新一次 access token
python ebay_auth.py --save-user-token <token>  # 手工令牌写进缓存（兼容旧习惯）
```

`--login` / `--code` 需要 config.local.json 的 `ebay_api.ru_name`（eBay 后台的 RuName，
即"你的重定向 URL 名称"）与可用的 `client_id` / `client_secret`。
"""

import base64
import json
import os
import threading
import time
from urllib.parse import parse_qs, quote, urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
CONFIG_CANDIDATES = [
    os.path.join(PROJ, "config.local.json"),
    os.path.join(HERE, "config.json"),
]

DEFAULT_CACHE = os.path.normpath(
    os.path.join(PROJ, "02_soldeazy详情补数", "token.local.json"))
DEFAULT_LEGACY = os.path.normpath(
    os.path.join(PROJ, "02_soldeazy详情补数", "token.local.txt"))

# 默认申请的权限范围：api_scope 覆盖 Browse 的搜索/详情
SCOPES_DEFAULT = ["https://api.ebay.com/oauth/api_scope"]
SCOPE_HINT = {
    "https://api.ebay.com/oauth/api_scope": "Browse 搜索/详情（本项目要用的就这个）",
    "https://api.ebay.com/oauth/api_scope/buy.marketing": "售出数据（需 eBay 额外审批）",
}

REFRESH_SKEW = 300          # 提前 5 分钟续期，避免边界上刚好过期
HTTP_TIMEOUT = 30


class EbayAuthError(RuntimeError):
    pass


def _load_config():
    for p in CONFIG_CANDIDATES:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f), p
            except Exception:
                continue
    return {}, ""


def _mask(v):
    v = str(v or "")
    if not v:
        return "<空>"
    return v[:6] + "..." + v[-4:] if len(v) > 14 else "<已设置:%d位>" % len(v)


def _atomic_write_json(path, data):
    """原子写：先写临时文件再 replace，避免并发/中断留下半个文件。"""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def extract_code(text):
    """从用户粘贴的内容里取出授权码 —— 支持整条回调 URL、查询串、或裸 code。"""
    text = (text or "").strip().strip('"').strip("'")
    if not text:
        return ""
    if "code=" in text:
        q = parse_qs(urlparse(text).query or text)
        if q.get("code"):
            return q["code"][0]
        # 形如 "...?code=xxx&expires_in=299" 但不带 scheme 的情况
        for kv in text.split("?", 1)[-1].split("&"):
            if kv.startswith("code="):
                return kv[5:]
    return text


class EbayAuth:
    """令牌仓库：缓存 + 自动续期 + 多来源回退。线程安全（8 线程并发取详情只续期一次）。"""

    def __init__(self, env=None, token=None, cfg=None, cfg_path="", cache_file=None,
                 legacy_file=None, verbose=True, http=None, now=None):
        if cfg is None:
            cfg, cfg_path = _load_config()
        self.cfg, self.cfg_path = cfg, cfg_path
        self.api_cfg = cfg.get("ebay_api") or {}
        self.env = (env or self.api_cfg.get("env") or "production").lower()
        self.root = ("https://api.sandbox.ebay.com" if self.env == "sandbox"
                     else "https://api.ebay.com")
        self.auth_root = ("https://auth.sandbox.ebay.com" if self.env == "sandbox"
                          else "https://auth.ebay.com")
        self.verbose = verbose
        self.cache_file = cache_file or self.api_cfg.get("token_cache") or DEFAULT_CACHE
        self.legacy_file = legacy_file or DEFAULT_LEGACY
        self.client_id = (os.environ.get("EBAY_CLIENT_ID")
                          or self.api_cfg.get("client_id") or "").strip()
        self.client_secret = (os.environ.get("EBAY_CLIENT_SECRET")
                              or self.api_cfg.get("client_secret") or "").strip()
        self.ru_name = (os.environ.get("EBAY_RU_NAME")
                        or self.api_cfg.get("ru_name") or "").strip()
        self.scopes = list(self.api_cfg.get("scopes") or SCOPES_DEFAULT)

        self._http = http or requests
        self._now = now or time.time
        self._explicit = (token or "").strip()
        self._lock = threading.Lock()
        self._token = ""
        self._source = ""
        self._skip = set()          # 本次运行内已被 401 否掉的来源
        self.tried = []             # 诊用：记录每条路的尝试结果

    # ---------- 日志 ----------
    def _log(self, msg):
        if self.verbose:
            print("  [auth] %s" % msg)

    # ---------- 缓存 ----------
    def read_cache(self):
        if not os.path.isfile(self.cache_file):
            return {}
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception as exc:
            self._log("缓存读取失败（忽略）: %s" % exc)
            return {}

    def write_cache(self, patch):
        d = self.read_cache()
        d.update(patch)
        d["env"] = self.env
        d["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._now()))
        _atomic_write_json(self.cache_file, d)
        try:
            os.chmod(self.cache_file, 0o600)
        except Exception:
            pass
        return d

    def _fresh(self, d):
        exp = d.get("expires_at")
        if not exp:
            return False
        return float(exp) - REFRESH_SKEW > self._now()

    # ---------- OAuth 请求 ----------
    def _basic(self):
        if not (self.client_id and self.client_secret):
            raise EbayAuthError(
                "缺少 client_id / client_secret —— 在开发者后台 Application Keys 页复制"
                "生产环境的 App ID 与 Cert ID，填进 config.local.json 的 ebay_api")
        return (self.client_id, self.client_secret)

    def _post_token(self, data):
        r = self._http.post(self.root + "/identity/v1/oauth2/token", auth=self._basic(),
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            data=data, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            raise EbayAuthError("换 token 失败 HTTP %s: %s"
                                % (r.status_code, r.text[:220].replace("\n", " ")))
        return r.json()

    def _store(self, d, grant, refresh_token=None, keep_refresh=True):
        """把响应写进内存 + 缓存。响应里没带 refresh_token 时不要覆盖旧的。"""
        tok = d.get("access_token") or ""
        if not tok:
            raise EbayAuthError("响应里没有 access_token: %s" % str(d)[:200])
        patch = {
            "access_token": tok,
            "expires_at": self._now() + float(d.get("expires_in") or 7200),
            "grant": grant,
            "scope": d.get("scope") or " ".join(self.scopes),
        }
        new_refresh = refresh_token or d.get("refresh_token")
        if new_refresh:
            patch["refresh_token"] = new_refresh
            # 刷新令牌寿命约 18 个月（eBay 官方口径），这里只在首次拿到时记一次
            patch.setdefault("refresh_expires_at",
                             self._now() + float(d.get("refresh_token_expires_in") or 47304000))
        elif not keep_refresh:
            patch["refresh_token"] = ""
        self._token, self._source = tok, grant
        self.write_cache(patch)
        self._log("%s 成功：access_token 有效期 %.0f 秒%s"
                  % (grant, float(d.get("expires_in") or 7200),
                     "，已带 refresh_token 落盘" if new_refresh else ""))
        return tok

    def client_credentials(self):
        return self._store(
            self._post_token({"grant_type": "client_credentials",
                              "scope": " ".join(self.scopes)}),
            "client_credentials")

    def refresh(self):
        rt = (self.read_cache().get("refresh_token") or "").strip()
        if not rt:
            raise EbayAuthError("缓存里没有 refresh_token —— 先跑一次 --login 拿刷新令牌")
        return self._store(
            self._post_token({"grant_type": "refresh_token", "refresh_token": rt,
                              "scope": " ".join(self.scopes)}),
            "refresh_token", refresh_token=rt)

    # ---------- 授权码流程（拿 refresh token）----------
    def login_url(self):
        """生成用户同意链接。redirect_uri 必须是 RuName（重定向 URL 名称），不是网址本身。"""
        if not self.ru_name:
            raise EbayAuthError(
                "缺少 ru_name —— 在开发者后台 User Tokens / Get a Token from eBay 页面"
                "里能看到「你的重定向 URL 名称」(RuName)，填进 config.local.json 的 "
                "ebay_api.ru_name")
        return ("%s/oauth2/authorize?client_id=%s&redirect_uri=%s&response_type=code"
                "&scope=%s" % (self.auth_root, quote(self.client_id),
                               quote(self.ru_name), quote(" ".join(self.scopes))))

    def exchange_code(self, code_or_url):
        code = extract_code(code_or_url)
        if not code:
            raise EbayAuthError("没解析出 code")
        return self._store(
            self._post_token({"grant_type": "authorization_code", "code": code,
                              "redirect_uri": self.ru_name}),
            "authorization_code")

    # ---------- 多来源取 token ----------
    def _from_env(self):
        for k in ("EBAY_USER_TOKEN", "EBAY_ACCESS_TOKEN"):
            v = (os.environ.get(k) or "").strip()
            if v:
                return v, "env:" + k
        return "", ""

    def _from_legacy(self):
        p = self.api_cfg.get("token_file") or self.legacy_file
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    t = f.read().strip()
            except Exception:
                return "", ""
            if t:
                return t, "legacy:%s" % os.path.basename(p)
        t = (self.api_cfg.get("user_token") or "").strip()
        if t:
            return t, "config:ebay_api.user_token"
        return "", ""

    def providers(self):
        """返回按优先级排列的 (名字, 取令牌函数)。函数抛异常 = 这条路不通。"""
        def p_explicit():
            return self._explicit

        def p_env():
            t, src = self._from_env()
            if not t:
                raise EbayAuthError("未设置")
            return t

        def p_cache():
            d = self.read_cache()
            if d.get("env") and d["env"] != self.env:
                raise EbayAuthError("缓存是 %s 环境的令牌，当前要 %s" % (d["env"], self.env))
            if not self._fresh(d):
                raise EbayAuthError("缓存里没有未过期的 access_token")
            return d["access_token"]

        def p_legacy():
            t, src = self._from_legacy()
            if not t:
                raise EbayAuthError("没有 token.local.txt / config 里的 user_token")
            return t

        return [
            ("显式参数 token=", p_explicit),
            ("环境变量 EBAY_USER_TOKEN/ACCESS_TOKEN", p_env),
            ("缓存里未过期的 access_token", p_cache),
            ("refresh_token 续期", self.refresh),
            ("token.local.txt（兼容旧用法）", p_legacy),
            ("client_credentials", self.client_credentials),
        ]

    def resolve(self, force=False):
        with self._lock:
            if self._token and not force:
                return self._token
            self.tried = []
            errors = []
            for name, fn in self.providers():
                if name in self._skip:
                    self.tried.append((name, "跳过（本次已 401）"))
                    continue
                try:
                    tok = (fn() or "").strip()
                    if not tok:
                        raise EbayAuthError("返回空")
                    self.tried.append((name, "OK"))
                    # refresh_token / client_credentials 内部已写好来源名
                    if self._source in ("", "explicit"):
                        self._source = name
                    if name.startswith("显式") or name.startswith("环境") or name.startswith("缓存") \
                            or name.startswith("token.local"):
                        self._source = name
                    self._token = tok
                    self._log("token 来源：%s（长度 %d）" % (name, len(tok)))
                    return self._token
                except Exception as exc:
                    msg = str(exc).replace("\n", " ")[:160]
                    self.tried.append((name, "失败：%s" % msg))
                    errors.append("  - %s → %s" % (name, msg))
            raise EbayAuthError(
                "拿不到可用的 eBay 令牌。逐条尝试结果：\n%s\n"
                "建议：① 跑 `python 脚本/ebay_auth.py --check` 看凭据是否配对；"
                "② 有可用 client_id/client_secret 的话跑 `--login` 换一份 18 个月的 "
                "refresh_token，之后脚本就自动续期了。"
                % ("\n".join(errors) if errors else "  （全部被跳过）"))

    def token(self, force=False):
        return self.resolve(force=force)

    def invalidate(self, reason=""):
        """收到 401 时调用：清掉内存令牌、把当前来源拉黑，下次自动换下一条路。"""
        with self._lock:
            if self._source and self._source not in ("", "explicit"):
                self._skip.add(self._source)
            self._log("令牌被拒（%s），已停用来源「%s」，改用下一条路"
                      % (reason or "401", self._source or "未知"))
            self._token = ""
            return True

    def save_user_token(self, tok):
        """手工令牌写进缓存（不知道过期时间，按"用到被拒为止"处理）。"""
        tok = (tok or "").strip()
        if not tok:
            raise EbayAuthError("令牌为空")
        self._token, self._source = tok, "手工写入缓存"
        self.write_cache({"access_token": tok, "expires_at": None,
                          "grant": "manual", "scope": " ".join(self.scopes)})
        return self.cache_file

    def credential_warnings(self):
        """凭据形态自检 —— 这些错误肉眼很难看出来，但会让 OAuth 直接报 invalid_client。

        实测踩过的坑（2026-09-15）：
          config 里 client_id 填了**沙箱** App ID（BETA-SBX-…），
          client_secret 填的却是页面上那个 **Dev ID**（UUID 形态）——
          Dev ID 根本不参与 OAuth，Cert ID 才是 client_secret。
          结果 production / sandbox 都报 invalid_client，白试了几十次。
        """
        import re
        warns = []
        cid, sec = self.client_id or "", self.client_secret or ""
        if not cid or not sec:
            warns.append("client_id / client_secret 没配全（缺凭据无法换 token）")
            return warns
        if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                        r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", sec):
            warns.append("client_secret 是 UUID 形态 → 这是 **Dev ID**（开发者 ID），不是 Cert ID！"
                         "OAuth 的 client_secret 必须填 Cert ID（PRD-… / SBX-…）")
        cid_u = cid.upper()
        if "-PRD-" not in cid_u and "-SBX-" not in cid_u:
            warns.append("client_id 既不含 -PRD- 也不含 -SBX-，形态可疑（正常是 <应用名>-PRD-… ）")
        if "-SBX-" in cid_u and self.env == "production":
            warns.append("client_id 是**沙箱**(SBX) App ID，却要打 production —— 环境不匹配")
        if "-PRD-" in cid_u and self.env == "sandbox":
            warns.append("client_id 是**生产**(PRD) App ID，却要打 sandbox —— 环境不匹配")
        if sec.upper().startswith("PRD-") and "-SBX-" in cid_u:
            warns.append("App ID 是沙箱的、Cert ID 是生产的 —— 必须用**同一套密钥集**里的两个值")
        if sec.upper().startswith("SBX-") and "-PRD-" in cid_u:
            warns.append("App ID 是生产的、Cert ID 是沙箱的 —— 必须用**同一套密钥集**里的两个值")
        if not warns:
            warns.append("凭据形态检查通过（App ID / Cert ID 环境标记一致）")
        return warns

    def status(self):
        d = self.read_cache()
        exp = d.get("expires_at")
        return {
            "环境": self.env,
            "API 根": self.root,
            "client_id": _mask(self.client_id),
            "client_secret": _mask(self.client_secret),
            "ru_name": _mask(self.ru_name),
            "缓存文件": self.cache_file,
            "缓存存在": os.path.isfile(self.cache_file),
            "有 access_token": bool(d.get("access_token")),
            "有 refresh_token": bool(d.get("refresh_token")),
            "access_token 剩余秒": (round(float(exp) - self._now()) if exp else None),
            "refresh_token 剩余天": (round((float(d["refresh_expires_at"]) - self._now()) / 86400)
                                     if d.get("refresh_expires_at") else None),
            "上次换令牌方式": d.get("grant"),
            "缓存更新时间": d.get("updated_at"),
        }


# ---------- 命令行 ----------
def _print_status(auth):
    st = auth.status()
    for k, v in st.items():
        print("  %-22s %s" % (k, v))
    warns = auth.credential_warnings()
    for w in warns:
        print("  %-22s %s" % ("⚠️ 凭据检查" if "通过" not in w else "   凭据检查", w))


def _probe(auth, site="uk"):
    """用拿到的令牌真打一次 Browse API，验证权限范围够不够。"""
    tok = auth.token()
    hdr = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
           "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DGB%2Czip%3DSW1A1AA"}
    r = requests.get(auth.root + "/buy/browse/v1/item_summary/search", headers=hdr,
                     params={"q": "wireless earbuds", "limit": 1}, timeout=30)
    print("  Browse 探针 → HTTP %s" % r.status_code)
    if r.status_code == 200:
        d = r.json()
        print("  total=%s 首条=%s" % (d.get("total"),
                                     (d.get("itemSummaries") or [{}])[0].get("title", "-")[:50]))
    else:
        print("  %s" % r.text[:250].replace("\n", " "))
    return r.status_code


def _check_deep(auth):
    """体检的完整逻辑：逐条来源试到底，直到有一条**真能调通 API**为止。

    只"读到一个令牌字符串"不等于"这个令牌能用" —— 所以必须真打一次
    （实测坑：token.local.txt 里躺着一个 2 小时前就过期的令牌，
     只检查"文件非空"会误报健康）。
    """
    attempts = []
    for _ in range(8):
        try:
            auth.resolve(force=True)
        except EbayAuthError as exc:
            print("  %s" % str(exc).replace("\n", "\n  "))
            return 1, attempts
        src = auth._source
        code = _probe(auth)
        attempts.append((src, code))
        if code == 200:
            print("-" * 70)
            print("  结论：来源「%s」可用 ✅  之后的采集会走它，并在过期时自动续期" % src)
            return 0, attempts
        if code in (401, 403):
            print("  来源「%s」不可用（HTTP %s），换下一条路…" % (src, code))
            auth.invalidate("HTTP %s" % code)
            continue
        print("-" * 70)
        print("  结论：令牌大概率是好的，但 eBay 返回了 %s（不是鉴权问题，看上面的报文）" % code)
        return 1, attempts
    print("  所有来源都试过了，没有一条能调通。")
    return 1, attempts


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="eBay OAuth 凭据体检 / 持久化")
    p.add_argument("--env", choices=("production", "sandbox"), default=None)
    p.add_argument("--check", action="store_true", help="体检：凭据 + 缓存 + 真调一次 API")
    p.add_argument("--login", action="store_true", help="打印授权链接（拿 refresh token）")
    p.add_argument("--code", default="", help="把回调 URL 或 code 换成 refresh_token")
    p.add_argument("--refresh", action="store_true", help="立刻刷新 access token")
    p.add_argument("--save-user-token", dest="save_user_token", default="",
                   help="手工令牌写进缓存")
    p.add_argument("--providers", action="store_true", help="只跑一遍来源探测，不调 API")
    args = p.parse_args(argv)

    auth = EbayAuth(env=args.env)

    if args.login:
        print("授权链接（浏览器打开并同意）：\n")
        print(auth.login_url())
        print("\n同意后浏览器会跳到你的 RuName 地址，地址栏里带 `?code=...`；"
              "把整条 URL（或只把 code）贴给下一条命令：")
        print("  python 脚本/ebay_auth.py --code \"<粘贴回调URL>\"")
        print("\n申请的权限：")
        for s in auth.scopes:
            print("  - %s  (%s)" % (s, SCOPE_HINT.get(s, "自定义")))
        return 0

    if args.code:
        auth.exchange_code(args.code)
        print("已保存 refresh_token 到 %s" % auth.cache_file)
        return 0

    if args.save_user_token:
        print("已写入 %s" % auth.save_user_token(args.save_user_token))
        return 0

    if args.refresh:
        auth.refresh()
        return 0

    print("=" * 70)
    print("eBay 凭据体检")
    print("=" * 70)
    _print_status(auth)

    if args.providers:
        print("-" * 70)
        try:
            auth.resolve()
        except EbayAuthError as exc:
            print("  取令牌失败：\n%s" % exc)
        for name, res in auth.tried:
            print("  %-38s %s" % (name, res))
        print("=" * 70)
        return 0

    print("-" * 70)
    code, attempts = _check_deep(auth)
    print("-" * 70)
    print("  逐条来源尝试记录：")
    for name, res in auth.tried:
        print("    %-38s %s" % (name, res))
    print("=" * 70)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
