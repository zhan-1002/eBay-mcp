---
name: ebay-title-generation
description: Produces exactly 30 compliant English eBay listing title candidates from verified product facts and optional competitor evidence. Use when the user asks for eBay titles, listing title variants, or a 30-title deliverable.
---

# Generate 30 eBay Titles

## Scope

Generate title candidates only. Do not select products, estimate sales, publish
or modify a listing. Use verified product facts; never invent a feature,
material, size, certification, compatibility claim or model number.

## Inputs

Require:

- target Marketplace;
- core product phrase;
- verified product attributes and compatibility facts.

Competitor titles are optional evidence. If evidence is absent and the user
authorizes retrieval, use `ebay_search_items` and selected `ebay_get_item`
calls. Use `ebay_get_category_aspects` when category requirements matter.

## Hard requirements

1. Return exactly 30 non-empty English titles.
2. Every title must be at most 80 characters including spaces.
3. Do not use commas, semicolons, vertical bars or unsupported punctuation.
   `&`, `-` and `.` are allowed.
4. A title must not repeat the same case-insensitive word.
5. Titles must be unique and materially different, not simple word reordering.
6. Remove competitor brands used as the product's own brand.
7. Remove competitor model identifiers such as PRO4, LP40 or A6S.
8. Compatibility wording such as `for iPhone` is allowed only when the
   supplied product facts support it.
9. High-frequency competitor titles may contribute only a compliant cleaned
   version; prohibited brands and models are never preserved.
10. Do not add facts that are absent from the verified inputs.

## Quality targets

- Prefer 70 to 80 characters without filler.
- Put the core product phrase or strongest verified term within the first
  30 characters.
- Use natural eBay buyer language instead of a keyword bag.
- Vary real functions, specifications, compatible devices and use scenarios.

## Workflow

1. Separate verified facts from competitor language and assumptions.
2. Build an explicit forbidden-term list for competitor brands and models.
3. Generate more than 30 candidates.
4. Call `ebay_validate_titles` with the candidates and forbidden terms.
5. Rewrite only failed candidates, then validate again.
6. Stop only when `valid_for_delivery=true`.

## Output

Return:

- `titles`: the final 30 titles in ranked order;
- `validation`: the complete `ebay_validate_titles` result;
- `assumptions`: normally empty; unresolved facts must not enter titles;
- `excluded_terms`: competitor brands and model identifiers removed.

