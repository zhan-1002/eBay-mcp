"""Low-level authenticated HTTP gateway for official eBay APIs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import random
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from ebay_mcp_server.config import BASE_SCOPE, Settings
from ebay_mcp_server.contracts import Marketplace
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.oauth import OAuthTokenProvider


@dataclass
class ApiResponse:
    data: dict[str, Any]
    meta: dict[str, Any]


class EbayGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        http: httpx.AsyncClient | None = None,
    ):
        self.settings = settings
        self.http = http or httpx.AsyncClient(
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_http = http is None
        self.oauth = OAuthTokenProvider(settings, self.http)

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        scopes: Iterable[str] = (BASE_SCOPE,),
        marketplace: Marketplace | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        token_kind: str = "application",
    ) -> ApiResponse:
        token = (
            self.oauth.user_token()
            if token_kind == "user"
            else await self.oauth.application_token(scopes)
        )
        headers = {"Authorization": f"Bearer {token}"}
        if marketplace:
            headers["X-EBAY-C-MARKETPLACE-ID"] = marketplace.marketplace_id
            location = f"country={marketplace.country},zip={marketplace.postal_code}"
            headers["X-EBAY-C-ENDUSERCTX"] = (
                "contextualLocation=" + quote(location, safe="")
            )

        response: httpx.Response | None = None
        refreshed = False
        max_attempts = self.settings.max_retries + 1
        for attempt in range(max_attempts):
            try:
                response = await self.http.request(
                    method,
                    f"{self.settings.api_root}{path}",
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=self.settings.request_timeout,
                )
            except httpx.HTTPError as exc:
                if attempt + 1 >= max_attempts:
                    raise EbayMcpError(
                        "NETWORK_ERROR",
                        f"eBay request failed: {type(exc).__name__}",
                        retryable=True,
                    ) from exc
                await self._backoff(attempt, None)
                continue

            if (
                response.status_code == 401
                and token_kind == "application"
                and not refreshed
            ):
                self.oauth.invalidate_application_tokens()
                token = await self.oauth.application_token(scopes)
                headers["Authorization"] = f"Bearer {token}"
                refreshed = True
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt + 1 < max_attempts:
                    await self._backoff(attempt, response)
                    continue
            break

        if response is None:
            raise EbayMcpError("NETWORK_ERROR", "eBay request produced no response.")
        if response.status_code < 200 or response.status_code >= 300:
            raise _api_error(response)

        try:
            body = response.json()
        except ValueError as exc:
            raise EbayMcpError(
                "INVALID_UPSTREAM_RESPONSE",
                "eBay returned a non-JSON response.",
                status_code=response.status_code,
                details=response.text[:500],
            ) from exc

        request_id = (
            response.headers.get("x-ebay-c-request-id")
            or response.headers.get("x-ebay-request-id")
            or response.headers.get("x-request-id")
        )
        return ApiResponse(
            data=body,
            meta={
                "http_status": response.status_code,
                "request_id": request_id,
                "environment": self.settings.environment,
                "marketplace_id": marketplace.marketplace_id if marketplace else None,
            },
        )

    async def _backoff(
        self, attempt: int, response: httpx.Response | None
    ) -> None:
        retry_after = 0.0
        if response is not None:
            try:
                retry_after = float(response.headers.get("retry-after", "0"))
            except ValueError:
                retry_after = 0.0
        delay = max(
            retry_after,
            self.settings.retry_base_delay * (2**attempt) + random.uniform(0, 0.2),
        )
        await asyncio.sleep(min(delay, 15.0))


def _api_error(response: httpx.Response) -> EbayMcpError:
    try:
        details: Any = response.json()
    except ValueError:
        details = response.text[:1000]
    status = response.status_code
    code = {
        400: "INVALID_REQUEST",
        401: "AUTH_FAILED",
        403: "SCOPE_OR_PERMISSION_REQUIRED",
        404: "NOT_FOUND",
        409: "CONFLICT",
        429: "RATE_LIMITED",
    }.get(status, "UPSTREAM_ERROR")
    return EbayMcpError(
        code,
        f"eBay API returned HTTP {status}.",
        status_code=status,
        retryable=status == 429 or status >= 500,
        details=details,
    )

