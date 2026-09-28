---
name: ebay-listing-retrieval
description: Retrieves active eBay listings and item details through official APIs. Use when searching listings, paginating results, resolving item IDs, or reading listing fields without scoring or recommendation.
---

# eBay Listing Retrieval

## Scope

Use this skill to retrieve active listings and their official Browse API details.
Do not perform product selection, keyword expansion, sales estimation, ranking,
or listing modification.

## Workflow

1. Call `ebay_get_capabilities` if the environment or Marketplace is unknown.
2. Call `ebay_search_items` with the user's exact query and Marketplace.
3. Preserve eBay result order. Do not invent a relevance score.
4. Follow pagination using `limit` and `offset`; offset must be zero or a
   multiple of limit.
5. Call `ebay_get_item` only for item IDs that need full details.
6. Return source, Marketplace, pagination and partial-error information.

## Identifier rules

- Treat the REST `itemId` and numeric `legacyItemId` as different identifiers.
- Pass the REST item ID to `ebay_get_item`.
- Do not reconstruct an item ID from URL text when the API already returned it.

## Output

Summarize the request parameters and result count, then return the requested
listing fields. State when a field was absent from eBay instead of guessing it.

