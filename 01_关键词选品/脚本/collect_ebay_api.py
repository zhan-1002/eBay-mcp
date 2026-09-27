# -*- coding: utf-8 -*-
"""eBay 官方 Browse API 采集（替代紫鸟抓搜索页 + Soldeazy 补详情）。

实测依据（2026-09-15，生产环境）：
  - item_summary/search：limit 上限 200，**一次请求就能拿满 200 条**（默认就取 200，
    不必再截断成 120）；搜索结果**没有** item specifics
  - getItem：localizedAspects 覆盖率 **100%**（120 条与 200 条都实测过）；
    categoryId/categoryPath/图片/描述 均 100%
  - 调用消耗：200 条 = 1 次 search + 200 次 getItem；8 线程并发约 20~25 秒
  - 配送地由 header 精确指定（X-EBAY-C-ENDUSERCTX），GB/US/DE 实测生效

凭据（交给 ebay_auth.EbayAuth 统一管理，会自动续期）：
  1. 环境变量 EBAY_USER_TOKEN / EBAY_ACCESS_TOKEN
  2. 缓存 02_soldeazy详情补数/token.local.json 里未过期的 access_token
  3. 缓存里的 refresh_token → 自动换新的 access token（**持久化靠这条**）
  4. 02_soldeazy详情补数/token.local.txt（兼容旧的手工令牌）
  5. client_credentials（需配对的 client_id + client_secret）

  access token 只有 2 小时；收到 401 会自动换令牌并重试一次，不再中途崩掉。
  体检 / 换取 18 个月 refresh_token：`python 脚本/ebay_auth.py --check`、`--login`。

环境：config.local.json 的 ebay_api.env = "production"（默认）| "sandbox"
"""

import json
import os
import re
import threading
import time
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))
CONFIG_CANDIDATES = [
    os.path.join(PROJ, "config.local.json"),
    os.path.join(HERE, "config.json"),
]
DEFAULT_TOKEN_FILE = os.path.normpath(
    os.path.join(PROJ, "02_soldeazy详情补数", "token.local.txt"))

API_LIMIT_MAX = 200          # 实测：>200 报 errorId 12006
DETAIL_SLEEP = 0.05          # 串行模式逐条间隔
DEFAULT_WORKERS = 8          # 并发取详情的默认线程数
MAX_WORKERS = 16             # 上限（避免触发服务端限流）

# 站点 -> (marketplace, 国家, 邮编)；与 sites.py 的站点码对齐
MARKETPLACE = {
    "us": ("EBAY_US", "US", "10001"),
    "uk": ("EBAY_GB", "GB", "SW1A1AA"),
    "de": ("EBAY_DE", "DE", "10115"),
    "au": ("EBAY_AU", "AU", "2000"),
    "fr": ("EBAY_FR", "FR", "75001"),
    "es": ("EBAY_ES", "ES", "28001"),
    "it": ("EBAY_IT", "IT", "00118"),
    "ca": ("EBAY_CA", "CA", "M5V3L9"),
    "hk": ("EBAY_HK", "HK", "999077"),
}


class EbayApiError(RuntimeError):
    pass


def _load_config():
    for p in CONFIG_CANDIDATES:
        if os.path.isfile(p):
            try:
                return json.load(open(p, encoding="utf-8")), p
            except Exception:
                continue
    return {}, ""


def _api_root(env):
    return "https://api.sandbox.ebay.com" if env == "sandbox" else "https://api.ebay.com"


def merge_categories(summary_leaf, detail_cat_id, category_id_path, category_path):
    """合并两个来源的类目信息（抽成纯函数便于单测）。

    实测来源差异：
      - 搜索 itemSummary.leafCategoryIds 可以有**两个类别**（如 [112529, 80077]），
        是判断"第二类目"的唯一依据
      - 详情 getItem 只有单个 categoryId，以及 categoryIdPath（祖先链 ID，形如 "293|15052|112529"）
        和 categoryPath（祖先链名称，形如 "Sound & Vision|Portable Audio & Headphones|Headphones"）
      - **getItem 不含 leafCategoryIds，也不含 categories**
    踩过的坑：直接用详情的 categoryId 覆盖搜索的 leafCategoryIds，
    会把第二类目丢掉（实测 120 条里第二类目从 3~4 条变成 0 条）。

    返回 (leaf_ids, categories, has_secondary, leaf_name)
    """
    names = [p for p in (category_path or "").split("|") if p]
    ids = [p for p in (category_id_path or "").split("|") if p]
    leaf = [str(x) for x in (summary_leaf or []) if x]
    detail_leaf = str(detail_cat_id or "").strip()
    if not leaf:
        leaf = [detail_leaf] if detail_leaf else ([ids[-1]] if ids else [])
    elif detail_leaf and detail_leaf not in leaf:
        leaf.append(detail_leaf)
    cats = []
    for i in range(max(len(ids), len(names))):
        cid = ids[i] if i < len(ids) else ""
        nm = names[i] if i < len(names) else ""
        if cid or nm:
            cats.append({"id": cid, "name": nm})
    has_secondary = len({x for x in leaf if x}) > 1
    leaf_name = names[-1] if names else (cats[0]["name"] if cats else "")
    return leaf, cats, has_secondary, leaf_name


class EbayApi:
    """官方 Browse API 客户端：搜索 + 详情 + （可选）client_credentials 换 token。"""

    def __init__(self, site="uk", env=None, token=None, timeout=(15, 60), verbose=True):
        cfg, cfg_path = _load_config()
        api_cfg = cfg.get("ebay_api") or {}
        self.cfg, self.cfg_path = cfg, cfg_path
        self.env = (env or api_cfg.get("env") or "production").lower()
        self.root = _api_root(self.env)
        self.timeout = timeout
        self.verbose = verbose
        self.calls = {"search": 0, "getItem": 0, "token": 0}

        if site not in MARKETPLACE:
            raise EbayApiError("未配置站点 %s（可用: %s）" % (site, ", ".join(sorted(MARKETPLACE))))
        self.site = site
        self.marketplace, self.country, self.zip = MARKETPLACE[site]

        self.api_cfg = api_cfg
        # 凭据统一走 ebay_auth：缓存 + 自动续期 + 多来源回退
        self.auth = None
        if token:
            self.token = token.strip()
            self._log("token 来源: 调用方显式传入（长度 %d）" % len(self.token))
        else:
            import ebay_auth
            self.auth = ebay_auth.EbayAuth(env=self.env, cfg=cfg, cfg_path=cfg_path,
                                          verbose=self.verbose)
            try:
                self.token = self.auth.token()
            except Exception as exc:
                raise EbayApiError(str(exc))

    # ---------- 凭据 ----------
    def _renew_token(self, reason=""):
        """401 之后换令牌：让 ebay_auth 跳过刚才被拒的来源，换下一条路。

        换到就返回 True（调用方重试一次），换不到返回 False（照常抛错）。
        多线程同时打到 401 时，EbayAuth 内部有锁，只会续期一次。
        """
        if self.auth is None:
            return False
        old = self.token
        try:
            self.auth.invalidate(reason)
            self.token = self.auth.token(force=True)
        except Exception as exc:
            self._log("自动续期失败：%s" % str(exc)[:160])
            return False
        return self.token != old

    def _token_via_client_credentials(self, cid, sec):
        """保留旧入口（外部脚本可能在用），实际走 ebay_auth。"""
        self.calls["token"] += 1
        r = requests.post(self.root + "/identity/v1/oauth2/token", auth=(cid, sec),
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          data={"grant_type": "client_credentials",
                                "scope": "https://api.ebay.com/oauth/api_scope"},
                          timeout=30)
        if r.status_code != 200:
            raise EbayApiError("client_credentials 换 token 失败 HTTP %s: %s"
                               % (r.status_code, r.text[:200]))
        return r.json().get("access_token") or ""

    # ---------- 基础 ----------
    def _log(self, msg):
        if self.verbose:
            print("  %s" % msg)

    def _headers(self):
        return {
            "Authorization": "Bearer " + self.token,
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%%3D%s%%2Czip%%3D%s"
                                   % (self.country, self.zip),
            "Accept": "application/json",
        }

    def _get(self, path, params=None, what="other"):
        r = requests.get(self.root + path, headers=self._headers(), params=params,
                         timeout=self.timeout)
        # access token 只有 2 小时，跑长任务时会中途过期 —— 自动换一次再试
        if r.status_code == 401 and self._renew_token("HTTP 401"):
            self._log("已换新令牌，重试一次：%s" % path.rsplit("/", 1)[-1])
            r = requests.get(self.root + path, headers=self._headers(), params=params,
                             timeout=self.timeout)
        if r.status_code == 401:
            raise EbayApiError("HTTP 401：token 无效或已过期，且自动续期没成功。"
                               "跑 `python 脚本/ebay_auth.py --check` 看凭据")
        if r.status_code == 403:
            raise EbayApiError("HTTP 403 无权限：%s" % r.text[:200])
        if r.status_code != 200:
            raise EbayApiError("HTTP %s：%s" % (r.status_code, r.text[:250]))
        return r.json()

    # ---------- 业务 ----------
    def search(self, keyword, max_items=200, extra_filters=None):
        """搜索商品，返回 itemSummary 列表（按 max_items 截断）。

        实测：limit 上限 200；offset 必须是 limit 的整数倍。
        """
        out = []
        offset = 0
        per_page = min(API_LIMIT_MAX, max(1, max_items))
        while len(out) < max_items:
            params = {"q": keyword, "limit": per_page, "offset": offset}
            if extra_filters:
                params.update(extra_filters)
            self.calls["search"] += 1
            data = self._get("/buy/browse/v1/item_summary/search", params, "search")
            batch = data.get("itemSummaries") or []
            total = data.get("total")
            self._log("搜索 offset=%d 返回 %d 条（站点内总匹配 %s）" % (offset, len(batch), total))
            if not batch:
                break
            out.extend(batch)
            if not data.get("next") or len(out) >= max_items:
                break
            offset += per_page
            time.sleep(0.2)
        return out[:max_items]

    def get_item(self, item_id, session=None):
        """取单条详情。session 让并发时每线程复用各自连接（避免共享连接池竞争）。"""
        self.calls["getItem"] += 1
        s = session or requests
        url = self.root + "/buy/browse/v1/item/" + quote(item_id, safe="")
        r = s.get(url, headers=self._headers(), timeout=self.timeout)
        # 并发跑到一半令牌过期：换一次再试，避免整批 200 条里后面全失败
        if r.status_code == 401 and self._renew_token("HTTP 401 (getItem)"):
            r = s.get(url, headers=self._headers(), timeout=self.timeout)
        if r.status_code == 401:
            raise EbayApiError("HTTP 401：token 无效或已过期，且自动续期没成功。"
                               "跑 `python 脚本/ebay_auth.py --check` 看凭据")
        if r.status_code == 403:
            raise EbayApiError("HTTP 403 无权限：%s" % r.text[:200])
        if r.status_code != 200:
            raise EbayApiError("HTTP %s：%s" % (r.status_code, r.text[:250]))
        return r.json()

    # ---------- 并发取详情 ----------
    def _detail_worker(self, idx_item):
        """线程工作单元：返回 (下标, 补好详情的 item 或 None)。"""
        i, item, summary = idx_item
        # 每线程一个 session（连接复用 + 线程安全）
        local = getattr(self._tls, "session", None)
        if local is None:
            local = requests.Session()
            self._tls.session = local
        try:
            d = self.get_item(item["item_id"], session=local)
        except EbayApiError as exc:
            item["detail_error"] = str(exc)[:160]
            return i, None, str(exc)[:100]
        return i, self._apply_detail(item, summary, d), None

    def _apply_detail(self, item, summary, d):
        """把 getItem 的返回合进 item（纯数据变换，便于单测）。"""
        asp = d.get("localizedAspects") or []
        item["item_specifics"] = [{"name": (a.get("name") or "").strip(),
                                   "value": str(a.get("value") or "").strip()}
                                  for a in asp if a.get("name") and a.get("value")]
        leaf, cats, has_secondary, leaf_name = merge_categories(
            [str(x) for x in (summary.get("leafCategoryIds") or []) if x],
            d.get("categoryId"), d.get("categoryIdPath"), d.get("categoryPath"))
        item["leaf_category_ids"] = leaf
        item["categories"] = cats
        item["has_secondary_category"] = has_secondary
        item["leaf_category_name"] = leaf_name
        names = [p for p in (d.get("categoryPath") or "").split("|") if p]
        item["category_path"] = " > ".join(names)
        item["breadcrumb"] = names
        item["description"] = d.get("description") or ""
        item["description_len"] = len(item["description"])
        item["short_description"] = d.get("shortDescription") or item.get("short_description") or ""
        imgs = [((d.get("image") or {}).get("imageUrl") or "")]
        imgs += [((x or {}).get("imageUrl") or "") for x in (d.get("additionalImages") or [])]
        imgs = [u for u in imgs if u]
        if imgs:
            item["image_url"] = imgs[0]
            item["images"] = imgs
            item["image_count"] = len(imgs)
        if d.get("brand"):
            item["brand_field"] = d["brand"]
        if d.get("color"):
            item["color_field"] = d["color"]
        if d.get("condition"):
            item["condition"] = d["condition"]
        if d.get("itemLocation"):
            loc = d["itemLocation"]
            item["item_location"] = loc.get("country") or item.get("item_location") or ""
            item["item_location_full"] = "%s / %s / %s" % (
                loc.get("city") or "", loc.get("postalCode") or "", loc.get("country") or "")
        item["detail_ok"] = True
        return item

    def collect(self, keyword, max_items=200, detail=True, workers=DEFAULT_WORKERS):
        """搜索 + （可选）取详情，输出与既有分析段兼容的结构。

        max_items 默认 **200** = eBay Browse API 单页上限：limit 最大就是 200，
        所以默认值下 **1 次 search 就够**（不需要翻页）。
        >200 时会自动翻页（offset 必须是 limit 的整数倍）。

        workers>1 时用线程池并发取详情（每线程独立 session）；
        workers<=1 时串行（保留退路，便于排查限流）。
        """
        t0 = time.time()
        summaries = self.search(keyword, max_items)
        self._log("搜索完成：%d 条" % len(summaries))
        items = [self._map_summary(s, i + 1) for i, s in enumerate(summaries)]
        if detail and items:
            workers = max(1, min(int(workers or 1), MAX_WORKERS))
            n = len(items)
            if workers > 1:
                self._log("并发取详情：%d 条 × %d 线程（串行实测约 %.1f 分钟）"
                          % (n, workers, n * 1.24 / 60))
                from concurrent.futures import ThreadPoolExecutor, as_completed
                self._tls = threading.local()
                done = 0
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = [pool.submit(self._detail_worker, (i, items[i], summaries[i]))
                            for i in range(n)]
                    for fut in as_completed(futs):
                        i, res, err = fut.result()
                        if res is not None:
                            items[i] = res
                        done += 1
                        if done % 20 == 0:
                            self._log("  详情 %d/%d" % (done, n))
            else:
                self._log("串行取详情：%d 条" % n)
                for i in range(n):
                    _i, res, _e = self._detail_worker((i, items[i], summaries[i]))
                    if res is not None:
                        items[i] = res
                    time.sleep(DETAIL_SLEEP)
        failed = [x["item_id"] for x in items if x.get("detail_error")]
        if failed:
            self._log("详情失败 %d 条: %s" % (len(failed), failed[:5]))
        self._log("完成，总耗时 %.1f 秒；调用统计 %s" % (time.time() - t0, self.calls))
        return {"items": items, "dominant_category_id": "", "aspect_refinements": [],
                "api_calls": dict(self.calls),
                "elapsed_sec": round(time.time() - t0, 1)}

    # ---------- 字段映射 ----------
    @staticmethod
    def _money(obj):
        if not obj:
            return None, ""
        try:
            return float(obj.get("value")), (obj.get("currency") or "")
        except (TypeError, ValueError):
            return None, (obj.get("currency") or "")

    def _map_summary(self, s, position):
        price, cur = self._money(s.get("price"))
        cats = [{"id": str(c.get("categoryId") or ""), "name": c.get("categoryName") or ""}
                for c in (s.get("categories") or [])]
        # 搜索侧的 leafCategoryIds 可能有两个 → 先原样保留（_enrich 会与详情合并）
        leaf = [str(x) for x in (s.get("leafCategoryIds") or []) if x]
        if not leaf:
            leaf = [c["id"] for c in cats[:1] if c["id"]]
        legacy = s.get("legacyItemId") or ""
        seller = s.get("seller") or {}
        return {
            "position": position,
            "item_id": s.get("itemId") or "",
            "legacy_item_id": str(legacy),
            "variant_id": "",
            "title": s.get("title") or "",
            "price": price,
            "price_max": price,
            "price_is_range": False,
            "currency": cur,
            "price_display": ("%s%s" % (cur, price)) if price is not None else "",
            "condition": s.get("condition") or "",
            "is_sponsored": bool(s.get("priorityListing")),
            "promoted_source": "api",
            "item_url": s.get("itemWebUrl") or "",
            "image_url": ((s.get("image") or {}).get("imageUrl") or ""),
            "image_count": len(s.get("additionalImages") or []) + (1 if s.get("image") else 0),
            "leaf_category_ids": leaf,
            "categories": cats,
            "has_secondary_category": len(set(leaf)) > 1,
            "search_rank": position - 1,
            "item_specifics": [],
            "seller": seller.get("username") or "",
            "short_description": s.get("shortDescription") or "",
            "item_location": (s.get("itemLocation") or {}).get("country") or "",
            "listing_marketplace": s.get("listingMarketplaceId") or "",
            "source": "ebay_api",
        }

def fetch(keyword, site="uk", max_items=200, detail=True, env=None, verbose=True):
    """便捷入口：与 collect_api.collect 同签名，供 run_keyword_research 调用。"""
    api = EbayApi(site=site, env=env, verbose=verbose)
    return api.collect(keyword, max_items=max_items, detail=detail)
