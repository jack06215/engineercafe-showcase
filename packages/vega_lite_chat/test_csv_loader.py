"""Tests for csv_loader.py and the bundled samples (samples.py)."""

import unittest

import pandas

from packages.vega_lite_chat.csv_loader import (
    NOT_UTF8,
    InputError,
    load_csv,
)
from packages.vega_lite_chat.samples import (
    SAMPLES,
    sample_named,
)


def _load(text: str) -> pandas.DataFrame:
    return load_csv(text.encode("utf-8"))


def _is_dates(series: pandas.Series) -> bool:
    return pandas.api.types.is_datetime64_any_dtype(series)


class EncodingTest(unittest.TestCase):
    def test_utf8_without_bom(self) -> None:
        df = _load("名前,値\nあ,1\n")
        self.assertEqual(list(df.columns), ["名前", "値"])

    def test_bom_is_stripped_from_the_first_header(self) -> None:
        df = load_csv(b"\xef\xbb\xbf" + "名前,値\nあ,1\n".encode())
        self.assertEqual(list(df.columns), ["名前", "値"])

    def test_cp932_is_rejected(self) -> None:
        with self.assertRaises(InputError) as caught:
            load_csv("名前,値\nあ,1\n".encode("cp932"))
        self.assertEqual(str(caught.exception), NOT_UTF8)


class ShapeTest(unittest.TestCase):
    def test_empty_file(self) -> None:
        with self.assertRaises(InputError):
            load_csv(b"")

    def test_blank_header_row(self) -> None:
        with self.assertRaises(InputError):
            load_csv(b"\n\n")

    def test_header_without_rows(self) -> None:
        with self.assertRaisesRegex(InputError, "データの行がありません"):
            _load("月,売上\n")

    def test_duplicate_headers_are_named(self) -> None:
        with self.assertRaisesRegex(InputError, "売上"):
            _load("売上,売上,地域\n1,2,福岡\n")

    def test_numbers_are_inferred_and_separators_stay_text(self) -> None:
        df = _load('整数,小数,桁区切り\n1,1.5,"1,234"\n2,2.5,"2,000"\n')
        self.assertTrue(pandas.api.types.is_integer_dtype(df["整数"]))
        self.assertTrue(pandas.api.types.is_float_dtype(df["小数"]))
        self.assertEqual(df["桁区切り"].tolist(), ["1,234", "2,000"])


class DateTest(unittest.TestCase):
    def test_iso_dates(self) -> None:
        for values, first in (
            (["2025-01-05", "2025-02-28"], pandas.Timestamp(2025, 1, 5)),
            (["2025-01", "2025-12"], pandas.Timestamp(2025, 1, 1)),
            (
                ["2025-01-05T10:00", "2025-01-05T11:30"],
                pandas.Timestamp(2025, 1, 5, 10),
            ),
        ):
            with self.subTest(values=values):
                df = _load("日付\n" + "\n".join(values) + "\n")
                self.assertTrue(_is_dates(df["日付"]))
                self.assertEqual(df["日付"][0], first)

    def test_slash_dates(self) -> None:
        for values, first in (
            (["2025/1/5", "2025/01/06"], pandas.Timestamp(2025, 1, 5)),
            (["2016/1", "2016/12"], pandas.Timestamp(2016, 1, 1)),
        ):
            with self.subTest(values=values):
                df = _load("年月\n" + "\n".join(values) + "\n")
                self.assertTrue(_is_dates(df["年月"]))
                self.assertEqual(df["年月"][0], first)

    def test_missing_values_become_nat(self) -> None:
        df = _load("日付,値\n2025-01-05,1\n,2\n")
        self.assertTrue(_is_dates(df["日付"]))
        self.assertTrue(pandas.isna(df["日付"][1]))

    def test_one_non_date_keeps_the_column_as_text(self) -> None:
        df = _load("日付\n2025-01-05\nあした\n")
        self.assertFalse(_is_dates(df["日付"]))
        self.assertEqual(df["日付"].tolist(), ["2025-01-05", "あした"])

    def test_impossible_date_keeps_the_column_as_text(self) -> None:
        df = _load("日付\n2025-13-45\n")
        self.assertFalse(_is_dates(df["日付"]))

    def test_japanese_and_era_dates_stay_text(self) -> None:
        df = _load("日付,和暦\n2025年1月5日,令和7年\n")
        self.assertFalse(_is_dates(df["日付"]))
        self.assertFalse(_is_dates(df["和暦"]))


class SamplesTest(unittest.TestCase):
    def test_every_sample_loads(self) -> None:
        for sample in SAMPLES:
            with self.subTest(sample=sample.file_name):
                df = load_csv(sample.read_bytes())
                self.assertGreater(len(df), 0)

    def test_sales_by_region(self) -> None:
        df = load_csv(sample_named("sales_by_region.csv").read_bytes())
        self.assertEqual(list(df.columns), ["月", "地域", "売上（万円）", "件数"])
        self.assertEqual(len(df), 120)
        self.assertTrue(_is_dates(df["月"]))
        self.assertEqual(
            df["地域"].unique().tolist(), ["福岡", "東京", "大阪", "名古屋", "札幌"]
        )

    def test_stores(self) -> None:
        df = load_csv(sample_named("stores.csv").read_bytes())
        self.assertEqual(
            list(df.columns), ["店舗名", "地域", "床面積（m²）", "月商（万円）"]
        )
        self.assertEqual(len(df), 30)
        self.assertEqual(
            df["地域"].unique().tolist(), ["福岡", "北九州", "久留米", "熊本", "佐賀"]
        )

    def test_unknown_sample(self) -> None:
        with self.assertRaises(KeyError):
            sample_named("nope.csv")


if __name__ == "__main__":
    unittest.main()
