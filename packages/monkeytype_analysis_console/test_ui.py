"""UI tests: drive the app headlessly with streamlit.testing's AppTest."""

import os
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.results import (
    Result,
)
from packages.monkeytype_analysis_console.ui import (
    ABORTED,
    ANALYSIS_PAGE,
    FOLDER_ENV,
    FOLDER_KEY,
    GOAL_KEY,
    NO_CHART,
    NO_HISTORY,
    NO_MISTAKES,
    NO_RESULTS,
    PICK_KEY,
    REPLAY_PAGE,
    result_label,
    threshold_key,
)

APP = Path(__file__).with_name("main.py")
TIMEOUT = 60  # the first run imports pandas, altair and streamlit


def _start(environ: dict[str, str] | None = None) -> AppTest:
    """Runs the app once, with only `environ` for the folder variable."""
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    with mock.patch.dict(os.environ):
        os.environ.pop(FOLDER_ENV, None)
        os.environ.update(environ or {})
        return app.run()


def _folder(paths: Iterable[Path]) -> tempfile.TemporaryDirectory[str]:
    folder = tempfile.TemporaryDirectory()
    fixtures.copy_to(Path(folder.name), paths)
    return folder


class UiTest(unittest.TestCase):
    def assert_clean(self, app: AppTest) -> None:
        self.assertFalse(app.exception, [e.value for e in app.exception])

    def open_folder(self, paths: Iterable[Path]) -> AppTest:
        folder = _folder(paths)
        self.addCleanup(folder.cleanup)
        app = _start()
        app.text_input(key=FOLDER_KEY).input(folder.name).run()
        self.assert_clean(app)
        return app

    def pick(self, app: AppTest, result: Result) -> AppTest:
        app.selectbox(key=PICK_KEY).select(result.identity).run()
        self.assert_clean(app)
        return app

    def metric(self, app: AppTest, label: str) -> str:
        values = [metric.value for metric in app.metric if metric.label == label]
        self.assertEqual(len(values), 1, [m.label for m in app.metric])
        return values[0]

    def word_lists(self, app: AppTest) -> dict[str, str]:
        """The word lists under their captions, when all three have words."""
        captions = [caption.value for caption in app.main.caption]
        titles = [c for c in captions if c in ("Words", "Missed words")]
        titles += [c for c in captions if c.startswith("Slow words under")]
        blocks = [block.value for block in app.main.code]
        self.assertEqual(len(titles), len(blocks))
        return dict(zip(titles, blocks, strict=True))

    def test_without_results(self) -> None:
        app = _start()
        self.assert_clean(app)
        self.assertEqual([info.value for info in app.info], [NO_RESULTS])
        self.assertEqual(len(app.selectbox), 0)

    def test_folder_box_loads_every_file(self) -> None:
        app = self.open_folder(fixtures.GOOD_FILES)
        self.assertIn(
            "9 results from 8 files, 1 duplicate skipped",
            [caption.value for caption in app.sidebar.caption],
        )
        picker = app.selectbox(key=PICK_KEY)
        self.assertEqual(len(picker.options), 9)
        # The newest result comes first and is shown.
        newest = fixtures.result(fixtures.MULTI, 2)
        self.assertEqual(picker.options[0], result_label(newest))
        self.assertEqual(self.metric(app, "wpm"), "48.8")

    def test_environment_variable_fills_the_folder_box(self) -> None:
        folder = _folder([fixtures.REAL])
        self.addCleanup(folder.cleanup)
        app = _start({FOLDER_ENV: folder.name})
        self.assert_clean(app)
        self.assertEqual(app.text_input(key=FOLDER_KEY).value, folder.name)
        self.assertEqual(self.metric(app, "wpm"), "51.69")

    def test_upload(self) -> None:
        app = _start()
        app.file_uploader[0].upload(
            "real.yml", fixtures.REAL.read_bytes(), "application/yaml"
        ).run()
        self.assert_clean(app)
        self.assertEqual(self.metric(app, "wpm"), "51.69")
        self.assertEqual(self.metric(app, "acc"), "98.39%")
        self.assertEqual(self.metric(app, "characters"), "61/0/0/0")
        self.assertEqual(self.metric(app, "session"), "00:00:14")

    def test_replay_of_a_result(self) -> None:
        app = self.open_folder([fixtures.TYPOS])
        self.assertEqual(self.metric(app, "test type"), "words 10")
        self.assertEqual(self.metric(app, "consistency"), "61.2%")
        captions = [caption.value for caption in app.main.caption]
        self.assertIn("english 1k · punctuation", captions)
        self.assertIn("1 word too fast to measure is not in the chart.", captions)
        self.assertEqual(len(app.main.get("vega_lite_chart")), 2)
        history = [element.value for element in app.main.html]
        self.assertTrue(any(">Python<" in value for value in history))

    def test_threshold_slider_changes_the_slow_words(self) -> None:
        typos = fixtures.result(fixtures.TYPOS)
        app = self.open_folder([fixtures.TYPOS])
        lists = self.word_lists(app)
        self.assertEqual(lists["Slow words under 40 wpm"], "sneeing Vec<T> about")
        self.assertEqual(lists["Missed words"], "sneeing test about null they")
        app.slider(key=threshold_key(typos)).set_value(46.0).run()
        self.assert_clean(app)
        self.assertEqual(
            self.word_lists(app)["Slow words under 46 wpm"],
            "sneeing Vec<T> test about they",
        )

    def test_picker_switches_the_result(self) -> None:
        app = self.open_folder(fixtures.GOOD_FILES)
        self.pick(app, fixtures.result(fixtures.REAL))
        self.assertEqual(self.metric(app, "wpm"), "51.69")
        badges = [element.value for element in app.main.markdown]
        self.assertTrue(any("PB +26.38" in value for value in badges), badges)

    def test_chart_error(self) -> None:
        app = self.open_folder([fixtures.CHART_ERROR])
        infos = [info.value for info in app.info]
        self.assertEqual(len(infos), 1)
        self.assertTrue(infos[0].startswith(NO_CHART))
        self.assertIn("was not found on the page", infos[0])

    def test_result_without_input_history(self) -> None:
        app = self.open_folder([fixtures.MULTI])
        self.pick(app, fixtures.result(fixtures.MULTI, 1))
        self.assertIn(NO_HISTORY, [info.value for info in app.info])
        self.assertEqual(len(app.slider), 0)

    def test_other_units(self) -> None:
        app = self.open_folder([fixtures.CPM])
        self.assertIn(
            "The chart and the word speeds are in cpm.",
            [caption.value for caption in app.main.caption],
        )

    def test_files_with_errors_are_listed(self) -> None:
        app = self.open_folder([fixtures.REAL, fixtures.NOT_A_RESULT, fixtures.BROKEN])
        self.assertEqual(
            [expander.label for expander in app.sidebar.expander],
            ["2 files had errors"],
        )
        errors = [element.value for element in app.sidebar.text]
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("broken.yml: YAML error on line"))

    def test_not_a_folder(self) -> None:
        app = _start()
        app.text_input(key=FOLDER_KEY).input("/no/such/folder").run()
        self.assert_clean(app)
        self.assertEqual(
            [warning.value for warning in app.sidebar.warning],
            ["Not a folder: /no/such/folder"],
        )
        self.assertEqual([info.value for info in app.info], [NO_RESULTS])

    def test_picked_result_that_is_gone_falls_back_to_the_newest(self) -> None:
        app = self.open_folder(fixtures.GOOD_FILES)
        self.pick(app, fixtures.result(fixtures.REAL))
        other = _folder([fixtures.CUSTOM])
        self.addCleanup(other.cleanup)
        app.text_input(key=FOLDER_KEY).input(other.name).run()
        self.assert_clean(app)
        self.assertEqual(self.metric(app, "wpm"), "27.3")

    def test_replay_is_the_page(self) -> None:
        app = _start()
        app.switch_page(REPLAY_PAGE).run()
        self.assert_clean(app)
        self.assertEqual([header.value for header in app.header], ["Result replay"])


class AnalysisPageTest(UiTest):
    def analyse(self, paths: Iterable[Path], result: Result | None = None) -> AppTest:
        app = self.open_folder(paths)
        if result is not None:
            self.pick(app, result)
        app.switch_page(ANALYSIS_PAGE).run()
        self.assert_clean(app)
        return app

    def test_without_results(self) -> None:
        app = _start()
        app.switch_page(ANALYSIS_PAGE).run()
        self.assert_clean(app)
        self.assertEqual([info.value for info in app.info], [NO_RESULTS])

    def test_analysis_of_a_result(self) -> None:
        app = self.analyse([fixtures.TYPOS])
        self.assertEqual([h.value for h in app.header], ["Result analysis"])
        self.assertEqual(self.metric(app, "accuracy goal"), "missed")
        # 7 wrong keys and their backspaces at 44.1 raw wpm.
        self.assertEqual(self.metric(app, "time lost to mistakes"), "3.81s")
        self.assertEqual(self.metric(app, "characters left wrong"), "5")
        captions = [caption.value for caption in app.main.caption]
        self.assertIn("acc 88.52% vs 96%", captions)
        self.assertIn("flags: none", captions)
        self.assertIn(
            "5 of 10 words mistyped, 5 typos", [m.value for m in app.main.markdown]
        )
        bands, categories, confusions, mistyped, position = (
            frame.value for frame in app.main.dataframe
        )
        self.assertEqual(
            list(bands["band"]), ["<31", "31-44", "45-59", "60-89", "90+", "all"]
        )
        self.assertEqual(len(categories), 5)
        self.assertEqual(set(confusions["confusion"]), {"n→e", "e→r"})
        self.assertEqual(
            list(mistyped["word"]), ["sneeing", "test", "about", "null", "they"]
        )
        self.assertEqual(list(position["part"]), ["first", "middle", "last"])
        self.assertEqual(len(app.main.get("vega_lite_chart")), 1)

    def test_goal_input_changes_the_check(self) -> None:
        app = self.analyse([fixtures.TYPOS])
        app.number_input(key=GOAL_KEY).set_value(85.0).run()
        self.assert_clean(app)
        self.assertEqual(self.metric(app, "accuracy goal"), "met")

    def test_aborted_result_shows_only_the_checks(self) -> None:
        app = self.analyse([fixtures.ABORTED])
        self.assertIn(ABORTED, [info.value for info in app.info])
        self.assertIn(
            "flags: failed (min accuracy), aborted",
            [caption.value for caption in app.main.caption],
        )
        self.assertEqual(len(app.main.dataframe), 0)

    def test_result_without_input_history(self) -> None:
        app = self.analyse([fixtures.MULTI], fixtures.result(fixtures.MULTI, 1))
        self.assertIn(NO_HISTORY, [info.value for info in app.info])

    def test_result_without_mistakes(self) -> None:
        app = self.analyse([fixtures.HEATMAP_OFF])
        self.assertIn(NO_MISTAKES, [info.value for info in app.info])

    def test_picked_result_and_goal_carry_across_pages(self) -> None:
        app = self.analyse(fixtures.GOOD_FILES, fixtures.result(fixtures.TYPOS))
        self.assertEqual(self.metric(app, "characters left wrong"), "5")
        app.number_input(key=GOAL_KEY).set_value(85.0).run()
        app.switch_page(REPLAY_PAGE).run()
        self.assert_clean(app)
        self.assertEqual(self.metric(app, "wpm"), "38.4")
        app.switch_page(ANALYSIS_PAGE).run()
        self.assert_clean(app)
        self.assertEqual(app.number_input(key=GOAL_KEY).value, 85.0)
        self.assertEqual(self.metric(app, "accuracy goal"), "met")


if __name__ == "__main__":
    unittest.main()
