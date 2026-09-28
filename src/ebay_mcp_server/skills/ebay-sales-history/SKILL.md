---
name: ebay-sales-history
description: Uses the optional sales-history provider when explicitly configured. Use when requesting sales observations unavailable from official APIs, while enforcing provider availability, provenance, access rules, and fail-closed behavior.
---

# eBay Sales History Provider

## Current state

The base eBay MCP package does not include a scraper or non-public data
provider. Never imply that sales history is available before checking status.

## Workflow

1. Call `ebay_sales_provider_status`.
2. If unavailable, stop and report `SALES_PROVIDER_NOT_CONFIGURED`.
3. If available, confirm Marketplace, query, result limit and provider terms.
4. Call `ebay_get_sales_history`.
5. Preserve provider provenance, retrieval time, cursor, partial status and
   warnings.
6. Distinguish observed transactions from estimates or derived aggregates.

## Safety rules

- Do not bypass CAPTCHA, access controls, account restrictions or technical
  protection measures.
- Do not request or expose Cookie, token, proxy or account secrets in chat.
- Respect the provider's rate limit and concurrency limit.
- If page structure or response shape is unrecognized, fail closed.
- Never silently substitute seller feedback counts for complete sales history.

