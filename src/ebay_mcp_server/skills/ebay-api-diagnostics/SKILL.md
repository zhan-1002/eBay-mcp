---
name: ebay-api-diagnostics
description: Diagnoses eBay MCP authentication, scopes, quotas, Marketplace configuration, and upstream failures. Use for 401, 403, 429, 5xx, missing capability, or connectivity investigations.
---

# eBay API Diagnostics

## Workflow

1. Call `ebay_get_capabilities` without exposing credential values.
2. Confirm production versus sandbox and the requested Marketplace.
3. Call `ebay_get_rate_limits` when application-token authentication works.
4. Reproduce the failure with the smallest read-only request.
5. Report the failed layer: configuration, OAuth, scope, entitlement, quota,
   request validation, upstream availability, or local transport.

## Error interpretation

- `401`: token or client authentication failed; retry only after refresh or
  configuration correction.
- `403`: the token may be valid but the scope, user authorization, or eBay
  entitlement is missing.
- `429`: respect Retry-After and reduce request rate.
- `5xx`: retry within the configured budget, then report partial availability.
- `404`: verify endpoint version and path before concluding that authorization
  is missing.

## Critical distinction

Having a quota entry does not prove that the current token has permission, and
having a documented endpoint does not prove that the application is entitled
to use it. Report quota, scope and successful invocation as separate facts.

