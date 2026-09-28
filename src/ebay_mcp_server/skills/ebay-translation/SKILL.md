---
name: ebay-translation
description: Translates eBay listing text with the official Translation API. Use when translating an item title or other supported listing text while preserving product facts and compatibility wording.
---

# eBay Translation

## Workflow

1. Confirm source language, target language and translation context.
2. Send one text segment per `ebay_translate_text` call.
3. Use `ITEM_TITLE` for listing titles unless another supported context is
   explicitly required.
4. Preserve model numbers, measurements and compatibility qualifiers.
5. Return the official translation without adding product claims.

## Rules

- Translation does not authorize using a competitor's trademark.
- Do not translate or normalize item IDs, SKUs, model numbers or measurements.
- Do not silently remove safety warnings or compatibility qualifiers.
- If the API rejects a language or context, report the upstream error rather
  than falling back to an unlabelled machine translation.

