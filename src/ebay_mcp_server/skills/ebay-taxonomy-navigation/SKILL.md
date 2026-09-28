---
name: ebay-taxonomy-navigation
description: Resolves eBay category trees, category suggestions, and item aspects. Use when identifying a category or determining required, recommended, optional, single-value, or selection-only attributes.
---

# eBay Taxonomy Navigation

## Workflow

1. Determine the target `marketplace_id`.
2. Call `ebay_get_default_category_tree` unless a verified tree ID is supplied.
3. Call `ebay_suggest_categories` with the product phrase.
4. Keep the returned category IDs and category names together.
5. Call `ebay_get_category_aspects` for the chosen leaf category.
6. Report required and constrained aspects separately.

## Interpretation rules

- `aspectRequired=true` is a hard listing requirement.
- `aspectUsage` expresses eBay recommendation level; it does not replace
  `aspectRequired`.
- `aspectMode=SELECTION_ONLY` means the value must come from eBay's allowed
  values.
- Respect `itemToAspectCardinality`; do not collapse multi-value aspects.
- Category IDs are Marketplace-specific. Never reuse a category solely because
  its name looks similar on another Marketplace.

## Boundaries

This skill identifies official taxonomy metadata. It does not choose products,
publish listings, or fabricate missing item specifics.

