---
name: ebay-sales-history
description: Uses the optional sales-history provider when explicitly configured. Use when requesting purchase-history observations unavailable from official APIs, and report provider availability and provenance.
---

# eBay Sales History Provider

## Current state

The base package reserves the provider and does not include a purchase-history
collector yet. Check status before treating sales history as available. The
project does not forbid automated collection.

## Workflow

1. Call `ebay_sales_provider_status`.
2. If unavailable, stop and report `SALES_PROVIDER_NOT_CONFIGURED`.
3. If available, confirm Marketplace, query, result limit and provider terms.
4. Call `ebay_get_sales_history`.
5. Preserve provider provenance, retrieval time, cursor, partial status and
   warnings.
6. Distinguish observed transactions from estimates or derived aggregates.

## Rules

- Do not request or expose Cookie, token, proxy or account secrets in chat.
- Keep the provider's rate limit and concurrency limit.
- If page structure or response shape is unrecognized, return a clear failure.
- Never silently substitute seller feedback counts for complete sales history.

