"""Tests for the bundled samples (samples.py): they load, and they chart."""

import unittest

import pandas

from packages.vega_lite_chat.samples import (
    SAMPLES,
    sample_named,
)
from packages.vega_lite_core.chart_spec import ChartSpec
from packages.vega_lite_core.compiler import (
    compile_chart,
    vega_lite_errors,
    with_inline_data,
)
from packages.vega_lite_core.csv_loader import load_csv
from packages.vega_lite_core.profile import profile_frame

MONTH = {"field": "月", "type": "temporal", "timeUnit": "yearmonth"}
SALES = {"field": "売上", "type": "quantitative", "aggregate": "sum"}
REGION = {"field": "地域", "type": "nominal"}


def _is_dates(series: pandas.Series) -> bool:
    return pandas.api.types.is_datetime64_any_dtype(series)


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


class InlineDataTest(unittest.TestCase):
    def test_sample_data_round_trips(self) -> None:
        df = load_csv(sample_named("sales_by_region.csv").read_bytes())
        profile = profile_frame(df, sample_rows=3, seed=0, max_listed_values=20)
        spec = ChartSpec.model_validate(
            {
                "mark": "line",
                "x": MONTH,
                "y": {**SALES, "field": "売上（万円）"},
                "color": REGION,
            }
        )
        inline = with_inline_data(compile_chart(spec, profile, height=300), df)
        self.assertEqual(len(inline["data"]["values"]), 120)
        self.assertEqual(vega_lite_errors(inline), [])


if __name__ == "__main__":
    unittest.main()
