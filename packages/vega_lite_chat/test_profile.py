"""Tests for profile.py."""

import unittest

import numpy
import pandas
import yaml

from packages.vega_lite_chat.profile import (
    DataProfile,
    guess_type,
    plain,
    profile_frame,
    profile_yaml,
)


def _frame() -> pandas.DataFrame:
    return pandas.DataFrame(
        {
            "月": pandas.to_datetime(
                pandas.Series(
                    [
                        "2024-01-01",
                        "2024-02-01",
                        "2024-03-01",
                        "2024-04-01",
                        None,
                        "2024-06-01",
                    ]
                )
            ),
            "地域": ["福岡", "東京", "福岡", "大阪", "東京", "福岡"],
            "店舗名": ["天神店", "銀座店", "博多店", "梅田店", "新宿店", "西新店"],
            "売上（万円）": [320, 500, 410, 280, 610, 390],
            "比率": [0.5, None, 1.5, 2.0, 2.5, 3.0],
            "達成": [True, False, True, True, False, True],
        }
    )


def _profile(sample_rows: int = 3, seed: int = 0) -> DataProfile:
    return profile_frame(
        _frame(), sample_rows=sample_rows, seed=seed, max_listed_values=4
    )


class GuessTest(unittest.TestCase):
    def test_types(self) -> None:
        df = _frame()
        self.assertEqual(guess_type(df["売上（万円）"]), "quantitative")
        self.assertEqual(guess_type(df["比率"]), "quantitative")
        self.assertEqual(guess_type(df["月"]), "temporal")
        self.assertEqual(guess_type(df["地域"]), "nominal")
        self.assertEqual(guess_type(df["達成"]), "nominal")


class PlainTest(unittest.TestCase):
    def test_scalars(self) -> None:
        self.assertEqual(plain(numpy.int64(3)), 3)
        self.assertIsInstance(plain(numpy.int64(3)), int)
        self.assertEqual(plain(numpy.float64(2.5)), 2.5)
        self.assertEqual(plain(3.0), 3)
        self.assertIsNone(plain(float("nan")))
        self.assertIsNone(plain(None))
        self.assertIsNone(plain(pandas.NaT))
        self.assertEqual(plain(pandas.Timestamp(2025, 1, 5)), "2025-01-05")
        self.assertEqual(
            plain(pandas.Timestamp(2025, 1, 5, 10, 30)), "2025-01-05T10:30"
        )
        self.assertEqual(plain(numpy.bool_(True)), "True")
        self.assertEqual(plain("福岡"), "福岡")


class ProfileTest(unittest.TestCase):
    def test_columns(self) -> None:
        profile = _profile()
        self.assertEqual(profile.rows, 6)
        self.assertEqual(
            profile.names(), ("月", "地域", "店舗名", "売上（万円）", "比率", "達成")
        )
        self.assertIsNone(profile.column("ない列"))

    def test_numeric_column(self) -> None:
        column = _profile().column("売上（万円）")
        assert column is not None
        self.assertEqual(
            (column.guess, column.min, column.max), ("quantitative", 280, 610)
        )
        self.assertEqual((column.distinct, column.nulls), (6, 0))
        self.assertIsNone(column.values)
        ratio = _profile().column("比率")
        assert ratio is not None
        self.assertEqual((ratio.min, ratio.max, ratio.nulls), (0.5, 3, 1))

    def test_date_column(self) -> None:
        column = _profile().column("月")
        assert column is not None
        self.assertEqual(column.guess, "temporal")
        self.assertEqual((column.min, column.max), ("2024-01-01", "2024-06-01"))
        self.assertEqual((column.distinct, column.nulls), (5, 1))

    def test_values_are_listed_for_few_categories(self) -> None:
        column = _profile().column("地域")
        assert column is not None
        self.assertEqual(
            column.values, ("福岡", "東京", "大阪")
        )  # first appearance order
        self.assertIsNone(column.min)

    def test_values_are_not_listed_past_the_limit(self) -> None:
        column = _profile().column("店舗名")
        assert column is not None
        self.assertEqual(column.distinct, 6)
        self.assertIsNone(column.values)

    def test_booleans_are_listed_as_text(self) -> None:
        column = _profile().column("達成")
        assert column is not None
        self.assertEqual(column.values, ("True", "False"))

    def test_sample_is_seeded_and_in_file_order(self) -> None:
        first, again = _profile(seed=7), _profile(seed=7)
        self.assertEqual(first.sample, again.sample)
        self.assertEqual(len(first.sample), 3)
        stores = [row["店舗名"] for row in first.sample]
        order = _frame()["店舗名"].tolist()
        self.assertEqual(stores, sorted(stores, key=order.index))

    def test_sample_never_exceeds_the_rows(self) -> None:
        self.assertEqual(len(_profile(sample_rows=50).sample), 6)


class YamlTest(unittest.TestCase):
    def test_japanese_stays_readable(self) -> None:
        text = profile_yaml(_profile())
        self.assertIn("売上（万円）", text)
        self.assertIn("福岡", text)
        self.assertNotIn("\\u", text)

    def test_round_trip(self) -> None:
        document = yaml.safe_load(profile_yaml(_profile()))
        self.assertEqual(document["rows"], 6)
        by_name = {column["name"]: column for column in document["columns"]}
        self.assertEqual(by_name["地域"]["values"], ["福岡", "東京", "大阪"])
        self.assertNotIn("min", by_name["地域"])
        self.assertNotIn("values", by_name["売上（万円）"])
        self.assertEqual(by_name["月"]["min"], "2024-01-01")
        self.assertEqual(len(document["sample"]), 3)


if __name__ == "__main__":
    unittest.main()
