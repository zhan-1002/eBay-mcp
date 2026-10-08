---
name: ebay-sales-history
description: Collects eBay purchase-history transaction rows. Those rows are the sales detail. Do not substitute Browse API estimatedSoldQuantity.
---

# eBay Sales History Provider

## Current state

The sales data is the collected purchase-history detail: each `transactions`
row with price, quantity, time and variation. `visible_quantity` only sums
those rows. Browse API `estimatedSoldQuantity` from `ebay_get_item` is an
official aggregate estimate and is not this sales record. Do not report it,
rank by it, or fill a gap with it when the transaction rows are missing.

The purchase-history provider uses a persistent local browser session to read
those rows from an eBay listing's purchase-history page. After the user agrees
to sign in, the same window stays open and minimized for later polls. The
project MCP configuration enables this provider; standalone deployments select
it with `EBAY_SALES_PROVIDER=purchase_history`.

## Workflow

1. Call `ebay_sales_provider_status`.
2. If the provider is disabled, stop and report `SALES_PROVIDER_NOT_CONFIGURED`.
3. Keep the browser minimized. If a call returns
   `SALES_WINDOW_CONFIRMATION_REQUIRED`, ask the user whether to show the
   window. Only after they agree, call `ebay_sales_open_login` or retry with
   `allow_browser_window=true`.
4. Confirm Marketplace, numeric legacy item IDs and per-item limit.
5. Call `ebay_get_sales_history` in the same MCP server process.
6. Preserve provider provenance, retrieval time, coverage, partial status and
   warnings.
7. Return `transactions` as the sales detail. Mention `visible_quantity` only
   as the sum of those rows.

## Rules

- Do not request or expose Cookie, token, proxy or account secrets in chat.
- Keep the provider's rate limit and concurrency limit.
- Use traditional numeric `legacyItemId` values, not Browse REST item IDs.
- If page structure or response shape is unrecognized, return a clear failure.
- Never substitute `estimatedSoldQuantity` or seller feedback counts for the
  collected transaction rows.
- A browser check is not human verification. While it is only a check, keep the
  window hidden and wait for a captcha component to appear.
- Ask to show the window only after that component is present, and only with the
  user's permission.

