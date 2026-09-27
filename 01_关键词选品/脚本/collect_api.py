# -*- coding: utf-8 -*-
"""官方 Browse API：按站点设配送地，搜 120 条，再拉前 10 条 specifics。"""

import time
from urllib.parse import quote

import requests

from config_load import ebay_api_creds
from sites import get_site

SCOPE = "https://api.ebay.com/oauth/api_scope"
HOSTS = {
    "sandbox": "https://api.sandbox.ebay.com",
    "production": "https://api.ebay.com",
}


def _host(environment):
    return HOSTS.get(environment) or HOSTS["sandbox"]


def _token(environment=None):
    creds = ebay_api_creds(environment)
    env = creds["environment"]
    url = _host(env) + "/identity/v1/oauth2/token"
    r = requests.post(
        url,
        auth=(creds["client_id"], creds["client_secret"]),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError("换 token 失败 HTTP %s（%s）: %s" % (r.status_code, env, r.text[:400]))
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("换 token 失败: %s" % data)
    return token, env


def _headers(token, site_cfg):
    loc = "country=%s,zip=%s" % (site_cfg["country"], site_cfg["zip"])
    return {
        "Authorization": "Bearer " + token,
        "X-EBAY-C-MARKETPLACE-ID": site_cfg["marketplace_id"],
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + quote(loc, safe=""),
    }


def _money(obj):
    if not obj:
        return None, ""
    try:
        return float(obj.get("value")), obj.get("currency") or ""
    except (TypeError, ValueError):
        return None, obj.get("currency") or ""


def _map_summary(it, position):
    price, currency = _money(it.get("price"))
    cats = []
    for c in it.get("categories") or []:
        cats.append({"id": str(c.get("categoryId") or ""), "name": c.get("categoryName") or ""})
    leaf = [str(x) for x in (it.get("leafCategoryIds") or []) if x]
    if not leaf:
        leaf = [c["id"] for c in cats if c["id"]]
    return {
        "position": position,
        "item_id": it.get("itemId") or "",
        "legacy_item_id": it.get("legacyItemId") or "",
        "title": it.get("title") or "",
        "price": price,
        "currency": currency,
        "condition": it.get("condition") or "",
        "is_sponsored": bool(it.get("priorityListing")),
        "item_url": it.get("itemWebUrl") or "",
        "leaf_category_ids": leaf,
        "categories": cats,
        "has_secondary_category": len(leaf) > 1,
        "item_specifics": [],
        "source": "api",
    }


def _map_specifics(detail):
    rows = []
    for asp in detail.get("localizedAspects") or []:
        name = (asp.get("name") or asp.get("type") or "").strip()
        value = asp.get("value")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v)
        value = (value or "").strip()
        if name and value:
            rows.append({"name": name, "value": value})
    return rows


def collect(keyword, site_code, max_items=200, detail_n=10, environment=None):
    site_cfg = get_site(site_code)
    token, env = _token(environment)
    host = _host(env)
    headers = _headers(token, site_cfg)
    params = {
        "q": keyword,
        "limit": min(max(1, max_items), 200),
        "filter": "deliveryCountry:%s" % site_cfg["country"],
        "fieldgroups": "EXTENDED,ASPECT_REFINEMENTS,CATEGORY_REFINEMENTS",
    }
    print("  API [%s] 搜索: %s / %s / 配送 %s %s" % (
        env, keyword, site_cfg["marketplace_id"], site_cfg["country"], site_cfg["zip"]))
    r = requests.get(host + "/buy/browse/v1/item_summary/search",
                     headers=headers, params=params, timeout=45)
    if r.status_code != 200:
        raise RuntimeError("搜索失败 HTTP %s: %s" % (r.status_code, r.text[:400]))
    payload = r.json()
    summaries = payload.get("itemSummaries") or []
    items = []
    for i, it in enumerate(summaries[:max_items], 1):
        items.append(_map_summary(it, i))

    refine_aspects = []
    for dist in ((payload.get("refinement") or {}).get("aspectDistributions") or []):
        name = dist.get("localizedAspectName") or ""
        for v in dist.get("aspectValueDistributions") or []:
            refine_aspects.append({
                "name": name,
                "value": v.get("localizedAspectValue") or "",
                "match_count": v.get("matchCount"),
            })

    for it in items[:detail_n]:
        item_id = it.get("item_id")
        if not item_id:
            continue
        url = host + "/buy/browse/v1/item/" + quote(item_id, safe="")
        try:
            dr = requests.get(url, headers=headers, timeout=30)
            if dr.status_code != 200:
                print("  getItem 失败 %s HTTP %s" % (item_id, dr.status_code))
                continue
            detail = dr.json()
            it["item_specifics"] = _map_specifics(detail)
            leaf = [str(x) for x in (detail.get("categoryPathIds", "").split("|") if isinstance(detail.get("categoryPathIds"), str) else []) if x]
            if detail.get("categoryId"):
                cid = str(detail.get("categoryId"))
                if cid not in it["leaf_category_ids"]:
                    it["leaf_category_ids"] = [cid] + it["leaf_category_ids"]
            if leaf:
                it["leaf_category_ids"] = list(dict.fromkeys(it["leaf_category_ids"] + [leaf[-1]]))
            time.sleep(0.15)
        except Exception as e:
            print("  getItem 异常 %s: %s" % (item_id, e))

    dominant = (payload.get("refinement") or {}).get("dominantCategoryId") or ""
    return {
        "items": items,
        "dominant_category_id": str(dominant) if dominant else "",
        "aspect_refinements": refine_aspects,
    }
