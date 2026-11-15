"""Tests for checks.py: every rule in packages/vega_lite_chat/DESIGN.md §5, passing and failing."""

import unittest
from typing import Any

import pandas

from packages.vega_lite_core.chart_spec import ChartSpec
from packages.vega_lite_core.checks import check_chart, empty_column_errors
from packages.vega_lite_core.profile import (
    DataProfile,
    profile_frame,
)

MONTH = {"field": "月", "type": "temporal", "timeUnit": "yearmonth"}
SALES = {"field": "売上", "type": "quantitative", "aggregate": "sum"}
REGION = {"field": "地域", "type": "nominal"}


def _profile() -> DataProfile:
    df = pandas.DataFrame(
        {
            "月": pandas.to_datetime(
                ["2024-01-01", "2024-02-01", "2025-01-01", "2025-02-01", "2025-03-01"]
            ),
            "地域": ["福岡", "東京", "福岡", "大阪", "東京"],
            "店舗名": ["天神店", "銀座店", "博多店", "梅田店", "新宿店"],
            "売上": [320, 500, 410, 280, 610],
        }
    )
    # 店舗名 has five values, past the limit of four, so it lists none.
    return profile_frame(df, sample_rows=3, seed=0, max_listed_values=4)


PROFILE = _profile()


def _errors(**chart: Any) -> list[str]:
    return check_chart(ChartSpec.model_validate(chart), PROFILE)


class PassingTest(unittest.TestCase):
    def test_valid_charts(self) -> None:
        charts: list[dict[str, Any]] = [
            {"mark": "line", "x": MONTH, "y": SALES, "color": REGION},
            {
                "mark": "bar",
                "x": REGION,
                "y": {**SALES, "stack": "normalize"},
                "color": REGION,
            },
            {"mark": "arc", "theta": SALES, "color": REGION},
            {
                "mark": "rect",
                "x": {**MONTH, "type": "ordinal", "timeUnit": "month"},
                "y": REGION,
                "color": SALES,
            },
            {
                "mark": "boxplot",
                "x": REGION,
                "y": {"field": "売上", "type": "quantitative"},
            },
            {
                "mark": "bar",
                "x": REGION,
                "y": {"field": None, "aggregate": "count", "type": "quantitative"},
            },
            {
                "mark": "bar",
                "x": {"field": "売上", "type": "quantitative", "bin": True},
                "y": {"field": None, "aggregate": "count", "type": "quantitative"},
            },
            {
                "mark": "point",
                "x": {"field": "売上", "type": "ordinal"},
                "y": {"field": "店舗名", "type": "ordinal"},
            },
            {
                "mark": "bar",
                "x": REGION,
                "y": {"field": "地域", "type": "quantitative", "aggregate": "distinct"},
            },
            {
                "mark": "bar",
                "x": REGION,
                "y": SALES,
                "top_n": {"field": "地域", "by": "売上", "n": 2},
                "filters": [
                    {"field": "月", "op": "equal", "value": 2025, "timeUnit": "year"},
                    {"field": "月", "op": "range", "value": ["2024-04", "2025-03-31"]},
                    {
                        "field": "月",
                        "op": "equal",
                        "value": "2025-02",
                        "timeUnit": "yearmonth",
                    },
                    {
                        "field": "月",
                        "op": "oneOf",
                        "value": [1, 2],
                        "timeUnit": "month",
                    },
                    {"field": "売上", "op": "gte", "value": 300},
                    {"field": "地域", "op": "oneOf", "value": ["福岡", "東京"]},
                    {"field": "店舗名", "op": "equal", "value": "どこでも店"},
                ],
            },
        ]
        for chart in charts:
            with self.subTest(chart=chart):
                self.assertEqual(_errors(**chart), [])


class ColumnTest(unittest.TestCase):
    def test_unknown_column_lists_the_columns_and_a_guess(self) -> None:
        errors = _errors(mark="bar", x=REGION, y={**SALES, "field": "売上額"})
        self.assertEqual(len(errors), 1)
        self.assertIn("unknown column `売上額` in y", errors[0])
        self.assertIn("did you mean `売上`", errors[0])
        self.assertIn("columns are: 月, 地域, 店舗名, 売上", errors[0])

    def test_unknown_column_in_filters_and_top_n(self) -> None:
        errors = _errors(
            mark="bar",
            x=REGION,
            y=SALES,
            filters=[{"field": "年", "op": "equal", "value": 2025}],
            top_n={"field": "地域", "by": "利益", "n": 3},
        )
        self.assertTrue(any("`年` in filters[0]" in error for error in errors), errors)
        self.assertTrue(any("`利益` in top_n.by" in error for error in errors), errors)


class TypeTest(unittest.TestCase):
    def test_text_cannot_be_numbers_or_dates(self) -> None:
        for kind in ("quantitative", "temporal"):
            with self.subTest(kind=kind):
                errors = _errors(mark="bar", x={"field": "地域", "type": kind}, y=SALES)
                self.assertTrue(
                    any("type `" + kind in error for error in errors), errors
                )

    def test_numbers_and_dates_can_be_categories(self) -> None:
        self.assertEqual(
            _errors(mark="bar", x={"field": "売上", "type": "nominal"}, y=SALES), []
        )
        self.assertEqual(
            _errors(
                mark="bar", x={**MONTH, "type": "ordinal", "timeUnit": "year"}, y=SALES
            ),
            [],
        )

    def test_date_as_category_needs_a_time_unit(self) -> None:
        errors = _errors(mark="bar", x={"field": "月", "type": "nominal"}, y=SALES)
        self.assertTrue(any("needs a timeUnit" in error for error in errors), errors)


class AggregateTest(unittest.TestCase):
    def test_sum_needs_a_number(self) -> None:
        errors = _errors(
            mark="bar",
            x=REGION,
            y={"field": "地域", "type": "quantitative", "aggregate": "sum"},
        )
        self.assertTrue(
            any("use count or distinct" in error for error in errors), errors
        )

    def test_count_works_on_text(self) -> None:
        self.assertEqual(
            _errors(
                mark="bar",
                x=REGION,
                y={"field": "店舗名", "type": "quantitative", "aggregate": "count"},
            ),
            [],
        )

    def test_only_count_may_omit_the_field(self) -> None:
        errors = _errors(
            mark="bar",
            x=REGION,
            y={"field": None, "type": "quantitative", "aggregate": "sum"},
        )
        self.assertTrue(any("`field` is null" in error for error in errors), errors)
        errors = _errors(
            mark="bar", x=REGION, y={"field": None, "type": "quantitative"}
        )
        self.assertTrue(any("`field` is null" in error for error in errors), errors)

    def test_aggregates_are_quantitative(self) -> None:
        errors = _errors(mark="bar", x=REGION, y={**SALES, "type": "nominal"})
        self.assertTrue(
            any("use type quantitative" in error for error in errors), errors
        )

    def test_bin_needs_a_number(self) -> None:
        errors = _errors(
            mark="bar",
            x={**REGION, "bin": True},
            y={"field": None, "aggregate": "count", "type": "quantitative"},
        )
        self.assertTrue(
            any("bin needs a numeric column" in error for error in errors), errors
        )


class TimeUnitTest(unittest.TestCase):
    def test_time_unit_needs_a_date(self) -> None:
        errors = _errors(mark="bar", x={**REGION, "timeUnit": "year"}, y=SALES)
        self.assertTrue(
            any("timeUnit needs a date column" in error for error in errors), errors
        )

    def test_filter_time_unit_needs_a_date(self) -> None:
        errors = _errors(
            mark="bar",
            x=REGION,
            y=SALES,
            filters=[{"field": "売上", "op": "equal", "value": 1, "timeUnit": "year"}],
        )
        self.assertTrue(
            any("timeUnit needs a date column" in error for error in errors), errors
        )


class MarkTest(unittest.TestCase):
    def test_theta_only_with_arc(self) -> None:
        errors = _errors(mark="bar", x=REGION, y=SALES, theta=SALES)
        self.assertTrue(
            any("theta only applies to the arc mark" in error for error in errors),
            errors,
        )

    def test_arc_needs_theta(self) -> None:
        errors = _errors(mark="arc", color=REGION)
        self.assertTrue(
            any("arc mark needs theta" in error for error in errors), errors
        )

    def test_arc_needs_color(self) -> None:
        # The slices come from color; top_n alone leaves one full circle.
        errors = _errors(
            mark="arc",
            theta=SALES,
            top_n={"field": "地域", "by": "売上", "n": 5},
        )
        self.assertTrue(
            any("arc mark needs color" in error for error in errors), errors
        )

    def test_bar_needs_x_and_y(self) -> None:
        errors = _errors(mark="bar", x=REGION)
        self.assertTrue(
            any("needs both x and y; set y" in error for error in errors), errors
        )

    def test_rect_needs_color(self) -> None:
        errors = _errors(mark="rect", x=REGION, y={**MONTH, "type": "ordinal"})
        self.assertTrue(any("set color" in error for error in errors), errors)

    def test_boxplot_aggregates_by_itself(self) -> None:
        errors = _errors(mark="boxplot", x=REGION, y=SALES)
        self.assertTrue(
            any("boxplot aggregates by itself" in error for error in errors), errors
        )

    def test_boxplot_needs_a_quantitative_axis(self) -> None:
        errors = _errors(
            mark="boxplot", x=REGION, y={"field": "店舗名", "type": "nominal"}
        )
        self.assertTrue(
            any("one quantitative axis" in error for error in errors), errors
        )


class StackTest(unittest.TestCase):
    def test_stack_only_on_bar_and_area(self) -> None:
        errors = _errors(mark="line", x=MONTH, y={**SALES, "stack": "zero"})
        self.assertTrue(
            any("stack only applies to bar and area" in error for error in errors),
            errors,
        )

    def test_stack_only_on_x_or_y(self) -> None:
        errors = _errors(
            mark="bar", x=REGION, y=SALES, color={**REGION, "stack": "zero"}
        )
        self.assertTrue(any("x or y channel" in error for error in errors), errors)


class FilterTest(unittest.TestCase):
    def _filter_errors(self, **filter_: Any) -> list[str]:
        return _errors(mark="bar", x=REGION, y=SALES, filters=[filter_])

    def test_failing_filters(self) -> None:
        cases: list[tuple[dict[str, Any], str]] = [
            ({"field": "地域", "op": "gt", "value": "福岡"}, "use equal or oneOf"),
            (
                {"field": "売上", "op": "range", "value": [1, 2, 3]},
                "list of two values",
            ),
            ({"field": "売上", "op": "range", "value": 5}, "list of two values"),
            ({"field": "地域", "op": "oneOf", "value": "福岡"}, "non-empty list"),
            ({"field": "地域", "op": "equal", "value": ["福岡"]}, "single value"),
            ({"field": "売上", "op": "gt", "value": "300"}, "as a number"),
            ({"field": "月", "op": "gt", "value": 2025}, "ISO date string"),
            ({"field": "月", "op": "gt", "value": "2025年1月"}, "not an ISO date"),
            (
                {"field": "月", "op": "equal", "value": "2025", "timeUnit": "year"},
                "whole number",
            ),
            (
                {"field": "月", "op": "equal", "value": 13, "timeUnit": "month"},
                "from 1 to 12",
            ),
            (
                {
                    "field": "月",
                    "op": "equal",
                    "value": "2025-3",
                    "timeUnit": "yearmonth",
                },
                "'YYYY-MM'",
            ),
            (
                {"field": "地域", "op": "equal", "value": "沖縄"},
                "its values are: 福岡, 東京, 大阪",
            ),
        ]
        for filter_, expected in cases:
            with self.subTest(filter=filter_):
                errors = self._filter_errors(**filter_)
                self.assertTrue(any(expected in error for error in errors), errors)


class TopNTest(unittest.TestCase):
    def test_rank_by_a_number(self) -> None:
        errors = _errors(
            mark="bar",
            x=REGION,
            y=SALES,
            top_n={"field": "店舗名", "by": "地域", "n": 3},
        )
        self.assertTrue(
            any("rank by a numeric column" in error for error in errors), errors
        )


def _blank_profile() -> DataProfile:
    df = pandas.DataFrame(
        {
            "地域": ["福岡", "東京", "大阪"],
            "売上": [320, 500, 410],
            "目標": [float("nan")] * 3,
            "備考": [None] * 3,
        }
    )
    return profile_frame(df, sample_rows=3, seed=0, max_listed_values=20)


BLANK_PROFILE = _blank_profile()


def _blank(name: str) -> str:
    return f"column `{name}` has no values, so the chart would be blank"


def _empty_errors(**chart: Any) -> list[str]:
    return empty_column_errors(ChartSpec.model_validate(chart), BLANK_PROFILE)


class EmptyColumnTest(unittest.TestCase):
    def test_an_empty_column_is_refused(self) -> None:
        errors = _empty_errors(mark="bar", x=REGION, y={**SALES, "field": "目標"})
        self.assertEqual(errors, [_blank("目標")])

    def test_columns_with_values_pass(self) -> None:
        self.assertEqual(_empty_errors(mark="bar", x=REGION, y=SALES), [])

    def test_count_without_a_field_passes(self) -> None:
        count = {"field": None, "type": "quantitative", "aggregate": "count"}
        self.assertEqual(_empty_errors(mark="bar", x=REGION, y=count), [])

    def test_unknown_column_is_left_to_check_chart(self) -> None:
        errors = _empty_errors(mark="bar", x=REGION, y={**SALES, "field": "利益"})
        self.assertEqual(errors, [])

    def test_one_column_on_two_channels_gives_one_error(self) -> None:
        target = {"field": "目標", "type": "quantitative"}
        errors = _empty_errors(
            mark="point", x={**SALES, "aggregate": None}, y=target, size=target
        )
        self.assertEqual(errors, [_blank("目標")])

    def test_errors_are_sorted_by_column_name(self) -> None:
        errors = _empty_errors(
            mark="point",
            x={"field": "目標", "type": "quantitative"},
            y={**SALES, "aggregate": None},
            color={"field": "備考", "type": "nominal"},
        )
        # x comes first, but 備考 sorts before 目標.
        self.assertEqual(errors, [_blank("備考"), _blank("目標")])

    def test_check_chart_accepts_a_blank_chart(self) -> None:
        spec = ChartSpec.model_validate(
            {"mark": "bar", "x": REGION, "y": {**SALES, "field": "目標"}}
        )
        self.assertEqual(check_chart(spec, BLANK_PROFILE), [])


if __name__ == "__main__":
    unittest.main()
