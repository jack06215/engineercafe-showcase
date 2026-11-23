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
    FOLDER_ENV,
    FOLDER_KEY,
    NO_CHART,
    NO_HISTORY,
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
            "8 results from 7 files, 1 duplicate skipped",
            [caption.value for caption in app.sidebar.caption],
        )
        picker = app.selectbox(key=PICK_KEY)
        self.assertEqual(len(picker.options), 8)
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


if __name__ == "__main__":
    unittest.main()
