# -*- coding: utf-8 -*-
"""起草 Application Growth Check 申请文案，并卡 2000 字符上限。

约束（来自表单上方原文，很重要）：
  · "We cannot approve applications which are in beta or do not have any usage."
  · 需订阅 Marketplace User Account Deletion 通知
  · 需提供 application purpose and flow / application URL / forecasted daily API usage
  · 每日默认额度 5,000 次；要提额必须走这个流程
"""
import io
import os

TITLE = ("eBay keyword research tool - read-only Browse + Taxonomy collector "
         "for internal product selection (live, ~4,000 calls/day)")

DETAILS = """WHAT IT DOES - live internal tool, in daily use
Read-only collector for keyword research and competitor analysis:
1) Browse item_summary/search - up to 200 listings per keyword x marketplace (1 call per combination).
2) Browse getItem - item specifics, category path, images, description for every listing (200 calls per combination).
3) Taxonomy get_item_aspects_for_category / get_category_suggestions - required, recommended and optional aspects plus allowed values per leaf category.
4) Output: internal Excel reports - price bands, brand vs white-label share, keyword scoring, promoted (ad-slot) position distribution, SEO titles.

MEASURED USAGE - live, not beta
- 1 combination = 1 search + 200 getItem = 201 calls.
- ~20 combinations/day over 9 marketplaces (GB US DE AU FR ES IT CA HK) = ~4,000 calls/day, already near the default 5,000/day limit.
- Verified today: 2,656 calls in 16 runs; one 200-item run takes ~25s.

REQUESTED
1) Browse API daily limit raised to 20,000 calls/day. We reach 4,000/day with only ~20 combinations; retries and seasonal keyword growth need headroom.
2) Marketplace Insights API (buy.marketplace.insights, item_sales/search) - to add sold-item / realized-price data to the same reports. Production currently returns 403 errorId 1100 and the scope request returns invalid_scope.
3) Catalog API (commerce.catalog.readonly) - product/epid-level aggregation.
4) buy.item.bulk (batched getItem); Buy Deal / Buy Feed if available.

COMPLIANCE
- Strictly read-only: never creates, updates or deletes listings, offers, inventory or account data. Zero write operations.
- Keyset already granted the Marketplace User Account Deletion exemption; no buyer personal data stored or processed.
- Data used internally for product selection / pricing research only - not resold, published or redistributed.
- Auth: client_credentials application token.

ROADMAP: same read-only pipeline will back a small internal MCP-style server for our own team."""

print("=" * 78)
print("Application Title / Summary（直接粘这一行）")
print("=" * 78)
print(TITLE)
print("字符数: %d" % len(TITLE))
print()
print("=" * 78)
print("Application Details（直接粘，注意 2000 字符上限）")
print("=" * 78)
print(DETAILS)
print("-" * 78)
print("字符数: %d / 2000  %s" % (len(DETAILS), "✅ 在限内" if len(DETAILS) <= 2000 else "❌ 超了"))

out = os.path.join(os.environ["TEMP"], "growth_check_application.txt")
with io.open(out, "w", encoding="utf-8") as f:
    f.write("TITLE:\n%s\n\nDETAILS:\n%s\n" % (TITLE, DETAILS))
print("\n已存一份到 %s（方便复制）" % out)
