"""Tests for compiler.py. Every compiled spec must pass Vega-Lite's JSON schema."""

import unittest
from pathlib import Path
from typing import Any

import pandas
import yaml

from packages.vibe_coding_club.vega_lite_chat.chart_spec import ChartSpec
from packages.vibe_coding_club.vega_lite_chat.checks import check_chart
from packages.vibe_coding_club.vega_lite_chat.compiler import (
    RANK,
    SCHEMA_URL,
    TOTAL,
    compile_chart,
    escape_field,
    vega_lite_errors,
    with_inline_data,
)
from packages.vibe_coding_club.vega_lite_chat.config import load_config
from packages.vibe_coding_club.vega_lite_chat.csv_loader import load_csv
from packages.vibe_coding_club.vega_lite_chat.profile import (
    DataProfile,
    profile_frame,
)
from packages.vibe_coding_club.vega_lite_chat.samples import sample_named

PROMPTS = Path(__file__).with_name("prompts.yaml")
MONTH = {"field": "月", "type": "temporal", "timeUnit": "yearmonth"}
SALES = {"field": "売上", "type": "quantitative", "aggregate": "sum"}
REGION = {"field": "地域", "type": "nominal"}

ONE_PER_MARK: dict[str, dict[str, Any]] = {
    "bar": {"mark": "bar", "x": REGION, "y": SALES},
    "line": {"mark": "line", "x": MONTH, "y": SALES, "color": REGION},
    "point": {
        "mark": "point",
        "x": {"field": "売上", "type": "quantitative"},
        "y": {"field": "件数", "type": "quantitative"},
        "size": {"field": "件数", "type": "quantitative"},
    },
    "area": {
        "mark": "area",
        "x": MONTH,
        "y": {**SALES, "stack": "zero"},
        "color": REGION,
    },
    "arc": {"mark": "arc", "theta": SALES, "color": REGION},
    "rect": {
        "mark": "rect",
        "x": {**MONTH, "type": "ordinal", "timeUnit": "month"},
        "y": REGION,
        "color": {**SALES, "aggregate": "mean"},
    },
    "boxplot": {
        "mark": "boxplot",
        "x": REGION,
        "y": {"field": "売上", "type": "quantitative"},
    },
}


def _frame() -> pandas.DataFrame:
    return pandas.DataFrame(
        {
            "月": pandas.to_datetime(
                ["2024-01-01", "2024-02-01", "2025-01-01", "2025-02-01"]
            ),
            "地域": ["福岡", "東京", "福岡", "大阪"],
            "売上": [320, 500, 410, 280],
            "件数": [10, 12, 11, 9],
            "単価.税込[円]": [1.5, 2.0, float("nan"), 3.25],
        }
    )


def _profile(df: pandas.DataFrame) -> DataProfile:
    return profile_frame(df, sample_rows=3, seed=0, max_listed_values=20)


PROFILE = _profile(_frame())


def _compile(**chart: Any) -> dict[str, Any]:
    spec = ChartSpec.model_validate(chart)
    errors = check_chart(spec, PROFILE)
    if errors:
        raise AssertionError(f"the test chart itself is invalid: {errors}")
    return compile_chart(spec, PROFILE, height=400)


class SchemaTest(unittest.TestCase):
    def assert_valid(self, compiled: dict[str, Any]) -> None:
        self.assertEqual(vega_lite_errors(compiled), [])

    def test_one_chart_per_mark(self) -> None:
        for mark, chart in ONE_PER_MARK.items():
            with self.subTest(mark=mark):
                compiled = _compile(**chart)
                self.assertEqual(compiled["mark"]["type"], mark)
                self.assert_valid(compiled)

    def test_facets_filters_and_top_n_are_valid(self) -> None:
        compiled = _compile(
            mark="bar",
            x={"field": "地域", "type": "nominal", "sort": "-y"},
            y={**SALES, "stack": "none"},
            column={"field": "月", "type": "ordinal", "timeUnit": "year"},
            row=REGION,
            filters=[
                {
                    "field": "月",
                    "op": "range",
                    "value": ["2024-01", "2025-01-31T09:30"],
                },
                {"field": "件数", "op": "gt", "value": 5},
                {"field": "地域", "op": "oneOf", "value": ["福岡", "大阪"]},
            ],
            top_n={"field": "地域", "by": "売上", "n": 2},
        )
        self.assert_valid(compiled)

    def test_broken_spec_is_reported_with_its_path(self) -> None:
        broken = {
            "$schema": SCHEMA_URL,
            "mark": "bar",
            "encoding": {"color": {"field": "a", "type": "nominal", "stack": "zero"}},
        }
        errors = vega_lite_errors(broken)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("encoding/color"), errors)

    def test_prompt_examples_compile(self) -> None:
        if not PROMPTS.exists():
            self.skipTest("prompts.yaml is not there yet")
        data = load_config().data
        book = yaml.safe_load(PROMPTS.read_text(encoding="utf-8"))
        for index, example in enumerate(book["examples"]):
            df = load_csv(sample_named(example["sample"]).read_bytes())
            profile = profile_frame(
                df,
                sample_rows=data.sample_rows,
                seed=data.sample_seed,
                max_listed_values=data.max_listed_values,
            )
            charts = {
                "current": example.get("current"),
                "reply": example["reply"].get("chart"),
            }
            for key, raw in charts.items():
                if raw is None:
                    continue
                with self.subTest(example=index, chart=key):
                    spec = ChartSpec.model_validate(raw)
                    self.assertEqual(check_chart(spec, profile), [])
                    self.assert_valid(compile_chart(spec, profile, height=400))


class LayoutTest(unittest.TestCase):
    def test_single_view(self) -> None:
        compiled = _compile(**ONE_PER_MARK["bar"])
        self.assertEqual(compiled["$schema"], SCHEMA_URL)
        self.assertEqual((compiled["width"], compiled["height"]), ("container", 400))
        self.assertNotIn("data", compiled)
        self.assertNotIn("transform", compiled)

    def test_facets_drop_the_container_width(self) -> None:
        compiled = _compile(mark="bar", x=REGION, y=SALES, column=REGION)
        self.assertNotIn("width", compiled)
        self.assertEqual(compiled["height"], 400)
        compiled = _compile(mark="bar", x=REGION, y=SALES, row=REGION)
        self.assertEqual(compiled["height"], 200)

    def test_title(self) -> None:
        self.assertEqual(_compile(title="売上", **ONE_PER_MARK["bar"])["title"], "売上")

    def test_line_gets_points_to_hover(self) -> None:
        self.assertEqual(
            _compile(**ONE_PER_MARK["line"])["mark"], {"type": "line", "point": True}
        )


class EncodingTest(unittest.TestCase):
    def test_fields_are_copied(self) -> None:
        compiled = _compile(
            mark="bar", x={**REGION, "sort": "-y", "title": "地域名"}, y=SALES
        )
        self.assertEqual(
            compiled["encoding"]["x"],
            {"field": "地域", "type": "nominal", "sort": "-y", "title": "地域名"},
        )
        self.assertEqual(
            compiled["encoding"]["y"],
            {"field": "売上", "type": "quantitative", "aggregate": "sum"},
        )

    def test_time_units_are_utc(self) -> None:
        compiled = _compile(**ONE_PER_MARK["line"])
        self.assertEqual(compiled["encoding"]["x"]["timeUnit"], "utcyearmonth")

    def test_raw_dates_get_a_utc_scale(self) -> None:
        compiled = _compile(
            mark="point",
            x={"field": "月", "type": "temporal"},
            y={"field": "売上", "type": "quantitative"},
        )
        self.assertEqual(compiled["encoding"]["x"]["scale"], {"type": "utc"})

    def test_stack(self) -> None:
        self.assertIsNone(
            _compile(mark="bar", x=REGION, y={**SALES, "stack": "none"})["encoding"][
                "y"
            ]["stack"]
        )
        self.assertEqual(
            _compile(mark="bar", x=REGION, y={**SALES, "stack": "normalize"})[
                "encoding"
            ]["y"]["stack"],
            "normalize",
        )

    def test_count_without_field(self) -> None:
        compiled = _compile(
            mark="bar",
            x=REGION,
            y={"field": None, "type": "quantitative", "aggregate": "count"},
        )
        self.assertEqual(
            compiled["encoding"]["y"], {"type": "quantitative", "aggregate": "count"}
        )

    def test_dots_and_brackets_are_escaped(self) -> None:
        self.assertEqual(escape_field("単価.税込[円]"), "単価\\.税込\\[円\\]")
        compiled = _compile(
            mark="bar",
            x=REGION,
            y={"field": "単価.税込[円]", "type": "quantitative", "aggregate": "mean"},
        )
        self.assertEqual(compiled["encoding"]["y"]["field"], "単価\\.税込\\[円\\]")
        self.assertEqual(compiled["encoding"]["y"]["title"], "単価.税込[円]")
        self.assertEqual(vega_lite_errors(compiled), [])


class TooltipTest(unittest.TestCase):
    def test_every_encoded_field_once(self) -> None:
        compiled = _compile(mark="bar", x=REGION, y=SALES, color=REGION)
        self.assertEqual(
            compiled["encoding"]["tooltip"],
            [
                {"field": "地域", "type": "nominal"},
                {"field": "売上", "type": "quantitative", "aggregate": "sum"},
            ],
        )

    def test_mirrors_time_units_and_dates(self) -> None:
        tooltip = _compile(**ONE_PER_MARK["line"])["encoding"]["tooltip"]
        self.assertIn(
            {"field": "月", "type": "temporal", "timeUnit": "utcyearmonth"}, tooltip
        )
        tooltip = _compile(
            mark="point",
            x={"field": "月", "type": "temporal"},
            y={"field": "売上", "type": "quantitative"},
        )["encoding"]["tooltip"]
        self.assertIn(
            {"field": "月", "type": "temporal", "timeUnit": "utcyearmonthdate"}, tooltip
        )

    def test_boxplot_has_none(self) -> None:
        self.assertNotIn("tooltip", _compile(**ONE_PER_MARK["boxplot"])["encoding"])


class FilterTest(unittest.TestCase):
    def _transform(self, **filter_: Any) -> list[dict[str, Any]]:
        compiled = _compile(mark="bar", x=REGION, y=SALES, filters=[filter_])
        self.assertEqual(vega_lite_errors(compiled), [])
        transform: list[dict[str, Any]] = compiled["transform"]
        return transform

    def test_dates_become_utc_expressions(self) -> None:
        # Vega-Lite's own timeUnit predicates dropped every row in Streamlit's frontend.
        month = 'datum["月"]'
        cases: list[tuple[dict[str, Any], str]] = [
            (
                {"field": "月", "op": "gte", "value": "2025-01-05"},
                f"time({month}) >= 1736035200000",
            ),
            (
                {"field": "月", "op": "lt", "value": "2025-01-05T09:30"},
                f"time({month}) < 1736069400000",
            ),
            (
                {"field": "月", "op": "equal", "value": 2025, "timeUnit": "year"},
                f"utcyear({month}) === 2025",
            ),
            (
                {"field": "月", "op": "oneOf", "value": [1, 2], "timeUnit": "month"},
                f"indexof([1, 2], (utcmonth({month}) + 1)) >= 0",
            ),
            (
                {
                    "field": "月",
                    "op": "equal",
                    "value": "2025-02",
                    "timeUnit": "yearmonth",
                },
                f"(utcyear({month}) * 100 + utcmonth({month}) + 1) === 202502",
            ),
            (
                {
                    "field": "月",
                    "op": "range",
                    "value": ["2025-01-01", "2025-06-30"],
                },
                f"time({month}) >= 1735689600000 && time({month}) <= 1751241600000",
            ),
            (
                {"field": "月", "op": "range", "value": [1, 5], "timeUnit": "day"},
                (
                    f"((utcday({month}) + 6) % 7 + 1) >= 1"
                    f" && ((utcday({month}) + 6) % 7 + 1) <= 5"
                ),
            ),
        ]
        for filter_, expected in cases:
            with self.subTest(filter=filter_):
                self.assertEqual(self._transform(**filter_), [{"filter": expected}])

    def test_numbers_stay_numbers_and_text_becomes_text(self) -> None:
        self.assertEqual(
            self._transform(field="売上", op="range", value=[300, 450]),
            [{"filter": {"field": "売上", "range": [300, 450]}}],
        )
        self.assertEqual(
            self._transform(field="地域", op="equal", value="福岡"),
            [{"filter": {"field": "地域", "equal": "福岡"}}],
        )

    def test_top_n_after_the_filters(self) -> None:
        compiled = _compile(
            mark="bar",
            x=REGION,
            y=SALES,
            filters=[{"field": "件数", "op": "gt", "value": 9}],
            top_n={"field": "地域", "by": "売上", "n": 2},
        )
        self.assertEqual(
            compiled["transform"][1:],
            [
                {
                    "joinaggregate": [{"op": "sum", "field": "売上", "as": TOTAL}],
                    "groupby": ["地域"],
                },
                {
                    "window": [{"op": "dense_rank", "as": RANK}],
                    "sort": [{"field": TOTAL, "order": "descending"}],
                },
                {"filter": {"field": RANK, "lte": 2}},
            ],
        )
        self.assertEqual(
            compiled["transform"][0], {"filter": {"field": "件数", "gt": 9}}
        )


class InlineDataTest(unittest.TestCase):
    def test_rows_are_embedded(self) -> None:
        df = _frame()
        df.loc[1, "月"] = pandas.Timestamp(2024, 2, 1, 9, 30)
        compiled = _compile(**ONE_PER_MARK["bar"])
        inline = with_inline_data(compiled, df)
        self.assertNotIn("data", compiled)
        values = inline["data"]["values"]
        self.assertEqual(len(values), 4)
        self.assertEqual(
            values[0],
            {
                "月": "2024-01-01",
                "地域": "福岡",
                "売上": 320,
                "件数": 10,
                "単価.税込[円]": 1.5,
            },
        )
        self.assertEqual(values[1]["月"], "2024-02-01T09:30:00Z")
        self.assertIsNone(values[2]["単価.税込[円]"])
        self.assertEqual(inline["encoding"], compiled["encoding"])
        self.assertEqual(vega_lite_errors(inline), [])

    def test_sample_data_round_trips(self) -> None:
        df = load_csv(sample_named("sales_by_region.csv").read_bytes())
        profile = _profile(df)
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
