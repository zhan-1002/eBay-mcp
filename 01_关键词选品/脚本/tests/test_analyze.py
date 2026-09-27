# -*- coding: utf-8 -*-
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analyze import (
    TITLE_MAX, build_report, exact_title_freq, generate_titles,
    merge_values, price_bands, tokenize,
)


class AnalyzeTests(unittest.TestCase):
    def test_keep_duplicate_titles(self):
        freq = exact_title_freq(["Red Cup", "Red Cup", "Blue Cup"])
        self.assertEqual(freq["Red Cup"], 2)
        self.assertEqual(freq["Blue Cup"], 1)

    def test_merge_handwritten_values(self):
        groups = merge_values(["Brand New", "brand-new", "brand new", "Used"])
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["count"], 3)

    def test_price_bands(self):
        items = [{"price": p, "currency": "USD"} for p in (10, 12, 15, 20, 40)]
        band = price_bands(items)
        self.assertEqual(band["count"], 5)
        self.assertEqual(band["min"], 10)
        self.assertEqual(band["max"], 40)
        self.assertEqual(band["suggest_price"], band["p50"])

    def test_generate_at_least_20_titles(self):
        titles = [
            "Sony WH-1000XM5 Wireless Noise Canceling Headphones Black",
            "Sony WH-1000XM5 Wireless Headphones Silver",
            "Bose QuietComfort Ultra Wireless Headphones Blue",
        ] * 8
        items = []
        for i, t in enumerate(titles, 1):
            items.append({
                "position": i,
                "title": t,
                "price": 200 + i,
                "currency": "USD",
                "is_sponsored": i <= 2,
                "leaf_category_ids": ["15032", "293"] if i == 1 else ["15032"],
                "categories": [{"id": "15032", "name": "Headphones"}],
                "item_specifics": [
                    {"name": "Brand", "value": "Sony" if "Sony" in t else "Bose"},
                    {"name": "Colour", "value": "Black" if "Black" in t else "Blue"},
                    {"name": "Type", "value": "Over-Ear"},
                ] if i <= 10 else [],
            })
        report = build_report("wireless headphones", "us", items, recommend_n=20, specifics_n=10)
        self.assertGreaterEqual(len(report["recommended_titles"]), 20)
        self.assertTrue(all(len(t) <= TITLE_MAX for t in report["recommended_titles"]))
        self.assertEqual(report["category"]["recommend_leaf_id"], "15032")
        self.assertGreaterEqual(report["category"]["dual_category_count"], 1)
        self.assertGreaterEqual(report["ad_count"], 2)
        self.assertTrue(any(s["name"].lower() == "brand" for s in report["specifics"]))

    def test_tokenize_skips_stopwords(self):
        tokens = tokenize("The Best Cup for Tea and Coffee")
        self.assertNotIn("the", tokens)
        self.assertIn("best", tokens)
        self.assertIn("cup", tokens)


if __name__ == "__main__":
    unittest.main()
