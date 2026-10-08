"""Logged-in eBay purchase-history provider backed by a persistent browser."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.providers.sales import SalesHistoryProvider

logger = logging.getLogger("ebay_mcp.purchase_history")

MARKETPLACE_HOSTS = {
    "EBAY_US": "www.ebay.com",
    "EBAY_GB": "www.ebay.co.uk",
    "EBAY_DE": "www.ebay.de",
    "EBAY_AU": "www.ebay.com.au",
    "EBAY_FR": "www.ebay.fr",
    "EBAY_ES": "www.ebay.es",
    "EBAY_IT": "www.ebay.it",
    "EBAY_CA": "www.ebay.ca",
    "EBAY_HK": "www.ebay.com.hk",
}

MARKETPLACE_CURRENCIES = {
    "EBAY_US": "USD",
    "EBAY_GB": "GBP",
    "EBAY_DE": "EUR",
    "EBAY_AU": "AUD",
    "EBAY_FR": "EUR",
    "EBAY_ES": "EUR",
    "EBAY_IT": "EUR",
    "EBAY_CA": "CAD",
    "EBAY_HK": "HKD",
}

FATAL_SESSION_CODES = {
    "SALES_BROWSER_DEPENDENCY_MISSING",
    "SALES_BROWSER_PROFILE_NOT_CONFIGURED",
    "SALES_BROWSER_PROFILE_LOCKED",
    "SALES_BROWSER_START_FAILED",
    "SALES_LOGIN_REQUIRED",
    "SALES_CHALLENGE_DETECTED",
    "SALES_MANUAL_RECOVERY_TIMEOUT",
    "SALES_WINDOW_CONFIRMATION_REQUIRED",
    "SALES_CHECK_UNRESOLVED",
    "SALES_PAGE_SCHEMA_CHANGED",
}

_ITEM_ID = re.compile(r"^\d{9,15}$")
_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"[-+]?\d[\d,.]*")


def human_verification_selector(extracted: dict[str, Any]) -> str:
    """Return the captcha widget selector present in a fetched document."""

    return str(extracted.get("humanVerificationSelector") or "")


def manual_intervention_code(url: str, title: str = "", body: str = "") -> str | None:
    """Return the session error that requires a person, without treating it as final."""

    lowered = f"{url}\n{title}\n{body}".casefold()
    if (
        "splashui/challenge" in url.casefold()
        or "checking your browser" in lowered
        or "pardon our interruption" in lowered
    ):
        return "SALES_CHALLENGE_DETECTED"
    if "signin" in url.casefold() or "sign in to your account" in lowered:
        return "SALES_LOGIN_REQUIRED"
    return None


def normalize_legacy_item_ids(item_ids: list[str] | str) -> list[str]:
    values = [item_ids] if isinstance(item_ids, str) else list(item_ids or [])
    normalized: list[str] = []
    invalid: list[str] = []
    for value in values:
        item_id = str(value).strip()
        if not _ITEM_ID.fullmatch(item_id):
            invalid.append(item_id)
        elif item_id not in normalized:
            normalized.append(item_id)
    if invalid:
        raise EbayMcpError(
            "INVALID_LEGACY_ITEM_ID",
            "Purchase history requires numeric legacy item IDs.",
            details={"invalid": invalid, "expected": "9 to 15 digits"},
        )
    if not normalized:
        raise EbayMcpError(
            "MISSING_LEGACY_ITEM_ID",
            "At least one legacy item ID is required.",
        )
    if len(normalized) > 50:
        raise EbayMcpError(
            "TOO_MANY_ITEM_IDS",
            "A single purchase-history call accepts at most 50 item IDs.",
            details={"requested": len(normalized), "maximum": 50},
        )
    return normalized


def _header_key(value: str) -> str:
    text = _SPACE.sub(" ", value).strip().casefold()
    if "variation" in text or "specific" in text:
        return "variation"
    if "price" in text:
        return "price"
    if "quantity" in text or text in {"qty", "qty."}:
        return "quantity"
    if "date" in text or "purchased" in text:
        return "date"
    if "user" in text or "buyer" in text or "bidder" in text:
        return "buyer"
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "unknown"


def _parse_quantity(value: str) -> int | None:
    match = re.search(r"\d+", value.replace(",", ""))
    return int(match.group()) if match else None


def _parse_price(value: str, fallback_currency: str) -> tuple[float | None, str]:
    currency = fallback_currency
    upper = value.upper()
    if "£" in value or "GBP" in upper:
        currency = "GBP"
    elif "€" in value or "EUR" in upper:
        currency = "EUR"
    elif "C$" in upper or "CAD" in upper:
        currency = "CAD"
    elif "AU$" in upper or "AUD" in upper:
        currency = "AUD"
    elif "HK$" in upper or "HKD" in upper:
        currency = "HKD"
    elif "$" in value or "USD" in upper:
        currency = "USD"

    match = _NUMBER.search(value.replace("\xa0", " "))
    if not match:
        return None, currency
    raw = match.group().replace(",", "")
    try:
        return float(Decimal(raw)), currency
    except InvalidOperation:
        return None, currency


def _parse_purchase_time(value: str) -> tuple[str | None, str | None]:
    text = _SPACE.sub(" ", value).strip()
    timezone_match = re.search(r"\b([A-Z]{2,5})$", text)
    timezone_name = timezone_match.group(1) if timezone_match else None
    without_timezone = (
        text[: timezone_match.start()].strip() if timezone_match else text
    )
    formats = (
        "%d %b %Y at %H:%M:%S",
        "%d %b %Y at %H:%M",
        "%d %b %Y at %I:%M:%S%p",
        "%d %b %Y at %I:%M%p",
        "%b %d, %Y at %H:%M:%S",
        "%b %d, %Y at %H:%M",
        "%b %d, %Y at %I:%M:%S%p",
        "%b %d, %Y at %I:%M%p",
        "%d %b %Y",
        "%b %d, %Y",
    )
    for date_format in formats:
        try:
            # eBay supplies a local clock time and timezone abbreviation separately.
            parsed = datetime.strptime(without_timezone, date_format)  # noqa: DTZ007
            return parsed.isoformat(), timezone_name
        except ValueError:
            continue
    return None, timezone_name


def normalize_purchase_table(
    headers: list[str],
    rows: list[list[str]],
    marketplace_id: str,
    *,
    limit: int,
) -> dict[str, Any]:
    """Normalize DOM table cells without depending on live eBay markup in tests."""

    keys = [_header_key(value) for value in headers]
    fallback_currency = MARKETPLACE_CURRENCIES.get(marketplace_id, "")
    transactions: list[dict[str, Any]] = []

    for row in rows[:limit]:
        values = [_SPACE.sub(" ", str(value)).strip() for value in row]
        record = {
            keys[index]: values[index]
            for index in range(min(len(keys), len(values)))
            if values[index]
        }
        if not record:
            continue
        quantity = _parse_quantity(record.get("quantity", ""))
        price, currency = _parse_price(record.get("price", ""), fallback_currency)
        purchased_at, timezone_name = _parse_purchase_time(record.get("date", ""))
        transactions.append(
            {
                "buyer_masked": record.get("buyer"),
                "variation": record.get("variation"),
                "price": price,
                "currency": currency or None,
                "price_text": record.get("price"),
                "quantity": quantity,
                "purchased_at": purchased_at,
                "timezone": timezone_name,
                "purchased_at_text": record.get("date"),
            }
        )

    quantities = [
        transaction["quantity"]
        for transaction in transactions
        if transaction["quantity"] is not None
    ]
    prices = [
        transaction["price"]
        for transaction in transactions
        if transaction["price"] is not None
    ]
    dates = sorted(
        transaction["purchased_at"]
        for transaction in transactions
        if transaction["purchased_at"] is not None
    )
    return {
        "transactions": transactions,
        "summary": {
            "visible_transaction_count": len(transactions),
            "visible_quantity": sum(quantities),
            "minimum_observed_price": min(prices) if prices else None,
            "maximum_observed_price": max(prices) if prices else None,
            "currency": next(
                (
                    transaction["currency"]
                    for transaction in transactions
                    if transaction["currency"]
                ),
                fallback_currency or None,
            ),
        },
        "coverage": {
            "earliest_visible_purchase": dates[0] if dates else None,
            "latest_visible_purchase": dates[-1] if dates else None,
            "returned_records": len(transactions),
            "available_rows_on_page": len(rows),
            "record_limit": limit,
            "complete_history": False,
        },
    }


_VERIFICATION_WIDGET_SNIPPET = """
  const verificationSelector = (root) => {
    const selectors = [
      'iframe[src*="hcaptcha"]',
      'iframe[src*="recaptcha"]',
      'iframe[src*="captcha"]',
      'iframe[title*="captcha" i]',
      ".h-captcha",
      ".g-recaptcha",
      "#px-captcha",
      ".px-captcha-container",
      "[data-hcaptcha-widget-id]",
    ];
    for (const selector of selectors) {
      if (root.querySelector(selector)) return selector;
    }
    return "";
  };
"""

_FETCH_AND_EXTRACT_SCRIPT = (
    """
async ({url, timeoutMs}) => {
  const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
"""
    + _VERIFICATION_WIDGET_SNIPPET
    + """
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      credentials: "include",
      redirect: "follow",
      signal: controller.signal,
      headers: {Accept: "text/html,application/xhtml+xml"},
    });
    const text = await response.text();
    const doc = new DOMParser().parseFromString(text, "text/html");
    const candidates = Array.from(doc.querySelectorAll("table")).map((table) => {
      const headers = Array.from(
        table.querySelectorAll("thead th, tr.app-table__header-row th")
      ).map((cell) => clean(cell.textContent));
      const rows = Array.from(
        table.querySelectorAll("tbody tr, tr.app-table__row")
      )
        .map((row) =>
          Array.from(row.querySelectorAll("td")).map((cell) =>
            clean(cell.textContent)
          )
        )
        .filter((row) => row.length > 0);
      const score = headers.reduce((total, header) => {
        return total + (
          /quantity|qty|date|price|buyer|user|variation/i.test(header) ? 1 : 0
        );
      }, 0);
      return {headers, rows, score};
    }).sort((left, right) => right.score - left.score);
    const best = candidates[0] || {headers: [], rows: [], score: 0};
    return {
      status: response.status,
      contentType: response.headers.get("content-type") || "",
      bodyCharacterCount: text.length,
      title: doc.title,
      url: response.url,
      bodyText: clean(doc.body ? doc.body.textContent : "").slice(0, 4000),
      humanVerificationSelector: verificationSelector(doc),
      headers: best.headers,
      rows: best.rows,
      tableScore: best.score,
    };
  } finally {
    clearTimeout(timer);
  }
}
"""
)

_EXTRACT_CURRENT_DOCUMENT_SCRIPT = (
    """
() => {
  const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
"""
    + _VERIFICATION_WIDGET_SNIPPET
    + """
  const candidates = Array.from(document.querySelectorAll("table")).map((table) => {
    const headers = Array.from(
      table.querySelectorAll("thead th, tr.app-table__header-row th")
    ).map((cell) => clean(cell.textContent));
    const rows = Array.from(
      table.querySelectorAll("tbody tr, tr.app-table__row")
    )
      .map((row) =>
        Array.from(row.querySelectorAll("td")).map((cell) =>
          clean(cell.textContent)
        )
      )
      .filter((row) => row.length > 0);
    const score = headers.reduce((total, header) => {
      return total + (
        /quantity|qty|date|price|buyer|user|variation/i.test(header) ? 1 : 0
      );
    }, 0);
    return {headers, rows, score};
  }).sort((left, right) => right.score - left.score);
  const best = candidates[0] || {headers: [], rows: [], score: 0};
  return {
    title: document.title,
    url: location.href,
    bodyCharacterCount: document.documentElement.outerHTML.length,
    bodyText: clean(document.body ? document.body.textContent : "").slice(0, 4000),
    humanVerificationSelector: verificationSelector(document),
    headers: best.headers,
    rows: best.rows,
    tableScore: best.score,
  };
}
"""
)


class PersistentPurchaseHistoryBrowser:
    """Own one isolated persistent browser profile for all provider calls."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.profile_dir = (
            Path(settings.sales_profile_dir).expanduser()
            if settings.sales_profile_dir
            else None
        )
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lock = asyncio.Lock()
        self._session_state = "not_started"
        self._window_state = "unknown"
        self._parked_item_id: str | None = None

    @property
    def dependency_installed(self) -> bool:
        try:
            return importlib.util.find_spec("playwright.async_api") is not None
        except ModuleNotFoundError:
            return False

    async def status(self) -> dict[str, Any]:
        profile_initialized = bool(
            self.profile_dir
            and self.profile_dir.is_dir()
            and any(self.profile_dir.iterdir())
        )
        if not self.dependency_installed:
            session_state = "dependency_missing"
        elif self._context is not None:
            session_state = self._session_state
        elif profile_initialized:
            session_state = "profile_present_unverified"
        else:
            session_state = "requires_login"
        return {
            "browser_dependency_installed": self.dependency_installed,
            "profile_initialized": profile_initialized,
            "browser_running": self._context is not None,
            "headless": False,
            "browser_mode": "minimized_headed",
            "manual_recovery_timeout_seconds": (
                self.settings.sales_manual_recovery_timeout
            ),
            "session_state": session_state,
            "parked_item_id": self._parked_item_id,
            "browser_closed": self._context is None,
        }

    async def _ensure_context(self, *, present: bool = False) -> None:
        if self._context is not None:
            if present:
                await self._present_window()
            return
        if self.profile_dir is None:
            raise EbayMcpError(
                "SALES_BROWSER_PROFILE_NOT_CONFIGURED",
                "Configure EBAY_SALES_PROFILE_DIR before starting the sales browser.",
            )
        if not self.dependency_installed:
            raise EbayMcpError(
                "SALES_BROWSER_DEPENDENCY_MISSING",
                "Install the sales extra before enabling purchase-history collection.",
                details={
                    "install": "uv sync --extra sales",
                    "browser": "uv run playwright install chromium",
                },
            )
        from playwright.async_api import async_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        launch_options: dict[str, Any] = {
            "user_data_dir": str(self.profile_dir),
            "headless": False,
            "viewport": {"width": 1440, "height": 1000},
        }
        if not present:
            launch_options["args"] = ["--start-minimized"]
        if self.settings.sales_browser_channel:
            launch_options["channel"] = self.settings.sales_browser_channel
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                **launch_options
            )
        except Exception as exc:
            await self._stop_playwright()
            message = str(exc).casefold()
            if (
                "profile" in message
                or "processsingleton" in message
                or "in use" in message
            ):
                raise EbayMcpError(
                    "SALES_BROWSER_PROFILE_LOCKED",
                    "The sales browser profile is already in use.",
                    details={"action": "Close the other sales browser and retry."},
                ) from exc
            raise EbayMcpError(
                "SALES_BROWSER_START_FAILED",
                f"Could not start the sales browser: {type(exc).__name__}",
                details={
                    "browser_channel": self.settings.sales_browser_channel or "chromium"
                },
            ) from exc
        self._context.set_default_navigation_timeout(
            self.settings.sales_navigation_timeout * 1000
        )
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        if present:
            await self._present_window()
        else:
            await self._minimize_window()

    async def _set_window_state(self, state: str) -> None:
        context = self._context
        page = self._page
        if context is None or page is None:
            return
        new_cdp_session = getattr(context, "new_cdp_session", None)
        if new_cdp_session is None:
            return
        try:
            session = await new_cdp_session(page)
        except Exception:  # noqa: BLE001 - window control must not stop collection
            logger.info("Could not attach to the sales browser window")
            return
        try:
            result = await session.send("Browser.getWindowForTarget")
            await session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": result["windowId"],
                    "bounds": {"windowState": state},
                },
            )
        except Exception:  # noqa: BLE001 - window control must not stop collection
            logger.info("Could not change the sales browser window to %s", state)
        finally:
            detach = getattr(session, "detach", None)
            if detach is not None:
                try:
                    await detach()
                except Exception:  # noqa: BLE001
                    logger.info("Could not detach the sales browser window session")

    async def _minimize_window(self) -> None:
        if self._window_state == "minimized":
            return
        await self._set_window_state("minimized")
        self._window_state = "minimized"

    async def _present_window(self) -> None:
        if self._window_state != "normal":
            await self._set_window_state("normal")
            self._window_state = "normal"
        bring_to_front = getattr(self._page, "bring_to_front", None)
        if bring_to_front is None:
            return
        try:
            await bring_to_front()
        except Exception:  # noqa: BLE001 - window control must not stop collection
            logger.info("Could not bring the sales browser window forward")

    async def _wait_invisibly_for_verification(
        self,
        host: str,
        url: str,
        item_id: str,
        extracted: dict[str, Any],
        transport: str,
        observations: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]], str | None]:
        """Poll without showing the window until a captcha widget appears or the check clears."""

        self._session_state = "invisible_wait_for_verification"
        polls = max(1, int(self.settings.sales_challenge_grace_seconds))
        intervention = "SALES_CHALLENGE_DETECTED"
        load_error: EbayMcpError | None = None
        for _ in range(polls):
            if self.settings.sales_challenge_grace_seconds:
                await asyncio.sleep(1)
            await self._minimize_window()
            try:
                extracted, transport, observations = await self._load_purchase_page(
                    host,
                    url,
                    item_id,
                    allow_navigation=False,
                )
            except EbayMcpError as exc:
                if exc.code != "SALES_PAGE_LOAD_FAILED":
                    raise
                load_error = exc
                continue
            load_error = None
            if human_verification_selector(extracted):
                return extracted, transport, observations, "SALES_CHALLENGE_DETECTED"
            intervention = manual_intervention_code(
                str(extracted.get("url") or ""),
                str(extracted.get("title") or ""),
                str(extracted.get("bodyText") or ""),
            )
            if intervention != "SALES_CHALLENGE_DETECTED":
                return extracted, transport, observations, intervention
        if load_error is not None:
            raise load_error
        return extracted, transport, observations, intervention

    async def _await_manual_recovery(self, url: str, code: str) -> None:
        self._session_state = "awaiting_manual_verification"
        await self._present_window()
        try:
            await self._page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:
            raise EbayMcpError(
                "SALES_PAGE_LOAD_FAILED",
                f"Could not open the page for manual verification: {type(exc).__name__}",
                retryable=True,
            ) from exc
        if not await self._wait_until_unblocked():
            self._session_state = (
                "challenge" if code == "SALES_CHALLENGE_DETECTED" else "requires_login"
            )
            raise EbayMcpError(
                "SALES_MANUAL_RECOVERY_TIMEOUT",
                "Timed out waiting for manual login or browser verification.",
                details={
                    "timeout_seconds": self.settings.sales_manual_recovery_timeout,
                    "action": (
                        "Complete the restored browser window, leave it open, "
                        "and retry the purchase-history call."
                    ),
                },
            )

    async def _wait_until_unblocked(self) -> bool:
        deadline = (
            asyncio.get_running_loop().time()
            + self.settings.sales_manual_recovery_timeout
        )
        stable_checks = 0
        while asyncio.get_running_loop().time() < deadline:
            if self._page.is_closed():
                return False
            await asyncio.sleep(1)
            try:
                url = self._page.url
                title = await self._page.title()
                body = await self._page.evaluate(
                    "() => ((document.body && document.body.innerText) || '').slice(0, 2000)"
                )
            except Exception:  # noqa: BLE001 - keep waiting while the page changes
                stable_checks = 0
                continue
            ready = (
                manual_intervention_code(url, title, str(body or "")) is None
                and url not in {"", "about:blank"}
            )
            stable_checks = stable_checks + 1 if ready else 0
            if stable_checks >= 3:
                return True
        return False

    async def _load_purchase_page(
        self,
        host: str,
        url: str,
        item_id: str,
        *,
        allow_navigation: bool = True,
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        observations: list[dict[str, Any]] = []

        def observe(response: Any) -> None:
            parts = urlsplit(response.url)
            response_host = (parts.hostname or "").casefold()
            ebay_domain = host.casefold().removeprefix("www.")
            if (
                response_host != ebay_domain
                and not response_host.endswith(f".{ebay_domain}")
            ) or len(observations) >= 25:
                return
            resource_type = response.request.resource_type
            if resource_type not in {"document", "xhr", "fetch"}:
                return
            observed_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
            if parts.path.casefold().endswith("/bin/purchasehistory"):
                observed_url = f"{observed_url}?item={item_id}"
            observations.append(
                {
                    "method": response.request.method,
                    "url": observed_url,
                    "status": response.status,
                    "resource_type": resource_type,
                    "content_type": response.headers.get("content-type", "").split(";")[
                        0
                    ],
                }
            )

        self._page.on("response", observe)
        try:
            current = urlsplit(self._page.url)
            same_origin = (current.hostname or "").casefold() == host.casefold()
            if not allow_navigation or (
                same_origin and "splashui/challenge" not in current.path.casefold()
            ):
                extracted = await self._page.evaluate(
                    _FETCH_AND_EXTRACT_SCRIPT,
                    {
                        "url": url,
                        "timeoutMs": int(self.settings.sales_navigation_timeout * 1000),
                    },
                )
                transport = "browser_in_page_fetch"
            else:
                response = await self._page.goto(url, wait_until="domcontentloaded")
                self._window_state = "unknown"
                await self._minimize_window()
                await self._page.wait_for_timeout(500)
                extracted = await self._page.evaluate(_EXTRACT_CURRENT_DOCUMENT_SCRIPT)
                extracted["status"] = response.status if response else 0
                extracted["contentType"] = (
                    response.headers.get("content-type", "") if response else ""
                )
                transport = "browser_navigation_bootstrap"
        except EbayMcpError:
            raise
        except Exception as exc:
            raise EbayMcpError(
                "SALES_PAGE_LOAD_FAILED",
                f"Could not load purchase history for {item_id}: {type(exc).__name__}",
                retryable=True,
                details={"legacy_item_id": item_id},
            ) from exc
        finally:
            self._page.remove_listener("response", observe)
        return extracted, transport, observations

    def _purchase_result(
        self,
        extracted: dict[str, Any],
        transport: str,
        observations: list[dict[str, Any]],
        *,
        item_id: str,
        marketplace_id: str,
        url: str,
        limit: int,
    ) -> dict[str, Any]:
        final_url = str(extracted.get("url") or self._page.url)
        title = str(extracted.get("title") or "")
        page_text = str(extracted.get("bodyText") or "")
        intervention = manual_intervention_code(final_url, title, page_text)
        if intervention == "SALES_CHALLENGE_DETECTED":
            self._session_state = "challenge"
            raise EbayMcpError(
                intervention,
                "eBay presented a browser verification page.",
                details={
                    "legacy_item_id": item_id,
                    "action": "Complete verification in the restored browser window.",
                },
            )
        if intervention == "SALES_LOGIN_REQUIRED":
            self._session_state = "requires_login"
            raise EbayMcpError(
                intervention,
                "The purchase-history browser is not logged in.",
                details={
                    "legacy_item_id": item_id,
                    "action": "Complete login in the restored browser window.",
                },
            )
        response_status = int(extracted.get("status") or 0)
        if response_status >= 400:
            raise EbayMcpError(
                "SALES_PAGE_HTTP_ERROR",
                f"Purchase-history page returned HTTP {response_status}.",
                status_code=response_status,
                retryable=response_status in {408, 425, 429} or response_status >= 500,
                details={"legacy_item_id": item_id},
            )

        headers = list(extracted.get("headers") or [])
        rows = list(extracted.get("rows") or [])
        score = int(extracted.get("tableScore") or 0)
        lowered = f"{final_url}\n{title}\n{page_text}".casefold()
        empty_markers = (
            "no purchase history",
            "no purchases",
            "0 sold",
            "hasn't sold",
        )
        if score < 2 and not any(marker in lowered for marker in empty_markers):
            raise EbayMcpError(
                "SALES_PAGE_SCHEMA_CHANGED",
                "The purchase-history table was not recognized.",
                details={
                    "legacy_item_id": item_id,
                    "page_title": title,
                    "observed_headers": headers,
                },
            )

        normalized = normalize_purchase_table(
            headers,
            rows,
            marketplace_id,
            limit=limit,
        )
        normalized.update(
            {
                "legacy_item_id": item_id,
                "status": "ok",
                "source_url": url,
                "transport": transport,
                "response_body_character_count": int(
                    extracted.get("bodyCharacterCount") or 0
                ),
                "network_observations": observations,
                "warnings": [
                    "The sales record is the transactions list collected from this page.",
                    "visible_quantity only sums those rows and is not a substitute for them.",
                    "Do not replace these rows with Browse API estimatedSoldQuantity.",
                ],
            }
        )
        self._session_state = "ready"
        return normalized

    async def fetch(
        self,
        item_id: str,
        marketplace_id: str,
        *,
        limit: int,
        allow_window: bool = False,
    ) -> dict[str, Any]:
        host = MARKETPLACE_HOSTS.get(marketplace_id)
        if not host:
            raise EbayMcpError(
                "SALES_MARKETPLACE_UNSUPPORTED",
                f"Purchase-history collection is not configured for {marketplace_id}.",
                details={"supported": sorted(MARKETPLACE_HOSTS)},
            )
        url = f"https://{host}/bin/purchaseHistory?item={item_id}"
        async with self._lock:
            await self._ensure_context()
            await self._minimize_window()
            extracted, transport, observations = await self._load_purchase_page(
                host,
                url,
                item_id,
            )
            intervention = manual_intervention_code(
                str(extracted.get("url") or ""),
                str(extracted.get("title") or ""),
                str(extracted.get("bodyText") or ""),
            )
            detected = intervention
            if intervention == "SALES_CHALLENGE_DETECTED" and not human_verification_selector(
                extracted
            ):
                (
                    extracted,
                    transport,
                    observations,
                    intervention,
                ) = await self._wait_invisibly_for_verification(
                    host,
                    url,
                    item_id,
                    extracted,
                    transport,
                    observations,
                )
            selector = human_verification_selector(extracted)
            needs_person = bool(selector) or intervention == "SALES_LOGIN_REQUIRED"
            if intervention == "SALES_CHALLENGE_DETECTED" and not selector:
                self._session_state = "invisible_wait_for_verification"
                raise EbayMcpError(
                    "SALES_CHECK_UNRESOLVED",
                    "eBay's check continued without a human-verification component. The window stayed hidden.",
                    retryable=True,
                    details={
                        "legacy_item_id": item_id,
                        "session_state": self._session_state,
                    },
                )
            if needs_person and not allow_window:
                if selector:
                    self._session_state = "window_confirmation_required"
                    raise EbayMcpError(
                        "SALES_WINDOW_CONFIRMATION_REQUIRED",
                        "A human-verification component is present. The browser window stays hidden until you allow it.",
                        details={
                            "legacy_item_id": item_id,
                            "detected_as": intervention,
                            "human_verification_selector": selector,
                            "action": (
                                "Ask the user whether to show the browser window. "
                                "Only after they agree, retry with allow_browser_window=true."
                            ),
                        },
                    )
                self._session_state = "requires_login"
                raise EbayMcpError(
                    "SALES_LOGIN_REQUIRED",
                    "The purchase-history browser is on a sign-in page. The window stays hidden until you allow it.",
                    details={
                        "legacy_item_id": item_id,
                        "action": (
                            "Ask the user before calling ebay_sales_open_login. "
                            "Do not close the browser after login."
                        ),
                    },
                )
            if needs_person:
                await self._await_manual_recovery(url, intervention)
                extracted, transport, observations = await self._load_purchase_page(
                    host,
                    url,
                    item_id,
                )
            normalized = self._purchase_result(
                extracted,
                transport,
                observations,
                item_id=item_id,
                marketplace_id=marketplace_id,
                url=url,
                limit=limit,
            )
            if intervention:
                normalized["manual_recovery"] = intervention
                normalized["warnings"].append(
                    "The browser window was shown after confirmation and minimized after collection resumed."
                )
            elif detected:
                normalized["silent_grace_retry"] = True
            self._parked_item_id = item_id
            self._session_state = "parked"
            await self._minimize_window()
            return normalized

    async def inspect(self) -> dict[str, Any]:
        """Read the parked page without showing or closing the browser."""

        if self._context is None or self._page is None:
            return {
                "browser_running": False,
                "browser_closed": True,
                "ready_for_collection": False,
                "session_state": self._session_state,
                "page_url": None,
                "page_title": None,
                "intervention": None,
                "human_verification_selector": None,
                "parked_item_id": self._parked_item_id,
            }
        try:
            url = self._page.url
            title = await self._page.title()
            body = await self._page.evaluate(
                "() => ((document.body && document.body.innerText) || '').slice(0, 2000)"
            )
            selector = await self._page.evaluate(
                "() => {\n"
                + _VERIFICATION_WIDGET_SNIPPET
                + "  return verificationSelector(document);\n}"
            )
        except Exception as exc:  # noqa: BLE001 - inspection must not close the browser
            return {
                "browser_running": True,
                "browser_closed": False,
                "ready_for_collection": False,
                "session_state": "inspection_failed",
                "page_url": None,
                "page_title": None,
                "intervention": "SALES_PAGE_LOAD_FAILED",
                "human_verification_selector": None,
                "parked_item_id": self._parked_item_id,
                "error": type(exc).__name__,
            }
        intervention = manual_intervention_code(url, title, str(body or ""))
        selector_text = str(selector or "")
        ready = (
            intervention is None
            and not selector_text
            and url not in {"", "about:blank"}
        )
        return {
            "browser_running": True,
            "browser_closed": False,
            "ready_for_collection": ready,
            "session_state": self._session_state,
            "page_url": url,
            "page_title": title,
            "intervention": intervention,
            "human_verification_selector": selector_text or None,
            "parked_item_id": self._parked_item_id,
        }

    async def _park_on_history(
        self, marketplace_id: str, item_id: str | None
    ) -> dict[str, Any]:
        host = MARKETPLACE_HOSTS[marketplace_id]
        if item_id:
            normalized = normalize_legacy_item_ids([item_id])[0]
            await self._page.goto(
                f"https://{host}/bin/purchaseHistory?item={normalized}",
                wait_until="domcontentloaded",
            )
            self._parked_item_id = normalized
            self._window_state = "unknown"
        self._session_state = "parked"
        await self._minimize_window()
        return {
            "page_url": self._page.url,
            "page_title": await self._page.title(),
            "parked_item_id": self._parked_item_id,
            "session_state": self._session_state,
            "browser_running": True,
            "browser_closed": False,
        }

    async def _open_login_page_unlocked(self, marketplace_id: str) -> tuple[str, str]:
        host = MARKETPLACE_HOSTS.get(marketplace_id)
        if not host:
            raise EbayMcpError(
                "SALES_MARKETPLACE_UNSUPPORTED",
                f"Unsupported marketplace: {marketplace_id}",
            )
        await self._ensure_context(present=True)
        await self._page.goto(
            f"https://signin.{host.removeprefix('www.')}/ws/eBayISAPI.dll?SignIn",
            wait_until="domcontentloaded",
        )
        self._session_state = "awaiting_manual_login"
        return host, await self._page.title()

    async def open_login(
        self, marketplace_id: str = "EBAY_GB", item_id: str | None = None
    ) -> dict[str, Any]:
        """Show the login window, then keep it minimized on the history page."""

        async with self._lock:
            await self._open_login_page_unlocked(marketplace_id)
            if not await self._wait_until_unblocked():
                raise EbayMcpError(
                    "SALES_LOGIN_TIMEOUT",
                    "Timed out waiting for eBay sign-in to complete.",
                    details={"timeout_seconds": self.settings.sales_manual_recovery_timeout},
                )
            parked = await self._park_on_history(marketplace_id, item_id)
            if parked["parked_item_id"]:
                parked["instruction"] = (
                    "Login is complete. The browser stays open and minimized on "
                    "the purchase-history page until the sales tool polls it."
                )
            else:
                parked["instruction"] = (
                    "Login is complete. The browser stays open and minimized. "
                    "The sales tool checks this session, then opens each "
                    "purchase-history page in the same window."
                )
            return parked

    async def interactive_login(
        self, marketplace_id: str = "EBAY_GB"
    ) -> dict[str, Any]:
        async with self._lock:
            host, _title = await self._open_login_page_unlocked(marketplace_id)
            from playwright.async_api import Error as PlaywrightError

            deadline = asyncio.get_running_loop().time() + 900
            stable_success_checks = 0
            final_url = self._page.url
            title = await self._page.title()
            while asyncio.get_running_loop().time() < deadline:
                if self._page.is_closed():
                    break
                try:
                    final_url = self._page.url
                    title = await self._page.title()
                except PlaywrightError:
                    break

                lowered = f"{final_url}\n{title}".casefold()
                on_ebay = (
                    (urlsplit(final_url).hostname or "")
                    .casefold()
                    .endswith(host.removeprefix("www.").casefold())
                )
                login_complete = (
                    on_ebay
                    and "signin" not in lowered
                    and "splashui/challenge" not in lowered
                    and "pardon our interruption" not in lowered
                    and final_url != "about:blank"
                )
                stable_success_checks = (
                    stable_success_checks + 1 if login_complete else 0
                )
                if stable_success_checks >= 3:
                    break
                await asyncio.sleep(1)
            else:
                raise EbayMcpError(
                    "SALES_LOGIN_TIMEOUT",
                    "Timed out waiting for eBay sign-in to complete.",
                    details={"timeout_seconds": 900},
                )

            parked = await self._park_on_history(marketplace_id, None)
            return {
                "profile_initialized": True,
                "browser_running": True,
                "browser_closed": False,
                "final_url": parked["page_url"] or final_url,
                "page_title": parked["page_title"] or title,
                "session_state": self._session_state,
                "next_step": (
                    "Leave this browser open. Call ebay_get_sales_history to poll it."
                ),
            }

    async def _stop_playwright(self) -> None:
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._context = None
        self._page = None

    async def close(self) -> None:
        async with self._lock:
            if self._context is not None:
                await self._context.close()
            await self._stop_playwright()


class PurchaseHistoryProvider(SalesHistoryProvider):
    name = "ebay-purchase-history"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.browser = PersistentPurchaseHistoryBrowser(settings)

    async def open_login(
        self, marketplace_id: str, item_id: str | None = None
    ) -> dict[str, Any]:
        return await self.browser.open_login(marketplace_id, item_id=item_id)

    async def _require_parked_session(self, allow_window: bool) -> dict[str, Any] | None:
        inspect = getattr(self.browser, "inspect", None)
        if inspect is None:
            return None
        state = await inspect()
        selector = state.get("human_verification_selector")
        intervention = state.get("intervention")
        if not state.get("browser_running"):
            raise EbayMcpError(
                "SALES_BROWSER_NOT_PARKED",
                "The purchase-history browser is not open. Choose login first; the window then stays minimized.",
                details={
                    "action": "Call ebay_sales_open_login after the user agrees, and do not close the browser.",
                    "session": state,
                },
            )
        if selector and not allow_window:
            raise EbayMcpError(
                "SALES_WINDOW_CONFIRMATION_REQUIRED",
                "The parked page has a human-verification component. The window stays hidden until you allow it.",
                details={"session": state, "human_verification_selector": selector},
            )
        if intervention == "SALES_LOGIN_REQUIRED" and not allow_window:
            raise EbayMcpError(
                "SALES_LOGIN_REQUIRED",
                "The parked browser is on a sign-in page.",
                details={
                    "session": state,
                    "action": "Ask the user before calling ebay_sales_open_login.",
                },
            )
        return state

    async def status(self) -> dict[str, Any]:
        browser = await self.browser.status()
        available = (
            browser["browser_dependency_installed"] and browser["profile_initialized"]
        )
        if not browser["browser_dependency_installed"]:
            reason = "The optional Playwright sales dependency is not installed."
        elif not browser["profile_initialized"]:
            reason = "Run ebay-mcp-sales-login to initialize the browser profile."
        else:
            reason = None
        return {
            "name": self.name,
            "available": available,
            "implementation_bundled": True,
            "data_scope": "recent visible per-listing purchase history",
            "complete_lifetime_sales": False,
            "browser": browser,
            "reason": reason,
        }

    async def search(
        self,
        item_ids: list[str],
        marketplace_id: str,
        *,
        limit: int,
        allow_window: bool = False,
    ) -> dict[str, Any]:
        session = await self._require_parked_session(allow_window)
        normalized_ids = normalize_legacy_item_ids(item_ids)
        items: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        fatal_error: EbayMcpError | None = None

        for index, item_id in enumerate(normalized_ids):
            if index and self.settings.sales_min_delay:
                await asyncio.sleep(self.settings.sales_min_delay)
            try:
                items.append(
                    await self.browser.fetch(
                        item_id,
                        marketplace_id,
                        limit=limit,
                        allow_window=allow_window,
                    )
                )
            except EbayMcpError as exc:
                failures.append(
                    {
                        "legacy_item_id": item_id,
                        "status": "failed",
                        "error": exc.as_dict(),
                    }
                )
                if exc.code in FATAL_SESSION_CODES:
                    fatal_error = exc
                    for skipped in normalized_ids[index + 1 :]:
                        failures.append(
                            {
                                "legacy_item_id": skipped,
                                "status": "skipped",
                                "error": {
                                    "code": "SALES_BATCH_ABORTED",
                                    "message": f"Skipped after {exc.code}.",
                                    "retryable": False,
                                },
                            }
                        )
                    break

        if fatal_error is not None and not items:
            raise fatal_error

        return {
            "items": items,
            "failures": failures,
            "requested_count": len(normalized_ids),
            "succeeded_count": len(items),
            "failed_count": len(failures),
            "session": session,
            "partial": bool(failures),
            "window_confirmation_required": any(
                (failure.get("error") or {}).get("code")
                == "SALES_WINDOW_CONFIRMATION_REQUIRED"
                for failure in failures
            ),
            "warnings": [
                "Use items[].transactions as the sales detail. Do not substitute Browse API estimatedSoldQuantity.",
                "visible_quantity only sums the collected rows and is not lifetime sales.",
            ],
            "provenance": {
                "provider": self.name,
                "marketplace_id": marketplace_id,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_type": "logged-in eBay web page",
            },
        }

    async def close(self) -> None:
        await self.browser.close()
