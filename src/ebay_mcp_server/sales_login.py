"""Interactive one-time login for the isolated purchase-history profile."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ebay_mcp_server.config import Settings
from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.providers.purchase_history import (
    MARKETPLACE_HOSTS,
    PersistentPurchaseHistoryBrowser,
)


async def _login(marketplace_id: str) -> int:
    browser = PersistentPurchaseHistoryBrowser(Settings.load())
    try:
        result = await browser.interactive_login(marketplace_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "Browser remains open. Press Ctrl+C to stop this process.",
            file=sys.stderr,
        )
        await asyncio.Event().wait()
        return 0
    except EbayMcpError as exc:
        print(
            json.dumps({"success": False, "error": exc.as_dict()}, ensure_ascii=False)
        )
        return 1
    finally:
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sign in to eBay using the MCP sales browser profile."
    )
    parser.add_argument(
        "--marketplace",
        default="EBAY_GB",
        choices=sorted(MARKETPLACE_HOSTS),
        help="Marketplace whose eBay sign-in page should be opened.",
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(_login(args.marketplace)))
    except KeyboardInterrupt:
        print("Login cancelled.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
