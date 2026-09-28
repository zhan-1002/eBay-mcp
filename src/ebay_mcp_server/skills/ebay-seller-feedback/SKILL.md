---
name: ebay-seller-feedback
description: Reads and interprets official eBay seller feedback records. Use when examining feedback comments, feedback type, transaction price, or listing-level counts among orders that received feedback.
---

# eBay Seller Feedback

## Workflow

1. Obtain the seller's public username or immutable public user ID.
2. Call `ebay_get_seller_feedback` with `FEEDBACK_RECEIVED` unless the user
   explicitly asks for feedback sent by the seller.
3. Paginate within the requested limit.
4. Preserve listing ID, listing title, transaction price, feedback type,
   comment and transaction-period fields.
5. Label any listing aggregation as "feedback-linked orders".

## Required caveats

- Feedback entries cover only orders for which feedback exists.
- A feedback count is not absolute unit sales.
- Transaction periods may be coarse and must not be converted into invented
  transaction dates.
- Seller feedback percentage describes seller reputation, not product review
  score.
- Missing or hidden user identifiers must remain missing.

## Output

Separate observations from inference. Include the sample size, pagination
coverage and all limitations whenever producing aggregate counts.

