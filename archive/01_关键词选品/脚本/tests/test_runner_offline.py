# -*- coding: utf-8 -*-
"""壳程序入口的离线单测：多关键词/多站点拆分、日志 tee、文件名口径。

这些是从真实 bug 长出来的：
  `--keyword "wireless earbuds"` 被按空格拆成两个关键词，
  产物变成 wireless_..._uk.xlsx + earbuds_..._uk.xlsx —— 多词关键词是常态，
  绝不能按空格拆。
"""

import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import run_keyword_research as R  # noqa: E402


class KeywordSplitTests(unittest.TestCase):
    def test_multiword_keyword_is_one_keyword(self):
        self.assertEqual(R._split_keywords("wireless earbuds"), ["wireless earbuds"])

    def test_comma_separated(self):
        self.assertEqual(R._split_keywords("wireless earbuds,phone case"),
                         ["wireless earbuds", "phone case"])

    def test_chinese_comma_and_semicolon(self):
        self.assertEqual(R._split_keywords("蓝牙耳机，手机壳;充电器"),
                         ["蓝牙耳机", "手机壳", "充电器"])

    def test_extra_spaces_trimmed(self):
        self.assertEqual(R._split_keywords("  a b  ,  c  "), ["a b", "c"])

    def test_empty(self):
        self.assertEqual(R._split_keywords(""), [])
        self.assertEqual(R._split_keywords("  ,  "), [])


class SiteSplitTests(unittest.TestCase):
    def test_comma(self):
        self.assertEqual(R._split_sites("uk,us,de"), ["uk", "us", "de"])

    def test_space(self):
        self.assertEqual(R._split_sites("uk us de"), ["uk", "us", "de"])

    def test_upper_is_lowered(self):
        self.assertEqual(R._split_sites("UK, US"), ["uk", "us"])

    def test_mixed_separators(self):
        self.assertEqual(R._split_sites("uk, us de"), ["uk", "us", "de"])

    def test_empty(self):
        self.assertEqual(R._split_sites(""), [])


class TeeTests(unittest.TestCase):
    def test_writes_to_both_stdout_and_file(self):
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "log.txt")
        real = sys.stdout
        buf = io.StringIO()
        try:
            sys.stdout = buf
            with R._tee_console(p):
                print("第一行")
                print("第二行")
        finally:
            sys.stdout = real
        self.assertIn("第一行", buf.getvalue())
        with io.open(p, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("第一行", content)
        self.assertIn("第二行", content)

    def test_stdout_restored_after_exception(self):
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "log.txt")
        real = sys.stdout
        try:
            with self.assertRaises(ValueError):
                with R._tee_console(p):
                    raise ValueError("boom")
        finally:
            restored = sys.stdout
            sys.stdout = real
        self.assertIs(restored, real, "异常后也必须把 stdout 还原")

    def test_empty_path_is_noop(self):
        real = sys.stdout
        with R._tee_console(""):
            pass
        self.assertIs(sys.stdout, real)


class OutputNamingTests(unittest.TestCase):
    def test_filename_is_keyword_time_site(self):
        """文件名口径：关键词 + 时间 + 站点（用户明确要求）。"""
        import re
        from unittest import mock
        tmp = tempfile.mkdtemp()

        report = {
            "keyword": "wireless earbuds", "site": "uk", "mode": "api",
            "items": [], "recommended_titles": [], "specifics": [],
            "price": {}, "category": {}, "titles_exact": [], "titles_tokens": [],
            "market": {},
        }
        with mock.patch.object(R, "output_dir", return_value=tmp):
            xlsx = R.export_report(report, store="api", out_dir=tmp)
        name = os.path.basename(xlsx)
        self.assertRegex(name, r"^wireless_earbuds_\d{8}_\d{6}_uk\.xlsx$")
        self.assertTrue(os.path.isfile(xlsx))
        self.assertTrue(os.path.isfile(os.path.join(tmp, name.replace(".xlsx", ".json"))))


class InvisibleCharTests(unittest.TestCase):
    """复制粘贴带进来的隐形字符必须清掉。

    真实事故：从 Excel/聊天窗口粘贴的关键词会带 U+FEFF(BOM) 或 U+200B(零宽空格)，
    Python 的 `str.strip()` **不去掉**它们（不属于 Unicode 空白属性），
    于是"空关键词"变成"1 个隐形关键词"，参数确认里显示"关键词 : ﻿（1 个）"
    肉眼看不见，一路跑到 eBay 才报 HTTP 400 errorId 12023。
    """

    def test_bom_only_is_not_a_keyword(self):
        self.assertEqual(R._split_keywords("\ufeff"), [])
        self.assertEqual(R._clean_query("\ufeff"), "")

    def test_bom_prefixed_keyword_is_cleaned(self):
        self.assertEqual(R._split_keywords("\ufeffwireless earbuds"), ["wireless earbuds"])

    def test_zero_width_space_removed(self):
        self.assertEqual(R._split_keywords("wireless\u200b earbuds"), ["wireless earbuds"])

    def test_non_breaking_space_treated_as_whitespace(self):
        self.assertEqual(R._clean_query("wireless\xa0earbuds"), "wireless earbuds")

    def test_runs_of_whitespace_collapsed(self):
        self.assertEqual(R._clean_query("  wireless   earbuds  "), "wireless earbuds")

    def test_word_joiner_removed(self):
        self.assertEqual(R._clean_query("ear\u2060buds"), "earbuds")

    def test_sites_also_cleaned(self):
        self.assertEqual(R._split_sites("\ufeffuk, us"), ["uk", "us"])

    def test_none_is_safe(self):
        self.assertEqual(R._clean_query(None), "")


class LongCellClipTests(unittest.TestCase):
    """超长单元格必须截断 —— 否则 openpyxl 每条都吐警告，bat 日志被刷爆。

    真实事故：eBay 的 description 是整页 HTML（最长 310,582 字符），超过 Excel
    单元格上限 32767。第一版用 `dtype == object` 判断字符串列，但
    **pandas 3.0 起字符串列 dtype 变成 `str`**（共享目录运行时就是 3.0.3），
    判断失效 → 警告照旧。所以这里同时测 object 与 pandas 的 string dtype。
    """

    def test_clips_object_dtype_column(self):
        import pandas as pd
        long_html = "x" * 40000
        df = R._clip_long_cells(pd.DataFrame({"description": [long_html, "short"]}))
        self.assertLessEqual(len(df["description"].iloc[0]), R.EXCEL_CELL_MAX + 60)
        self.assertIn("已截断", df["description"].iloc[0])
        self.assertIn("40000", df["description"].iloc[0])
        self.assertEqual(df["description"].iloc[1], "short")

    def test_clips_pandas_string_dtype_column(self):
        """pandas 3.0 默认的 `str` dtype（用 StringDtype 等价模拟）。"""
        import pandas as pd
        df = pd.DataFrame({"description": pd.array(["y" * 40000], dtype="string")})
        out = R._clip_long_cells(df)
        self.assertIn("已截断", out["description"].iloc[0])

    def test_leaves_non_string_columns_alone(self):
        import pandas as pd
        df = R._clip_long_cells(pd.DataFrame({"price": [1.5, 2.5], "n": [1, 2]}))
        self.assertEqual(list(df["price"]), [1.5, 2.5])
        self.assertEqual(list(df["n"]), [1, 2])

    def test_short_strings_untouched(self):
        import pandas as pd
        df = R._clip_long_cells(pd.DataFrame({"t": ["a normal title"]}))
        self.assertEqual(df["t"].iloc[0], "a normal title")

    def test_empty_and_na_safe(self):
        import pandas as pd
        import numpy as np
        df = R._clip_long_cells(pd.DataFrame({"t": [None, np.nan, ""]}))
        self.assertEqual(len(df), 3)


class MenuOrderTests(unittest.TestCase):
    """交互顺序：**先选站点，再填关键词**（用户明确要求）。

    这条顺序是产品要求，不是实现细节，所以用脚本化输入把它钉住：
    记录提示语出现的先后，并断言传给主程序的关键词/站点都对。
    """

    def _drive(self, answers):
        """按脚本喂输入，返回 (提示语顺序, 实际传给 _run 的参数)。"""
        import builtins
        import kw_menu as M

        asked, calls = [], {}

        def fake_input(prompt=""):
            asked.append(prompt)
            if not answers:
                raise EOFError
            return answers.pop(0)

        def fake_run(kws, sites):
            calls["kws"] = kws
            calls["sites"] = sites
            return 0

        real_input, real_run, real_summary = builtins.input, M._run, M._summary
        builtins.input = fake_input
        M._run = fake_run
        M._summary = lambda rc: None
        try:
            sys.argv = ["kw_menu.py"]
            M.main([])
        finally:
            builtins.input = real_input
            M._run = real_run
            M._summary = real_summary
        return asked, calls

    def test_sites_are_asked_before_keywords(self):
        asked, calls = self._drive(["1", "wireless earbuds", "y", "n"])
        self.assertIn("站点编号: ", asked, "应该问站点")
        self.assertIn("关键词: ", asked, "应该问关键词")
        self.assertLess(asked.index("站点编号: "), asked.index("关键词: "),
                        "站点必须在关键词之前问")
        self.assertEqual(calls["sites"], ["uk"])
        self.assertEqual(calls["kws"], ["wireless earbuds"])

    def test_multi_site_multi_keyword(self):
        asked, calls = self._drive(["1 2", "wireless earbuds,phone case", "y", "n"])
        self.assertEqual(calls["sites"], ["uk", "us"])
        self.assertEqual(calls["kws"], ["wireless earbuds", "phone case"])

    def test_blank_keyword_reasks_before_running(self):
        asked, calls = self._drive(["1", "", "wireless earbuds", "y", "n"])
        self.assertEqual(calls["kws"], ["wireless earbuds"])
        # 空关键词后应该又出现一次关键词提示
        self.assertEqual(asked.count("关键词: "), 2)

    def test_all_sites_option(self):
        asked, calls = self._drive(["a", "earbuds", "y", "n"])
        self.assertEqual(len(calls["sites"]), 9)

    def test_s_switches_sites_keeping_keyword_flow(self):
        asked, calls = self._drive(["1", "earbuds", "y", "s", "2", "charger", "y", "n"])
        self.assertEqual(calls["sites"], ["us"], "换站点后应该用新站点再跑一次")
        self.assertEqual(calls["kws"], ["charger"])

    def test_bad_site_number_reasks(self):
        asked, calls = self._drive(["9 99", "1", "earbuds", "y", "n"])
        self.assertEqual(calls["sites"], ["uk"])
        self.assertGreaterEqual(asked.count("站点编号: "), 2)

    def test_q_quits_without_running(self):
        asked, calls = self._drive(["q"])
        self.assertEqual(calls, {})


class ApiUsageCounterTests(unittest.TestCase):
    """当日 API 用量计数。

    为什么要自己记：eBay **不提供额度查询** ——
    Browse API 响应头里没有任何 rate-limit 字段（实测打过完整响应头），
    官方 getRateLimits 接口在公网全 404。所以额度只能去后台看，或者自己记账。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_accumulates_within_same_day(self):
        d1 = R._record_api_usage({"search": 1, "getItem": 200, "token": 1}, self.tmp)
        self.assertEqual(d1["计费请求"], 201)
        self.assertEqual(d1["token"], 1, "token 要单独记，它不占 Browse 额度")
        d2 = R._record_api_usage({"search": 1, "getItem": 200}, self.tmp)
        self.assertEqual(d2["计费请求"], 402)
        self.assertEqual(d2["运行段数"], 2)

    def test_persisted_to_file(self):
        import json as _json
        R._record_api_usage({"search": 1, "getItem": 50}, self.tmp)
        path = os.path.join(self.tmp, R.USAGE_FILE)
        self.assertTrue(os.path.isfile(path))
        with io.open(path, encoding="utf-8") as f:
            data = _json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(list(data.values())[0]["计费请求"], 51)

    def test_unknown_call_kinds_counted_as_other(self):
        d = R._record_api_usage({"search": 1, "getItem": 10, "item_sales": 3}, self.tmp)
        self.assertEqual(d["其他"], 3)
        self.assertEqual(d["计费请求"], 14)

    def test_corrupt_file_does_not_crash(self):
        path = os.path.join(self.tmp, R.USAGE_FILE)
        with io.open(path, "w", encoding="utf-8") as f:
            f.write("{ 这不是 json")
        d = R._record_api_usage({"search": 1, "getItem": 1}, self.tmp)
        self.assertEqual(d["计费请求"], 2)


if __name__ == "__main__":
    unittest.main()
