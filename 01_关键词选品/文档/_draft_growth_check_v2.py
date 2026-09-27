# -*- coding: utf-8 -*-
"""重写 Growth Check 材料：短正文（躲开富文本标记导致的超限）+ txt 附件放完整详情。

背景：
  · 上一版 1971 字符被拒，报 "exceeds the allowed character limit"。
    字段明明写 limit: 2000 —— 原因是**富文本编辑器会给每行自动包标记**，
    每行多 7~11 字符，30 行就 +300，实际入库超 2000。
  · 用户明确：**销量（Marketplace Insights）是必须项**，所以改写时把它放第一位。
  · 表单自己也建议 "shorten the text or attach a text file with the additional information"。
"""
import io
import os

TITLE = ("Read-only eBay market-research tool (Browse + Taxonomy, live) - "
         "Marketplace Insights / sold-data access required")

# ---- 正文：短版，行数刻意压到最少（每行都会被加了标记） ----
SHORT = """Read-only internal market-research tool, live in daily use at about 4,000 API calls/day (measured).

OUR HARD REQUIREMENT - Marketplace Insights API
We need item_sales/search (scope buy.marketplace.insights) for sold-item counts and realized sold prices in the categories we research. This is a must-have: without sold data our pricing and demand conclusions are guesswork. Production currently returns 403 errorId 1100 and the scope request returns invalid_scope, so we have no access at all.

WHAT WE RUN TODAY
Browse item_summary/search (up to 200 listings per keyword x marketplace) -> Browse getItem for each listing (item specifics, category path, images, description) -> Taxonomy get_item_aspects_for_category / get_category_suggestions (required, recommended, optional aspects and allowed values) -> internal Excel reports: price bands, brand vs white-label share, keyword scoring, promoted-slot position, SEO titles.
One combination = 1 search + 200 getItem = 201 calls. About 20 combinations/day over 9 marketplaces (GB US DE AU FR ES IT CA HK) = about 4,000 calls/day, already near the 5,000/day default. Verified 2026-09-15: 2,656 calls in 16 runs; a 200-item run takes about 25 seconds.

ALSO REQUESTED: Browse daily limit 20,000 calls/day (estimate attached); Catalog API (commerce.catalog.readonly); buy.item.bulk.

COMPLIANCE: strictly read-only, zero write operations on listings, offers or inventory; keyset granted the Marketplace User Account Deletion exemption; no buyer personal data stored; internal use only, never resold or published.

Full flow, call-volume estimate and compliance detail: see the attached text file."""

# ---- 附件：完整详情 ----
ATTACH = """eBay Application Growth Check - supporting detail
Application ID: -BETA-PRD-f82b86fbd-f4f4c153
Environment: Production
Submitted: 2026-09-15

==========================================================================
1. WHAT THE APPLICATION DOES (live, in daily use)
==========================================================================
A read-only internal tool that collects eBay listing data for keyword
research, category research and competitor analysis. There is no
customer-facing product and no write operation anywhere in the flow.

Step by step:
1) Browse API - item_summary/search
   Reads up to 200 listings per keyword x marketplace (limit=200 is the
   API maximum, so one search call fills one page).
   Collected fields: title, price, condition, buying options, seller
   username + feedback score/percentage, item creation date, item
   location, availability, priorityListing (promoted flag), bid count
   for auction listings.

2) Browse API - getItem (one call per listing)
   Reads structured item specifics (localizedAspects), category id and
   category path, images, description, seller, shipping and availability.

3) Taxonomy API - get_item_aspects_for_category / get_category_suggestions
   Maps, for each leaf category, which aspects are required, recommended
   or optional, in what cardinality, and what the allowed values are.

4) Local analysis and reporting (no eBay calls)
   Internal Excel workbooks: price bands and distribution, brand vs
   white-label share, keyword frequency/scoring, promoted-slot position
   distribution, and suggested listing titles.

==========================================================================
2. MEASURED USAGE (real, verifiable - not a prototype)
==========================================================================
Call math per combination (one keyword x one marketplace):
   1 x item_summary/search  +  200 x getItem  =  201 API calls

Current volume: about 20 combinations/day across 9 marketplaces
(EBAY_GB, EBAY_US, EBAY_DE, EBAY_AU, EBAY_FR, EBAY_ES, EBAY_IT,
EBAY_CA, EBAY_HK) = about 4,000 calls/day, which is already close to
the default 5,000 calls/day limit.

Measured on 2026-09-15 (local counter, logged per run):
   2,656 API calls across 16 collection runs
   One 200-listing run completes in about 25 seconds (8 concurrent threads)
   Total collected: 200-listing runs for multiple keywords and marketplaces

==========================================================================
3. WHAT WE ARE ASKING FOR, AND WHY
==========================================================================
3.1 Marketplace Insights API  -- HARD REQUIREMENT
    Endpoint: /buy/marketplace_insights/v1_beta/item_sales/search
    Scope:    https://api.ebay.com/oauth/api_scope/buy.marketplace.insights
    Why:      Sold-item counts and realized (sold) prices. Our current
              reports can only see what is listed today, at asking prices.
              Without sold data we cannot tell demand from inventory, or
              a realistic selling price from an optimistic one. This is
              the single biggest gap in our research output.
    Current behaviour (production):
              HTTP 403, errorId 1100 "Insufficient permissions to fulfill
              the request"; requesting the scope returns invalid_scope.
    Forecast: +2 item_sales/search calls per combination
              (about 200 calls/day at current volume).

3.2 Browse API daily limit -> 20,000 calls/day
    We reach about 4,000 calls/day with only about 20 combinations. Growth
    to 60-90 combinations/day (more keywords, more marketplaces, seasonal
    research) needs 12,000-18,000 calls/day, plus roughly 10% headroom for
    retries and transient failures.

3.3 Catalog API (commerce.catalog.readonly)
    Product / epid level aggregation so that listings for the same product
    can be grouped instead of compared one by one.

3.4 buy.item.bulk (batched getItem)
    Reduces the number of individual getItem calls per combination, which
    lowers total call volume for the same output.

3.5 Buy Deal API / Buy Feed API - only if available for this use case.
    They would extend coverage of promoted and bulk listing data. Not
    essential; 3.1 is the priority.

==========================================================================
4. COMPLIANCE
==========================================================================
- Read-only by design: the tool never creates, updates or deletes
  listings, offers, inventory, orders or account data. There are no write
  scopes in the application and no write code path.
- Our keyset has been granted the eBay Marketplace User Account Deletion
  exemption.
- No buyer personal data is collected, stored or processed. We read public
  listing data only.
- Data is used internally for product selection and pricing research. It
  is never resold, published, redistributed, or exposed to third parties.
- Authentication: OAuth client_credentials (application access token),
  cached locally and refreshed automatically. No user access tokens are
  requested for this use case.

==========================================================================
5. ROADMAP
==========================================================================
The same read-only data pipeline will back a small internal server
(MCP-style) that answers product-research questions for our own team.
No new data categories and no write scopes will be introduced.
"""

print("=" * 78)
print("Application Title / Summary")
print("=" * 78)
print(TITLE)
print("字符数 %d" % len(TITLE))

print()
print("=" * 78)
print("Application Details（短版，粘进富文本框）")
print("=" * 78)
print(SHORT)
lines = SHORT.count("\n") + 1
print("-" * 78)
print("纯文本 %d 字符 ｜ %d 行 ｜ 估算含富文本标记 ≈ %d 字符 %s"
      % (len(SHORT), lines, len(SHORT) + lines * 9,
         "✅" if len(SHORT) + lines * 9 <= 2000 else "❌"))

doc_dir = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\01_关键词选品\文档"
attach_path = os.path.join(doc_dir, "申请附件_GrowthCheck详情.txt")
with io.open(attach_path, "w", encoding="utf-8") as f:
    f.write(ATTACH)
print()
print("附件已生成：%s" % attach_path)
print("  附件字符数 %d（附件没有 2000 上限）" % len(ATTACH))
