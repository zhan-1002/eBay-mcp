import json
from pathlib import Path

import pytest

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.providers.purchase_history import (
    PersistentPurchaseHistoryBrowser,
    PurchaseHistoryProvider,
    manual_intervention_code,
    normalize_legacy_item_ids,
    normalize_purchase_table,
)


def settings() -> Settings:
    return Settings(
        environment="production",
        client_id="",
        client_secret="",
        user_access_token="",
        request_timeout=30,
        max_retries=2,
        retry_base_delay=0,
        sales_provider="purchase_history",
        sales_profile_dir=".test-profile",
        sales_min_delay=0,
        sales_challenge_grace_seconds=0,
    )


def test_normalize_purchase_table_with_variations_and_uk_dates():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "purchase_history_uk.json").read_text(
            encoding="utf-8"
        )
    )
    result = normalize_purchase_table(
        fixture["headers"],
        fixture["rows"],
        "EBAY_GB",
        limit=100,
    )

    assert result["summary"] == {
        "visible_transaction_count": 2,
        "visible_quantity": 3,
        "minimum_observed_price": 10.0,
        "maximum_observed_price": 12.5,
        "currency": "GBP",
    }
    assert result["transactions"][0]["variation"] == "Colour: Blue"
    assert result["transactions"][0]["purchased_at"] == "2026-09-27T15:24:07"
    assert result["transactions"][0]["timezone"] == "BST"
    assert result["coverage"]["complete_history"] is False
    assert result["coverage"]["available_rows_on_page"] == 2


def test_normalize_purchase_table_honours_limit_and_missing_values():
    result = normalize_purchase_table(
        ["Buyer", "Price", "Qty", "Date"],
        [
            ["a***b", "US $4.99", "1", "Sep 27, 2026 at 08:30"],
            ["c***d", "US $5.99", "3", "Sep 26, 2026 at 08:30"],
        ],
        "EBAY_US",
        limit=1,
    )

    assert len(result["transactions"]) == 1
    assert result["summary"]["visible_quantity"] == 1
    assert result["coverage"]["available_rows_on_page"] == 2


def test_legacy_item_ids_are_deduplicated_and_rest_ids_are_rejected():
    assert normalize_legacy_item_ids(
        ["314126742195", "314126742195", " 385543168522 "]
    ) == ["314126742195", "385543168522"]

    with pytest.raises(EbayMcpError) as caught:
        normalize_legacy_item_ids(["v1|314126742195|0"])
    assert caught.value.code == "INVALID_LEGACY_ITEM_ID"


class FakeBrowser:
    def __init__(self, responses):
        self.responses = iter(responses)

    async def fetch(self, item_id, marketplace_id, *, limit, allow_window=False):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return {"legacy_item_id": item_id, "status": "ok", **response}

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_provider_preserves_successes_and_stops_after_session_failure():
    provider = PurchaseHistoryProvider(settings())
    provider.browser = FakeBrowser(
        [
            {"transactions": [], "summary": {}},
            EbayMcpError("SALES_LOGIN_REQUIRED", "Login required."),
        ]
    )

    result = await provider.search(
        ["314126742195", "385543168522", "123456789012"],
        "EBAY_GB",
        limit=100,
    )

    assert result["succeeded_count"] == 1
    assert result["failed_count"] == 2
    assert result["partial"] is True
    assert result["failures"][0]["error"]["code"] == "SALES_LOGIN_REQUIRED"
    assert result["failures"][1]["status"] == "skipped"


@pytest.mark.asyncio
async def test_provider_raises_session_failure_when_nothing_was_collected():
    provider = PurchaseHistoryProvider(settings())
    provider.browser = FakeBrowser(
        [EbayMcpError("SALES_CHALLENGE_DETECTED", "Challenge.")]
    )

    with pytest.raises(EbayMcpError) as caught:
        await provider.search(["314126742195"], "EBAY_GB", limit=100)
    assert caught.value.code == "SALES_CHALLENGE_DETECTED"


class FakeResponse:
    def __init__(self):
        self.status = 200
        self.headers = {"content-type": "text/html; charset=utf-8"}


class FakePage:
    def __init__(self, url: str):
        self.url = url
        self.goto_calls: list[str] = []

    def on(self, event, callback):
        return None

    def remove_listener(self, event, callback):
        return None

    async def goto(self, url, *, wait_until):
        self.goto_calls.append(url)
        self.url = url
        return FakeResponse()

    async def wait_for_timeout(self, timeout):
        return None

    async def title(self):
        return "eBay Sign In"

    async def evaluate(self, script, argument=None):
        return {
            "status": 200,
            "contentType": "text/html; charset=utf-8",
            "bodyCharacterCount": 12345,
            "title": "Item Purchase History",
            "url": argument["url"] if argument else self.url,
            "bodyText": "Item Purchase History",
            "headers": ["User ID", "Buy It Now price", "Quantity", "Date of purchase"],
            "rows": [["a***b", "£12.50", "2", "7 Oct 2026 at 6:03:10pm BST"]],
            "tableScore": 4,
        }


@pytest.mark.asyncio
async def test_browser_uses_in_page_fetch_when_origin_is_ready():
    browser = PersistentPurchaseHistoryBrowser(settings())
    browser._context = object()
    browser._page = FakePage("https://www.ebay.co.uk/")

    result = await browser.fetch("314126742195", "EBAY_GB", limit=100)

    assert result["transport"] == "browser_in_page_fetch"
    assert result["summary"]["visible_quantity"] == 2
    assert result["transactions"][0]["purchased_at"] == "2026-10-07T18:03:10"
    assert browser._page.goto_calls == []


@pytest.mark.asyncio
async def test_browser_bootstraps_first_item_with_navigation():
    browser = PersistentPurchaseHistoryBrowser(settings())
    browser._context = object()
    browser._page = FakePage("about:blank")

    result = await browser.fetch("314126742195", "EBAY_GB", limit=100)

    assert result["transport"] == "browser_navigation_bootstrap"
    assert browser._page.goto_calls == [
        "https://www.ebay.co.uk/bin/purchaseHistory?item=314126742195"
    ]


@pytest.mark.asyncio
async def test_open_login_keeps_the_owned_browser_running():
    browser = PersistentPurchaseHistoryBrowser(settings())
    context = object()
    browser._context = context
    browser._page = FakePage("about:blank")

    async def signed_in():
        browser._page.url = "https://www.ebay.co.uk/"
        return True

    browser._wait_until_unblocked = signed_in

    result = await browser.open_login("EBAY_GB", item_id="314126742195")

    assert browser._context is context
    assert result["browser_running"] is True
    assert result["browser_closed"] is False
    assert result["session_state"] == "parked"
    assert result["parked_item_id"] == "314126742195"
    assert browser._page.goto_calls == [
        "https://signin.ebay.co.uk/ws/eBayISAPI.dll?SignIn",
        "https://www.ebay.co.uk/bin/purchaseHistory?item=314126742195",
    ]


@pytest.mark.asyncio
async def test_sales_search_checks_the_parked_browser_before_collecting():
    provider = PurchaseHistoryProvider(settings())

    class ClosedBrowser:
        async def inspect(self):
            return {
                "browser_running": False,
                "intervention": None,
                "human_verification_selector": None,
            }

        async def fetch(self, *args, **kwargs):
            raise AssertionError("collection must not start")

    provider.browser = ClosedBrowser()

    with pytest.raises(EbayMcpError) as caught:
        await provider.search(["314126742195"], "EBAY_GB", limit=100)

    assert caught.value.code == "SALES_BROWSER_NOT_PARKED"


def test_manual_intervention_codes_cover_login_and_verification():
    assert (
        manual_intervention_code("https://www.ebay.co.uk/splashui/challenge")
        == "SALES_CHALLENGE_DETECTED"
    )
    assert (
        manual_intervention_code(
            "https://signin.ebay.co.uk/ws/eBayISAPI.dll",
            "Sign in",
        )
        == "SALES_LOGIN_REQUIRED"
    )
    assert manual_intervention_code("https://www.ebay.co.uk/") is None


class SequencePage(FakePage):
    def __init__(self, payloads):
        super().__init__("https://www.ebay.co.uk/")
        self.payloads = list(payloads)

    async def evaluate(self, script, argument=None):
        return self.payloads.pop(0)


def _challenge_payload():
    return {
        "status": 200,
        "contentType": "text/html",
        "bodyCharacterCount": 100,
        "title": "Pardon Our Interruption",
        "url": "https://www.ebay.co.uk/splashui/challenge",
        "bodyText": "Checking your browser",
        "humanVerificationSelector": "",
        "headers": [],
        "rows": [],
        "tableScore": 0,
    }


def _widget_payload():
    payload = _challenge_payload()
    payload["humanVerificationSelector"] = "#px-captcha"
    return payload


def _success_payload():
    return {
        "status": 200,
        "contentType": "text/html; charset=utf-8",
        "bodyCharacterCount": 12345,
        "title": "Item Purchase History",
        "url": "https://www.ebay.co.uk/bin/purchaseHistory?item=314126742195",
        "bodyText": "Item Purchase History",
        "headers": ["User ID", "Buy It Now price", "Quantity", "Date of purchase"],
        "rows": [["a***b", "£12.50", "2", "7 Oct 2026 at 6:03:10pm BST"]],
        "tableScore": 4,
    }


@pytest.mark.asyncio
async def test_fetch_retries_a_check_without_showing_the_window():
    browser = PersistentPurchaseHistoryBrowser(settings())
    browser._context = object()
    browser._page = SequencePage([_challenge_payload(), _success_payload()])
    events = []

    async def recover(url, code):
        events.append(("recover", code, url))

    async def minimize():
        events.append("minimize")

    browser._await_manual_recovery = recover
    browser._minimize_window = minimize

    result = await browser.fetch("314126742195", "EBAY_GB", limit=100)

    assert result["silent_grace_retry"] is True
    assert "manual_recovery" not in result
    assert result["summary"]["visible_quantity"] == 2
    assert "recover" not in events


@pytest.mark.asyncio
async def test_fetch_asks_before_showing_a_window():
    browser = PersistentPurchaseHistoryBrowser(settings())
    browser._context = object()
    browser._page = SequencePage([_challenge_payload(), _challenge_payload()])
    events = []

    async def recover(url, code):
        events.append("recover")

    async def present():
        events.append("present")

    browser._await_manual_recovery = recover
    browser._present_window = present

    with pytest.raises(EbayMcpError) as caught:
        await browser.fetch("314126742195", "EBAY_GB", limit=100)

    assert caught.value.code == "SALES_CHECK_UNRESOLVED"
    assert events == []


@pytest.mark.asyncio
async def test_visible_verification_widget_asks_before_showing_window():
    browser = PersistentPurchaseHistoryBrowser(settings())
    browser._context = object()
    browser._page = SequencePage([_challenge_payload(), _widget_payload()])
    events = []

    async def present():
        events.append("present")

    browser._present_window = present

    with pytest.raises(EbayMcpError) as caught:
        await browser.fetch("314126742195", "EBAY_GB", limit=100)

    assert caught.value.code == "SALES_WINDOW_CONFIRMATION_REQUIRED"
    assert caught.value.details["human_verification_selector"] == "#px-captcha"
    assert events == []


@pytest.mark.asyncio
async def test_fetch_shows_window_only_after_permission():
    browser = PersistentPurchaseHistoryBrowser(settings())
    browser._context = object()
    browser._page = SequencePage(
        [_challenge_payload(), _widget_payload(), _success_payload()]
    )
    events = []

    async def recover(url, code):
        events.append(code)

    browser._await_manual_recovery = recover

    result = await browser.fetch(
        "314126742195",
        "EBAY_GB",
        limit=100,
        allow_window=True,
    )

    assert events == ["SALES_CHALLENGE_DETECTED"]
    assert result["manual_recovery"] == "SALES_CHALLENGE_DETECTED"


@pytest.mark.asyncio
async def test_provider_stops_batch_after_manual_recovery_timeout():
    provider = PurchaseHistoryProvider(settings())
    provider.browser = FakeBrowser(
        [
            {"transactions": [], "summary": {}},
            EbayMcpError("SALES_MANUAL_RECOVERY_TIMEOUT", "Timed out."),
        ]
    )

    result = await provider.search(
        ["314126742195", "385543168522", "123456789012"],
        "EBAY_GB",
        limit=100,
    )

    assert result["succeeded_count"] == 1
    assert result["failures"][0]["error"]["code"] == "SALES_MANUAL_RECOVERY_TIMEOUT"
    assert result["failures"][1]["status"] == "skipped"
