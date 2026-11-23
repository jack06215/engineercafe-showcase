import math
import unittest
from typing import Any

import altair

from packages.monkeytype_analysis_console import fixtures, palette
from packages.monkeytype_analysis_console.charts import (
    HOVER_PARAM,
    KEY_LABEL_COLOUR,
    LEGEND_PARAM,
    keyboard_chart,
    progress_chart,
    speed_chart,
    word_speed_chart,
)
from packages.monkeytype_analysis_console.results import (
    Word,
)
from packages.monkeytype_analysis_console.typos import (
    KEY_POSITIONS,
    classify_words,
    wrong_keys,
)


def _spec(chart: altair.LayerChart | None) -> dict[str, Any]:
    assert chart is not None
    spec: dict[str, Any] = chart.to_dict()  # to_dict checks the Vega-Lite schema
    return spec


def _units(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Every single-mark view, depth first."""
    return [unit for unit, _ in _units_with_data(spec)]


def _units_with_data(
    spec: dict[str, Any], data: str | None = None
) -> list[tuple[dict[str, Any], str | None]]:
    """Every single-mark view with the dataset it reads, which may be a parent's."""
    data = spec.get("data", {}).get("name", data)
    units: list[tuple[dict[str, Any], str | None]] = []
    for layer in spec.get("layer", []):
        if "mark" in layer:
            units.append((layer, layer.get("data", {}).get("name", data)))
        else:
            units += _units_with_data(layer, data)
    return units


def _series(spec: dict[str, Any], name: str) -> dict[str, Any]:
    wanted = {"filter": f"(datum.series === '{name}')"}
    matches = [unit for unit in _units(spec) if wanted in unit.get("transform", [])]
    assert len(matches) == 1, matches
    return matches[0]


def _rows(spec: dict[str, Any], unit: dict[str, Any]) -> list[dict[str, Any]]:
    names = [name for found, name in _units_with_data(spec) if found is unit]
    assert names and names[0] is not None, "the unit has no data"
    rows: list[dict[str, Any]] = spec["datasets"][names[0]]
    return rows


def _mark(unit: dict[str, Any]) -> dict[str, Any]:
    mark: dict[str, Any] = unit["mark"]
    return mark


class SpeedChartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = _spec(speed_chart(fixtures.result(fixtures.REAL)))

    def test_series_are_drawn_like_monkeytype(self) -> None:
        wpm, raw, burst = (_series(self.spec, name) for name in ("wpm", "raw", "burst"))
        self.assertEqual(_mark(wpm)["type"], "line")
        self.assertEqual(_mark(wpm)["strokeWidth"], 3)
        self.assertNotIn("strokeDash", _mark(wpm))
        self.assertEqual(_mark(raw)["type"], "line")
        self.assertIn("strokeDash", _mark(raw))
        self.assertEqual(raw["encoding"]["opacity"]["condition"][0]["value"], 0.6)
        self.assertEqual(_mark(burst)["type"], "area")
        self.assertTrue(_mark(burst)["line"])

    def test_colours(self) -> None:
        scale = _series(self.spec, "wpm")["encoding"]["color"]["scale"]
        colours = dict(zip(scale["domain"], scale["range"], strict=True))
        self.assertEqual(
            colours,
            {
                "wpm": palette.MAIN,
                "raw": palette.MAIN,
                "burst": palette.SUB,
                "errors": palette.ERROR,
            },
        )

    def test_speeds_share_the_left_axis_and_errors_get_the_right(self) -> None:
        self.assertEqual(self.spec["resolve"], {"scale": {"y": "independent"}})
        speed_group = self.spec["layer"][0]
        speed_fields = {
            unit["encoding"]["y"]["field"]
            for unit in _units(speed_group)
            if "transform" in unit
        }
        self.assertEqual(speed_fields, {"value"})
        errors = _series(self.spec, "errors")
        self.assertNotIn(errors, _units(speed_group))
        self.assertEqual(errors["encoding"]["y"]["axis"]["orient"], "right")
        self.assertEqual(errors["encoding"]["y"]["title"], "errors")

    def test_errors_are_points_only_where_there_are_errors(self) -> None:
        errors = _series(self.spec, "errors")
        self.assertEqual(_mark(errors)["type"], "point")
        self.assertIn({"filter": "(datum.value > 0)"}, errors["transform"])

    def test_legend_toggles_and_hover(self) -> None:
        params = {param["name"]: param for param in self.spec["params"]}
        self.assertEqual(params[LEGEND_PARAM]["bind"], "legend")
        self.assertEqual(params[LEGEND_PARAM]["select"]["fields"], ["series"])
        # Each click adds or removes a series, so a second click shows all again.
        self.assertEqual(params[LEGEND_PARAM]["select"]["toggle"], "true")
        # The legend belongs to the first view with a colour, the burst area;
        # a legend-bound param defined on any other view ignores clicks.
        self.assertEqual(
            params[LEGEND_PARAM]["views"], [_series(self.spec, "burst")["name"]]
        )
        self.assertTrue(params[HOVER_PARAM]["select"]["nearest"])
        self.assertEqual(params[HOVER_PARAM]["select"]["fields"], ["t"])
        # Each param lives in exactly one view of its own.
        self.assertEqual(len(params[LEGEND_PARAM]["views"]), 1)
        self.assertEqual(len(params[HOVER_PARAM]["views"]), 1)
        self.assertNotEqual(params[LEGEND_PARAM]["views"], params[HOVER_PARAM]["views"])

    def test_hover_tooltip_has_every_series(self) -> None:
        rules = [
            unit
            for unit in _units(self.spec)
            if _mark(unit)["type"] == "rule" and "tooltip" in unit["encoding"]
        ]
        self.assertEqual(len(rules), 1)
        fields = [item["field"] for item in rules[0]["encoding"]["tooltip"]]
        self.assertEqual(fields, ["t", "wpm", "raw", "burst", "errors"])

    def test_previous_pb_line(self) -> None:
        pb_units = [
            unit
            for unit in _units(self.spec)
            if unit["encoding"].get("y", {}).get("field") == "pb"
        ]
        self.assertEqual({_mark(unit)["type"] for unit in pb_units}, {"rule", "text"})
        row = _rows(self.spec, pb_units[0])[0]
        self.assertAlmostEqual(row["pb"], 51.69 - 26.38)

    def test_axis_titles(self) -> None:
        self.assertEqual(_series(self.spec, "wpm")["encoding"]["x"]["title"], "seconds")
        cpm = _spec(speed_chart(fixtures.result(fixtures.CPM)))
        self.assertEqual(_series(cpm, "wpm")["encoding"]["y"]["title"], "cpm")

    def test_no_pb_line_without_a_pb_or_in_other_units(self) -> None:
        for path in (fixtures.TYPOS, fixtures.CPM):
            spec = _spec(speed_chart(fixtures.result(path)))
            fields = {
                unit["encoding"].get("y", {}).get("field") for unit in _units(spec)
            }
            with self.subTest(path.name):
                self.assertNotIn("pb", fields)

    def test_keeps_the_fractional_last_second(self) -> None:
        spec = _spec(speed_chart(fixtures.result(fixtures.TYPOS)))
        seconds = {row["t"] for row in _rows(spec, _series(spec, "wpm"))}
        self.assertIn(12.5, seconds)

    def test_none_without_a_chart(self) -> None:
        self.assertIsNone(speed_chart(fixtures.result(fixtures.CHART_ERROR)))
        self.assertIsNone(speed_chart(fixtures.result(fixtures.MULTI, 1)))


class WordSpeedChartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = fixtures.result(fixtures.TYPOS)
        self.spec = _spec(
            word_speed_chart(self.result.words, self.result.steps, 40, "wpm")
        )
        self.bars = next(u for u in _units(self.spec) if _mark(u)["type"] == "bar")

    def test_one_bar_per_measured_word(self) -> None:
        rows = _rows(self.spec, self.bars)
        self.assertEqual(len(rows), 9)
        self.assertNotIn("hello", [row["word"] for row in rows])

    def test_bars_take_the_band_colour_and_label(self) -> None:
        rows = {row["word"]: row for row in _rows(self.spec, self.bars)}
        self.assertEqual(rows["sneeing"]["colour"], palette.BANDS[0])
        self.assertEqual(rows["sneeing"]["band"], "<31")
        self.assertEqual(rows["the"]["colour"], palette.BANDS[4])
        self.assertEqual(rows["the"]["band"], "90+")
        self.assertIsNone(self.bars["encoding"]["color"]["scale"])

    def test_threshold_line(self) -> None:
        rule = next(u for u in _units(self.spec) if _mark(u)["type"] == "rule")
        self.assertEqual(_rows(self.spec, rule), [{"threshold": 40}])

    def test_none_without_measured_words(self) -> None:
        words = [Word(i=0, word="hello", wpm=math.inf, bucket=None)]
        self.assertIsNone(word_speed_chart(words, (), 40, "wpm"))


class KeyboardChartTest(unittest.TestCase):
    def setUp(self) -> None:
        words = fixtures.result(fixtures.TYPOS).words
        self.spec = _spec(keyboard_chart(wrong_keys(classify_words(words))))
        self.keys, self.labels = _units(self.spec)
        self.rows = {row["key"]: row for row in _rows(self.spec, self.keys)}

    def test_every_key_once(self) -> None:
        self.assertEqual(set(self.rows), set(KEY_POSITIONS))
        self.assertEqual(_mark(self.keys)["type"], "rect")
        self.assertEqual(_mark(self.labels)["type"], "text")
        self.assertEqual(_mark(self.labels)["color"], KEY_LABEL_COLOUR)

    def test_counts_and_confusions(self) -> None:
        self.assertEqual(self.rows["e"]["count"], 1)
        self.assertEqual(self.rows["e"]["confusions"], "e→r ×1")
        self.assertEqual(self.rows["n"]["count"], 1)
        self.assertEqual(self.rows["q"]["count"], 0)
        self.assertEqual(self.rows["q"]["confusions"], "")

    def test_colour_runs_from_grey_to_the_error_colour(self) -> None:
        scale = self.keys["encoding"]["color"]["scale"]
        self.assertEqual(scale["range"], [palette.SUB, palette.ERROR])
        self.assertEqual(scale["domain"], [0, 1])

    def test_top_row_is_drawn_first(self) -> None:
        self.assertTrue(self.keys["encoding"]["y"]["scale"]["reverse"])

    def test_without_typos_every_key_is_grey(self) -> None:
        spec = _spec(keyboard_chart({}))
        keys = _units(spec)[0]
        self.assertEqual({row["count"] for row in _rows(spec, keys)}, {0})


class ProgressChartTest(unittest.TestCase):
    def setUp(self) -> None:
        results = fixtures.read(fixtures.PROGRESS).results
        self.english = [
            r for r in results if r.test == "words 10" and r.language == "english 1k"
        ][:4]

    def test_line_and_points_over_time(self) -> None:
        spec = _spec(progress_chart(self.english, "wpm"))
        line, points = _units(spec)
        self.assertEqual(_mark(line)["type"], "line")
        self.assertEqual(points["encoding"]["x"]["type"], "temporal")
        self.assertEqual(points["encoding"]["y"]["field"], "wpm")
        self.assertFalse(points["encoding"]["y"]["scale"]["zero"])
        rows = _rows(spec, points)
        self.assertEqual([row["wpm"] for row in rows], [50, 52, 49, 55])

    def test_pbs_get_their_own_shape(self) -> None:
        spec = _spec(progress_chart(self.english, "wpm"))
        points = _units(spec)[1]
        shape = points["encoding"]["shape"]
        self.assertEqual(shape["scale"]["range"], ["circle", "diamond"])
        self.assertEqual(
            [row["kind"] for row in _rows(spec, points)],
            ["result", "result", "result", "PB"],
        )

    def test_goal_line_on_accuracy(self) -> None:
        spec = _spec(progress_chart(self.english, "acc", goal=96))
        rule = _units(spec)[2]
        self.assertEqual(_mark(rule)["type"], "rule")
        self.assertEqual(_rows(spec, rule), [{"goal": 96}])
        self.assertEqual(len(_units(_spec(progress_chart(self.english, "acc")))), 2)

    def test_tooltip(self) -> None:
        points = _units(_spec(progress_chart(self.english, "wpm")))[1]
        fields = [item["field"] for item in points["encoding"]["tooltip"]]
        self.assertEqual(fields, ["when", "test", "wpm", "acc", "consistency", "file"])

    def test_only_wpm_or_acc(self) -> None:
        with self.assertRaises(ValueError):
            progress_chart(self.english, "raw")


if __name__ == "__main__":
    unittest.main()
