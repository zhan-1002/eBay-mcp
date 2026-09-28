"""Configuration loaded from environment variables and optional local JSON."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


load_dotenv()

BASE_SCOPE = "https://api.ebay.com/oauth/api_scope"
FEEDBACK_SCOPE = f"{BASE_SCOPE}/commerce.feedback.readonly"


def _load_json_config() -> dict[str, Any]:
    explicit = os.getenv("EBAY_CONFIG_FILE", "").strip()
    candidates = [Path(explicit)] if explicit else [Path.cwd() / "config.local.json"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}
    return {}


def _env(name: str, fallback: Any = "") -> Any:
    value = os.getenv(name)
    return value if value not in (None, "") else fallback


@dataclass(frozen=True)
class Settings:
    environment: str
    client_id: str
    client_secret: str
    user_access_token: str
    request_timeout: float
    max_retries: int
    retry_base_delay: float
    sales_provider: str

    @classmethod
    def load(cls) -> "Settings":
        raw = _load_json_config()
        api = raw.get("ebay_api") if isinstance(raw.get("ebay_api"), dict) else {}
        environment = str(
            _env("EBAY_ENV", api.get("env") or api.get("environment") or "production")
        ).lower()
        if environment not in {"production", "sandbox"}:
            raise ValueError("EBAY_ENV must be production or sandbox")
        return cls(
            environment=environment,
            client_id=str(_env("EBAY_CLIENT_ID", api.get("client_id", ""))).strip(),
            client_secret=str(
                _env("EBAY_CLIENT_SECRET", api.get("client_secret", ""))
            ).strip(),
            user_access_token=str(_env("EBAY_USER_TOKEN", "")).strip(),
            request_timeout=float(_env("EBAY_REQUEST_TIMEOUT", "30")),
            max_retries=max(0, min(int(_env("EBAY_MAX_RETRIES", "2")), 5)),
            retry_base_delay=max(
                0.0, min(float(_env("EBAY_RETRY_BASE_DELAY", "0.5")), 10.0)
            ),
            sales_provider=str(_env("EBAY_SALES_PROVIDER", "disabled")).lower(),
        )

    @property
    def api_root(self) -> str:
        return (
            "https://api.sandbox.ebay.com"
            if self.environment == "sandbox"
            else "https://api.ebay.com"
        )

    @property
    def auth_root(self) -> str:
        return (
            "https://api.sandbox.ebay.com"
            if self.environment == "sandbox"
            else "https://api.ebay.com"
        )

    def public_status(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "client_credentials_configured": bool(
                self.client_id and self.client_secret
            ),
            "user_token_configured": bool(self.user_access_token),
            "sales_provider": self.sales_provider,
            "request_timeout_seconds": self.request_timeout,
            "max_retries": self.max_retries,
        }

