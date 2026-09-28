"""In-memory eBay OAuth token provider.

The MCP server never returns tokens to callers. Application tokens are cached
per scope set and refreshed five minutes before expiry.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import time
from typing import Iterable

import httpx

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError


@dataclass
class CachedToken:
    value: str
    expires_at: float

    def valid(self, now: float) -> bool:
        return bool(self.value) and self.expires_at - now > 300


class OAuthTokenProvider:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http
        self._cache: dict[tuple[str, ...], CachedToken] = {}
        self._lock = asyncio.Lock()

    async def application_token(self, scopes: Iterable[str]) -> str:
        scope_key = tuple(sorted(set(scopes)))
        now = time.time()
        cached = self._cache.get(scope_key)
        if cached and cached.valid(now):
            return cached.value

        async with self._lock:
            now = time.time()
            cached = self._cache.get(scope_key)
            if cached and cached.valid(now):
                return cached.value
            if not self.settings.client_id or not self.settings.client_secret:
                raise EbayMcpError(
                    "AUTH_NOT_CONFIGURED",
                    "Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET before calling official APIs.",
                )

            raw = (
                f"{self.settings.client_id}:{self.settings.client_secret}"
            ).encode("utf-8")
            basic = base64.b64encode(raw).decode("ascii")
            try:
                response = await self.http.post(
                    f"{self.settings.auth_root}/identity/v1/oauth2/token",
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "client_credentials",
                        "scope": " ".join(scope_key),
                    },
                    timeout=self.settings.request_timeout,
                )
            except httpx.HTTPError as exc:
                raise EbayMcpError(
                    "AUTH_NETWORK_ERROR",
                    f"eBay OAuth request failed: {type(exc).__name__}",
                    retryable=True,
                ) from exc
            if response.status_code != 200:
                raise EbayMcpError(
                    "AUTH_FAILED",
                    "eBay rejected the client credentials or requested scopes.",
                    status_code=response.status_code,
                    details=_safe_json(response),
                )

            body = response.json()
            token = str(body.get("access_token") or "")
            if not token:
                raise EbayMcpError(
                    "AUTH_INVALID_RESPONSE",
                    "eBay OAuth response did not contain an access token.",
                )
            expires_in = max(1, int(body.get("expires_in") or 7200))
            self._cache[scope_key] = CachedToken(token, now + expires_in)
            return token

    def user_token(self) -> str:
        if not self.settings.user_access_token:
            raise EbayMcpError(
                "USER_AUTH_REQUIRED",
                "This operation requires EBAY_USER_TOKEN and the corresponding user scopes.",
            )
        return self.settings.user_access_token

    def invalidate_application_tokens(self) -> None:
        self._cache.clear()


def _safe_json(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return response.text[:500]

