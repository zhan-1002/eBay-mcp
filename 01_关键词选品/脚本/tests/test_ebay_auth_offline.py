# -*- coding: utf-8 -*-
"""ebay_auth 离线单测 —— 注入假 HTTP 与假时钟，不联网、不碰真实凭据。

覆盖：
  1. extract_code 解析三种粘贴形态
  2. 缓存未过期 → 直接用，不发任何请求
  3. 缓存过期 + 有 refresh_token → 自动续期并写回（关键：持久化靠这条）
  4. refresh_token 续期时**不能**把 refresh_token 弄丢（eBay 刷新响应不返回新的）
  5. client_credentials 回退
  6. 过期令牌被 401 → invalidate 后跳过该来源，换下一条路
  7. 缓存环境不匹配（sandbox 令牌用在 production）→ 忽略缓存
  8. 原子写：缓存文件能读回、且带过期时间
"""

import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import ebay_auth  # noqa: E402


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class FakeHttp:
    """记录调用并按脚本回应；token 端点默认返回 200 + access_token。"""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def post(self, url, auth=None, headers=None, data=None, timeout=None):
        self.calls.append({"url": url, "auth": auth, "data": dict(data or {})})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(200, {"access_token": "at-from-%s" % (data or {}).get("grant_type"),
                                  "expires_in": 7200, "scope": "https://api.ebay.com/oauth/api_scope"})


class Clock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def make_auth(tmp, http, clock, **kw):
    cfg = {"ebay_api": {"env": kw.pop("env", "production"),
                        "client_id": "CID-1234567890",
                        "client_secret": "SECRET-1234567890",
                        "ru_name": "RUNAME-TEST"}}
    return ebay_auth.EbayAuth(cfg=cfg,
                              cache_file=os.path.join(tmp, "token.local.json"),
                              legacy_file=os.path.join(tmp, "token.local.txt"),
                              verbose=False, http=http, now=clock, **kw)


def write_cache(path, **patch):
    d = {"env": "production"}
    d.update(patch)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


class ExtractCodeTests(unittest.TestCase):
    def test_full_callback_url(self):
        url = ("https://my-redirect.example.com/?code=v%5E1.1%23i%5E1%23abc123"
               "&expires_in=299")
        self.assertEqual(ebay_auth.extract_code(url), "v^1.1#i^1#abc123")

    def test_bare_code(self):
        self.assertEqual(ebay_auth.extract_code("  v^1.1#i^1#xyz  "), "v^1.1#i^1#xyz")

    def test_query_string_without_scheme(self):
        self.assertEqual(ebay_auth.extract_code("?code=AAA&expires_in=299"), "AAA")


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clock = Clock()
        self.http = FakeHttp()

    def test_fresh_cache_used_without_any_request(self):
        auth = make_auth(self.tmp, self.http, self.clock)
        write_cache(auth.cache_file, access_token="cached-token",
                    expires_at=self.clock.t + 3600, grant="authorization_code")
        self.assertEqual(auth.token(), "cached-token")
        self.assertEqual(self.http.calls, [], "未过期就不该发任何请求")

    def test_expired_cache_triggers_refresh_and_writes_back(self):
        auth = make_auth(self.tmp, self.http, self.clock)
        write_cache(auth.cache_file, access_token="old", expires_at=self.clock.t - 10,
                    refresh_token="RT-18-MONTHS", grant="authorization_code")
        self.assertEqual(auth.token(), "at-from-refresh_token")
        self.assertEqual(self.http.calls[0]["data"]["grant_type"], "refresh_token")
        self.assertEqual(self.http.calls[0]["data"]["refresh_token"], "RT-18-MONTHS")
        # 落盘：新 access_token + 新的过期时间 + refresh_token 必须还在
        with io.open(auth.cache_file, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["access_token"], "at-from-refresh_token")
        self.assertGreater(d["expires_at"], self.clock.t)
        self.assertEqual(d["refresh_token"], "RT-18-MONTHS")

    def test_refresh_response_without_new_refresh_token_keeps_old(self):
        """eBay 的 refresh_token 响应通常不回新的刷新令牌，丢了就白授权一次。"""
        auth = make_auth(self.tmp, self.http, self.clock)
        write_cache(auth.cache_file, access_token="old", expires_at=self.clock.t - 1,
                    refresh_token="RT-KEEP-ME")
        auth.token()
        with io.open(auth.cache_file, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("refresh_token"), "RT-KEEP-ME")

    def test_skew_refreshes_before_actual_expiry(self):
        """剩 60 秒也算"该换了"（提前 5 分钟），避免边界上刚好过期。"""
        auth = make_auth(self.tmp, self.http, self.clock)
        write_cache(auth.cache_file, access_token="about-to-die",
                    expires_at=self.clock.t + 60, refresh_token="RT")
        self.assertEqual(auth.token(), "at-from-refresh_token")

    def test_env_mismatch_ignores_cache(self):
        """sandbox 的令牌绝不能拿去打 production —— 但也不要卡死，继续往下一条路走。"""
        auth = make_auth(self.tmp, self.http, self.clock, env="production")
        write_cache(auth.cache_file, env="sandbox", access_token="sandbox-token",
                    expires_at=self.clock.t + 3600)
        tok = auth.token()
        self.assertNotEqual(tok, "sandbox-token")
        self.assertEqual(self.http.calls[0]["data"]["grant_type"], "client_credentials")
        reasons = dict(auth.tried)
        self.assertIn("sandbox", reasons["缓存里未过期的 access_token"])

    def test_env_mismatch_and_no_credentials_raises(self):
        auth = make_auth(self.tmp, self.http, self.clock, env="production")
        auth.client_secret = ""
        write_cache(auth.cache_file, env="sandbox", access_token="sandbox-token",
                    expires_at=self.clock.t + 3600)
        with self.assertRaises(ebay_auth.EbayAuthError):
            auth.token()

    def test_second_call_reuses_in_memory_token(self):
        auth = make_auth(self.tmp, self.http, self.clock)
        write_cache(auth.cache_file, access_token="cached",
                    expires_at=self.clock.t + 3600)
        auth.token()
        auth.token()
        self.assertEqual(self.http.calls, [])


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clock = Clock()

    def test_client_credentials_when_no_cache(self):
        http = FakeHttp()
        auth = make_auth(self.tmp, http, self.clock)
        self.assertEqual(auth.token(), "at-from-client_credentials")
        self.assertEqual(http.calls[0]["data"]["grant_type"], "client_credentials")
        self.assertEqual(http.calls[0]["auth"], ("CID-1234567890", "SECRET-1234567890"))

    def test_legacy_txt_used_when_no_cache(self):
        http = FakeHttp()
        auth = make_auth(self.tmp, http, self.clock)
        with io.open(auth.legacy_file, "w", encoding="utf-8") as f:
            f.write("v^1.1#i^1#legacy-user-token")
        self.assertEqual(auth.token(), "v^1.1#i^1#legacy-user-token")
        self.assertEqual(http.calls, [], "有现成令牌就不该去换")

    def test_401_marks_source_dead_and_moves_on(self):
        """贴了个过期手工令牌：拒掉之后要自动往下走 client_credentials。"""
        http = FakeHttp()
        auth = make_auth(self.tmp, http, self.clock)
        with io.open(auth.legacy_file, "w", encoding="utf-8") as f:
            f.write("expired-manual-token")
        self.assertEqual(auth.token(), "expired-manual-token")
        auth.invalidate("HTTP 401")
        self.assertEqual(auth.token(force=True), "at-from-client_credentials")
        self.assertEqual(http.calls[0]["data"]["grant_type"], "client_credentials")

    def test_all_paths_fail_reports_every_attempt(self):
        http = FakeHttp([FakeResponse(401, {"error": "invalid_client",
                                            "error_description": "client authentication failed"})])
        auth = make_auth(self.tmp, http, self.clock)
        with self.assertRaises(ebay_auth.EbayAuthError) as ctx:
            auth.token()
        msg = str(ctx.exception)
        self.assertIn("client_credentials", msg)
        names = [n for n, _ in auth.tried]
        self.assertIn("client_credentials", names)
        self.assertEqual(len(names), 6, "6 条来源都要出现在尝试记录里")

    def test_missing_client_secret_gives_actionable_error(self):
        http = FakeHttp()
        auth = make_auth(self.tmp, http, self.clock)
        auth.client_secret = ""
        with self.assertRaises(ebay_auth.EbayAuthError) as ctx:
            auth.token()
        self.assertIn("Cert ID", str(ctx.exception))


class LoginUrlTests(unittest.TestCase):
    def test_login_url_uses_runame_as_redirect(self):
        tmp = tempfile.mkdtemp()
        auth = make_auth(tmp, FakeHttp(), Clock())
        url = auth.login_url()
        self.assertIn("https://auth.ebay.com/oauth2/authorize", url)
        self.assertIn("response_type=code", url)
        self.assertIn("redirect_uri=RUNAME-TEST", url)
        self.assertIn("scope=https", url)

    def test_sandbox_uses_sandbox_auth_host(self):
        tmp = tempfile.mkdtemp()
        auth = make_auth(tmp, FakeHttp(), Clock(), env="sandbox")
        self.assertIn("https://auth.sandbox.ebay.com", auth.login_url())

    def test_missing_runame_says_where_to_get_it(self):
        tmp = tempfile.mkdtemp()
        auth = make_auth(tmp, FakeHttp(), Clock())
        auth.ru_name = ""
        with self.assertRaises(ebay_auth.EbayAuthError) as ctx:
            auth.login_url()
        self.assertIn("RuName", str(ctx.exception))

    def test_exchange_code_saves_refresh_token(self):
        tmp = tempfile.mkdtemp()
        http = FakeHttp([FakeResponse(200, {"access_token": "at1", "expires_in": 7200,
                                            "refresh_token": "RT-LONG",
                                            "refresh_token_expires_in": 47304000})])
        auth = make_auth(tmp, http, Clock())
        auth.exchange_code("https://cb.example.com/?code=THECODE&expires_in=299")
        self.assertEqual(http.calls[0]["data"]["grant_type"], "authorization_code")
        self.assertEqual(http.calls[0]["data"]["code"], "THECODE")
        self.assertEqual(http.calls[0]["data"]["redirect_uri"], "RUNAME-TEST")
        with io.open(auth.cache_file, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["refresh_token"], "RT-LONG")
        self.assertIn("refresh_expires_at", d)

    def test_save_user_token_writes_cache_without_expiry(self):
        tmp = tempfile.mkdtemp()
        auth = make_auth(tmp, FakeHttp(), Clock())
        auth.save_user_token("v^1.1#i^1#manual")
        with io.open(auth.cache_file, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["access_token"], "v^1.1#i^1#manual")
        self.assertIsNone(d["expires_at"])
        self.assertEqual(d["grant"], "manual")


class CredentialWarningTests(unittest.TestCase):
    """凭据形态自检 —— 这套检查是从真实踩坑里长出来的。

    真实事故：config 里 client_id 填了沙箱 App ID（BETA-SBX-…），
    client_secret 填的却是后台页面上那个 Dev ID（UUID 形态）。
    Dev ID 不参与 OAuth，Cert ID 才是 client_secret →
    production / sandbox 都报 invalid_client，白试了几十次。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _auth(self, cid, sec, env="production"):
        cfg = {"ebay_api": {"env": env, "client_id": cid, "client_secret": sec}}
        return ebay_auth.EbayAuth(cfg=cfg,
                                  cache_file=os.path.join(self.tmp, "c.json"),
                                  verbose=False, http=FakeHttp(), now=Clock())

    def test_dev_id_in_secret_slot_is_caught(self):
        a = self._auth("BETA-SBX-f82b86fbd-f4f4c153",
                       "16880a0b-a69a-4ac8-91fd-93986bb62f8a")
        w = " ".join(a.credential_warnings())
        self.assertIn("Dev ID", w)
        self.assertIn("Cert ID", w)

    def test_sandbox_app_id_with_production_env_is_caught(self):
        a = self._auth("BETA-SBX-f82b86fbd-f4f4c153", "SBX-abc-def", env="production")
        self.assertIn("沙箱", " ".join(a.credential_warnings()))

    def test_production_app_id_with_sandbox_env_is_caught(self):
        a = self._auth("BETA-PRD-f82b86fbd-f4f4c153", "PRD-abc-def", env="sandbox")
        self.assertIn("生产", " ".join(a.credential_warnings()))

    def test_mixed_keysets_are_caught(self):
        a = self._auth("BETA-SBX-f82b86fbd-f4f4c153",
                       "PRD-examplecert000-0000-0000-0000-0000")
        self.assertIn("同一套密钥集", " ".join(a.credential_warnings()))

    def test_consistent_production_pair_passes(self):
        """注意：形态检查通过 ≠ 密钥集真的生效，那只有真打一次 API 才知道。"""
        a = self._auth("BETA-PRD-f82b86fbd-f4f4c153",
                       "PRD-examplecert000-0000-0000-0000-0000")
        self.assertIn("通过", " ".join(a.credential_warnings()))

    def test_missing_credentials_reported(self):
        a = self._auth("", "")
        self.assertIn("没配全", " ".join(a.credential_warnings()))


class CostEstimateTests(unittest.TestCase):
    """花费估算 —— 关键在于**区分缓存命中与未命中**，否则会高估几十倍。

    实测（2026-09-15，wireless earbuds / 2 轮）：
      prompt_cache_hit_tokens 7296 ｜ miss 781 ｜ completion 1221
    第 2 轮的 prompt 是第 1 轮的**严格前缀**（代码里是 `prompt = prompt + 反馈`），
    所以命中率天然很高（实测 90%）。
    """

    def setUp(self):
        sys.path.insert(0, SCRIPTS)
        import llm_titles
        self.m = llm_titles

    def test_matches_measured_run(self):
        usage = {"prompt_tokens": 8077, "prompt_cache_hit_tokens": 7296,
                 "prompt_cache_miss_tokens": 781, "completion_tokens": 1221}
        cost = self.m.estimate_cost(usage)
        # 7296*0.02 + 781*1.0 + 1221*3.0 = 146 + 781 + 3663（单位：百万分之一元）
        self.assertAlmostEqual(cost, (7296 * 0.02 + 781 * 1.0 + 1221 * 3.0) / 1e6, places=9)
        self.assertLess(cost, 0.01, "一次完整生成应该在 1 分钱以内")

    def test_cache_hit_is_much_cheaper(self):
        base = {"prompt_tokens": 10000, "completion_tokens": 0}
        all_miss = self.m.estimate_cost(dict(base, prompt_cache_hit_tokens=0,
                                             prompt_cache_miss_tokens=10000))
        all_hit = self.m.estimate_cost(dict(base, prompt_cache_hit_tokens=10000,
                                            prompt_cache_miss_tokens=0))
        self.assertLess(all_hit, all_miss / 10)

    def test_missing_cache_fields_falls_back_to_upper_bound(self):
        """服务端没回明细时，按"全部未命中"算（宁可高估，不要报喜不报忧）。"""
        usage = {"prompt_tokens": 1000, "completion_tokens": 100}
        cost = self.m.estimate_cost(usage)
        expect = (1000 * self.m.PRICE_DEFAULT["cache_miss"]
                  + 100 * self.m.PRICE_DEFAULT["output"]) / 1e6
        self.assertAlmostEqual(cost, expect, places=9)

    def test_price_can_be_overridden_from_config(self):
        usage = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 0,
                 "prompt_cache_miss_tokens": 1000, "completion_tokens": 0}
        cheap = self.m.estimate_cost(usage, price={"cache_miss": 0.1})
        self.assertAlmostEqual(cheap, 1000 * 0.1 / 1e6, places=9)

    def test_off_peak_is_cheaper(self):
        usage = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 0,
                 "prompt_cache_miss_tokens": 1000, "completion_tokens": 500}
        self.assertLess(self.m.estimate_cost(usage, off_peak=True),
                        self.m.estimate_cost(usage, off_peak=False))


if __name__ == "__main__":
    unittest.main()
