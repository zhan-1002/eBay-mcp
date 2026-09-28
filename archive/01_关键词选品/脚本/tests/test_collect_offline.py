# -*- coding: utf-8 -*-
"""采集段离线单测：价格解析、title 清理、占位卡判定。

都不联网、不用紫鸟，跑法：
  python tests/test_collect_offline.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCHIVE = os.path.normpath(os.path.join(ROOT, "..", "99_归档", "紫鸟采集_20260915", "脚本"))
for p in (ROOT, ARCHIVE):
    if p not in sys.path:
        sys.path.insert(0, p)

# collect_ziniao 已归档（紫鸟链路封存），从归档目录导入
from collect_ziniao import (  # noqa: E402
    DEAD_PATTERNS, PLACEHOLDER_TITLES, clean_listing_title, parse_price_display,
)

class PriceParseTests(unittest.TestCase):
    """2026-09-14 真机实测到的价格原文形态。"""

    def test_range_with_unit_suffix(self):
        lo, hi, cur, disp = parse_price_display("\u00a321.97 to \u00a322.97(\u00a321.97/Unit)")
        self.assertEqual((lo, hi, cur), (21.97, 22.97, "\u00a3"))

    def test_single_with_unit_suffix(self):
        lo, hi, cur, _ = parse_price_display("\u00a313.99(\u00a313.99/Unit)")
        self.assertEqual((lo, hi, cur), (13.99, 13.99, "\u00a3"))

    def test_us_range(self):
        lo, hi, cur, _ = parse_price_display("US $10.99 to $19.99")
        self.assertEqual((lo, hi, cur), (10.99, 19.99, "US $"))

    def test_best_offer_suffix(self):
        lo, hi, _, _ = parse_price_display("$20.00 or Best Offer")
        self.assertEqual((lo, hi), (20.0, 20.0))

    def test_european_decimal_comma(self):
        # 旧实现把 "," 一律删掉 -> 1299，会把欧陆站点价格放大 100 倍
        lo, hi, cur, _ = parse_price_display("EUR 12,99")
        self.assertEqual((lo, hi, cur), (12.99, 12.99, "EUR"))

    def test_european_thousand_separator(self):
        lo, hi, cur, _ = parse_price_display("\u20ac1.234,56")
        self.assertEqual((lo, hi, cur), (1234.56, 1234.56, "\u20ac"))

    def test_empty_and_free(self):
        self.assertEqual(parse_price_display("")[0], None)
        self.assertEqual(parse_price_display("Free")[0], None)


class TitleCleanTests(unittest.TestCase):
    """卡片标题尾部带 eBay 的 a11y 提示文本（真机每张卡都有）。"""

    def test_strip_a11y_tail(self):
        raw = ("TWS Wireless Earbuds Bluetooth 5.5 Earphones 4 ENC Mics IP7 "
               "For Android & iPhone\nOpens in a new window or tab")
        self.assertEqual(
            clean_listing_title(raw),
            "TWS Wireless Earbuds Bluetooth 5.5 Earphones 4 ENC Mics IP7 For Android & iPhone")

    def test_strip_shorter_variant(self):
        self.assertEqual(clean_listing_title("Some Earbuds Opens in a new window"),
                         "Some Earbuds")

    def test_untouched_when_no_tail(self):
        self.assertEqual(clean_listing_title("Plain Title Without Tail"),
                         "Plain Title Without Tail")


class SkipRuleTests(unittest.TestCase):
    def test_placeholder_rule(self):
        self.assertIn("shop on ebay", {t.lower() for t in PLACEHOLDER_TITLES})

    def test_dead_listing_rule(self):
        text = "This listing was ended by the seller because the item is no longer available."
        self.assertTrue(any(p in text.lower() for p in DEAD_PATTERNS))


class MarketSheetTests(unittest.TestCase):
    """合表导出：dict 行必须按显式列序展开。

    踩过的坑：把 dict 直接交给 write_sections，迭代出来是**键**，
    整段被写成 N 行表头（实测价格段/品牌占位各 7 行全是表头）。
    """

    def _mod(self):
        import run_keyword_research as rk
        return rk

    def test_to_rows_maps_dict_by_explicit_keys(self):
        rk = self._mod()
        data = [{"价格段": "0-5", "下限": 0, "商品数": 10},
                {"价格段": "5-8", "下限": 5, "商品数": 16}]
        rows = rk.to_rows(data, ["价格段", "下限", "上限", "商品数"])
        self.assertEqual(rows[0], ["0-5", 0, None, 10])
        self.assertEqual(rows[1], ["5-8", 5, None, 16])

    def test_write_sections_puts_data_not_header(self):
        import openpyxl
        rk = self._mod()
        wb = openpyxl.Workbook()
        ws = wb.active
        data = [{"价格段": "0-5", "商品数": 10}, {"价格段": "5-8", "商品数": 16}]
        rk.write_sections(ws, [
            ("一、价格区间", ["价格段", "商品数"], rk.to_rows(data, ["价格段", "商品数"])),
        ])
        self.assertEqual(ws.cell(row=2, column=1).value, "价格段")
        self.assertEqual(ws.cell(row=3, column=1).value, "0-5")
        self.assertEqual(ws.cell(row=3, column=2).value, 10)
        self.assertEqual(ws.cell(row=4, column=1).value, "5-8")

    def test_price_bands_are_fixed_integer_edges(self):
        import report_market as rm
        self.assertEqual(rm.PRICE_BANDS[:3], [0, 5, 8])
        self.assertEqual(rm.PRICE_BAND_LABELS[0], "0-5")
        self.assertEqual(rm.PRICE_BAND_LABELS[-1], "20+")
        rows, stat = rm.build_price_table(
            [{"price": p} for p in (3, 6, 9, 11, 14, 18, 25)])
        self.assertEqual([r["商品数"] for r in rows], [1, 1, 1, 1, 1, 1, 1])
        self.assertEqual(rows[-1]["上限"], None)
        # n=7 时 p50 取 int(0.5*7)-1 = 2 号元素（降序索引下的中位写法）
        self.assertEqual(stat["p50"], 9)
        self.assertEqual(stat["min"], 3)
        self.assertEqual(stat["max"], 25)

    def test_brand_barrier_occupancy(self):
        import report_market as rm
        items = [{"price": 3, "title": "sony buds"}, {"price": 4, "title": "cheap buds"}]
        rows, summary, spec_rows, band_rows = rm.brand_barrier(
            items, [i["title"] for i in items], [], {"sony"})
        self.assertEqual(rows[0]["品牌词"], "sony")
        self.assertEqual(rows[0]["标题开头占位"], 1)
        first_band = [b for b in band_rows if b["价格带"] == "0-5"][0]
        self.assertEqual(first_band["商品数"], 2)
        self.assertEqual(first_band["带品牌词条数"], 1)
        self.assertEqual(first_band["品牌占位率%"], 50.0)


if __name__ == "__main__":
    unittest.main()
