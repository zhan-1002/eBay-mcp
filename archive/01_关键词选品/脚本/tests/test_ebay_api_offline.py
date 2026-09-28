# -*- coding: utf-8 -*-
"""eBay 官方 API 采集段离线单测（不联网）。

重点锁住踩过的坑：类目合并时必须保留搜索侧的第二个叶子类目。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from collect_ebay_api import MARKETPLACE, merge_categories  # noqa: E402


class CategoryMergeTests(unittest.TestCase):
    """实测口径：搜索 leafCategoryIds 可能两个；getItem 只有单 categoryId + 两个 path。"""

    def test_keeps_secondary_category_from_search(self):
        # 这条是核心回归：详情只给 112529，但搜索给了 [112529, 80077]
        leaf, cats, sec, name = merge_categories(
            ["112529", "80077"], "112529",
            "293|15052|112529", "Sound & Vision|Portable Audio & Headphones|Headphones")
        self.assertEqual(leaf, ["112529", "80077"])
        self.assertTrue(sec)
        self.assertEqual(name, "Headphones")

    def test_single_category(self):
        leaf, cats, sec, name = merge_categories(
            ["112529"], "112529",
            "293|15052|112529", "Sound & Vision|Portable Audio & Headphones|Headphones")
        self.assertEqual(leaf, ["112529"])
        self.assertFalse(sec)

    def test_pairs_ids_with_names_by_position(self):
        _, cats, _, _ = merge_categories(
            ["112529"], "112529",
            "293|15052|112529", "Sound & Vision|Portable Audio & Headphones|Headphones")
        self.assertEqual([c["id"] for c in cats], ["293", "15052", "112529"])
        self.assertEqual([c["name"] for c in cats],
                         ["Sound & Vision", "Portable Audio & Headphones", "Headphones"])
        # 末级 name 必须与末级 id 对齐
        self.assertEqual(cats[-1]["id"], "112529")
        self.assertEqual(cats[-1]["name"], "Headphones")

    def test_falls_back_to_detail_when_search_empty(self):
        leaf, _, _, name = merge_categories(
            [], "112529", "293|15052|112529", "Sound & Vision|Portable Audio|Headphones")
        self.assertEqual(leaf, ["112529"])
        self.assertEqual(name, "Headphones")

    def test_appends_detail_leaf_when_search_lacks_it(self):
        # 搜索只给了祖先，详情给了末级 → 末级要补进来
        leaf, _, _, _ = merge_categories(
            ["80077"], "112529", "293|15052|112529", "Sound & Vision|Portable|Headphones")
        self.assertEqual(leaf, ["80077", "112529"])
        self.assertTrue(merge_categories(["80077"], "112529", "", "")[2])

    def test_handles_missing_paths(self):
        leaf, cats, sec, name = merge_categories(["112529"], "112529", None, None)
        self.assertEqual(leaf, ["112529"])
        self.assertEqual(cats, [])
        self.assertFalse(sec)
        self.assertEqual(name, "")


class MarketplaceTests(unittest.TestCase):
    def test_site_map_covers_runner_sites(self):
        from sites import SITES
        missing = [s for s in SITES if s not in MARKETPLACE]
        self.assertEqual(missing, [], "sites.py 里的站点在 API 映射里缺失: %s" % missing)

    def test_gb_us_de_headers(self):
        self.assertEqual(MARKETPLACE["uk"], ("EBAY_GB", "GB", "SW1A1AA"))
        self.assertEqual(MARKETPLACE["us"][0], "EBAY_US")
        self.assertEqual(MARKETPLACE["de"][0], "EBAY_DE")


if __name__ == "__main__":
    unittest.main()
