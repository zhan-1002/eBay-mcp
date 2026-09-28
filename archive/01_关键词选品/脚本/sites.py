# -*- coding: utf-8 -*-
"""站点 ↔ 搜索域名 / 配送国家 / 邮编 / Browse marketplace。

配送地必须跟站点走，不能跟本机出口 IP，否则结果会偏到香港。
"""

SITES = {
    "us": {
        "host": "https://www.ebay.com",
        "marketplace_id": "EBAY_US",
        "country": "US",
        "country_id": "1",
        "zip": "10001",
        "ship_labels": ("Ship to", "Deliver to", "Shipping to"),
        "country_labels": ("United States", "USA"),
    },
    "uk": {
        "host": "https://www.ebay.co.uk",
        "marketplace_id": "EBAY_GB",
        "country": "GB",
        "country_id": "3",
        "zip": "SW1A1AA",
        "ship_labels": ("Ship to", "Deliver to"),
        "country_labels": ("United Kingdom", "UK"),
    },
    "de": {
        "host": "https://www.ebay.de",
        "marketplace_id": "EBAY_DE",
        "country": "DE",
        "country_id": "77",
        "zip": "10115",
        "ship_labels": ("Liefern nach", "Versand nach", "Ship to"),
        "country_labels": ("Deutschland", "Germany"),
    },
    "au": {
        "host": "https://www.ebay.com.au",
        "marketplace_id": "EBAY_AU",
        "country": "AU",
        "country_id": "15",
        "zip": "2000",
        "ship_labels": ("Ship to", "Deliver to"),
        "country_labels": ("Australia",),
    },
    "fr": {
        "host": "https://www.ebay.fr",
        "marketplace_id": "EBAY_FR",
        "country": "FR",
        "country_id": "71",
        "zip": "75001",
        "ship_labels": ("Livrer", "Ship to"),
        "country_labels": ("France",),
    },
    "es": {
        "host": "https://www.ebay.es",
        "marketplace_id": "EBAY_ES",
        "country": "ES",
        "country_id": "186",
        "zip": "28001",
        "ship_labels": ("Enviar a", "Ship to"),
        "country_labels": ("España", "Spain"),
    },
    "it": {
        "host": "https://www.ebay.it",
        "marketplace_id": "EBAY_IT",
        "country": "IT",
        "country_id": "101",
        "zip": "00118",
        "ship_labels": ("Spedisci a", "Ship to"),
        "country_labels": ("Italia", "Italy"),
    },
    "ca": {
        "host": "https://www.ebay.ca",
        "marketplace_id": "EBAY_CA",
        "country": "CA",
        "country_id": "2",
        "zip": "M5V3L9",
        "ship_labels": ("Ship to", "Deliver to"),
        "country_labels": ("Canada",),
    },
    "hk": {
        "host": "https://www.ebay.com.hk",
        "marketplace_id": "EBAY_HK",
        "country": "HK",
        "country_id": "107",
        "zip": "999077",
        "ship_labels": ("Ship to", "Deliver to"),
        "country_labels": ("Hong Kong",),
    },
}


def get_site(code):
    key = (code or "").strip().lower()
    if key not in SITES:
        raise ValueError("未知站点 %s（可用: %s）" % (code, ", ".join(sorted(SITES))))
    return SITES[key]


def search_url(code, keyword, page=1, per_page=240):
    from urllib.parse import quote_plus

    site = get_site(code)
    return (
        "%s/sch/i.html?_nkw=%s&_ipg=%d&_pgn=%d&_stpos=%s&_fcid=%s&rt=nc"
        % (site["host"], quote_plus(keyword), per_page, page, site["zip"], site["country_id"])
    )
