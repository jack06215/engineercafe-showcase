"""UI tests: drive the app headlessly with streamlit.testing's AppTest."""

import os
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest import mock

import anthropic
from streamlit.testing.v1 import AppTest

from packages.monkeytype_analysis_console import fixtures, ui
from packages.monkeytype_analysis_console.practice import (
    BUSY,
    GROUP_INSTRUCTIONS,
    TEXT_INSTRUCTIONS,
)
from packages.monkeytype_analysis_console.results import (
    Result,
)
from packages.monkeytype_analysis_console.ui import (
    ABORTED,
    ALL_PROBLEMS,
    ANALYSIS_PAGE,
    EARLIER_PROBLEMS,
    FOCUS_KEY,
    FOLDER_ENV,
    FOLDER_KEY,
    GOAL_KEY,
    GROUP_BUTTON_KEY,
    GROUP_EFFORT_KEY,
    GROUPS_BY_CLAUDE,
    KEY_ENV,
    LENGTH_KEY,
    MODEL_KEY,
    NEED_TWO,
    NO_CHART,
    NO_HISTORY,
    NO_KEY,
    NO_MISTAKES,
    NO_RECURRING,
    NO_RESULTS,
    NO_WORD_LISTS,
    NOTHING_TO_PRACTISE,
    PICK_KEY,
    PRACTICE_INTRO,
    PRACTICE_NEEDS_TWO,
    PRACTICE_PAGE,
    PROGRESS_PAGE,
    REPLAY_PAGE,
    RESET_BUTTON_KEY,
    TEST_KEY,
    TEXT_BUTTON_KEY,
    TEXT_BY_CLAUDE,
    TEXT_EFFORT_KEY,
    TIMEOUT_KEY,
    WORD_LISTS_KEY,
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


class ProgressPageTest(UiTest):
    def progress(self, paths: Iterable[Path]) -> AppTest:
        app = self.open_folder(paths)
        app.switch_page(PROGRESS_PAGE).run()
        self.assert_clean(app)
        return app

    def test_without_results(self) -> None:
        app = _start()
        app.switch_page(PROGRESS_PAGE).run()
        self.assert_clean(app)
        self.assertEqual([info.value for info in app.info], [NO_RESULTS])

    def test_needs_two_counted_results(self) -> None:
        # One result, plus one that is aborted.
        app = self.progress([fixtures.REAL, fixtures.ABORTED])
        self.assertEqual([info.value for info in app.info], [NEED_TWO])

    def test_progress_of_the_most_common_test_type(self) -> None:
        app = self.progress([fixtures.PROGRESS])
        self.assertEqual([h.value for h in app.header], ["Progress"])
        self.assertEqual(app.selectbox(key=TEST_KEY).value, "words 10")
        self.assertEqual(
            [s.value for s in app.subheader],
            ["code python", "english 1k", "Latest vs average", "Recurring problems"],
        )
        # wpm and acc for each of the two word lists.
        self.assertEqual(len(app.main.get("vega_lite_chart")), 4)
        trends, recurring = (frame.value for frame in app.main.dataframe)
        self.assertEqual(list(trends["word list"]), ["code python", "english 1k"])
        self.assertEqual(list(trends["change in wpm"]), ["+2.00", "+4.67"])
        self.assertEqual(
            list(trends["compared with"]),
            ["mean of 1 earlier result", "mean of 3 earlier results"],
        )
        self.assertEqual(list(recurring["word"]), ["century", "salt", "self", "they"])
        captions = [caption.value for caption in app.main.caption]
        self.assertIn("Key confusions seen at least twice: e→r ×2", captions)

    def test_test_type_filter(self) -> None:
        app = self.progress([fixtures.PROGRESS])
        app.selectbox(key=TEST_KEY).select("time 15").run()
        self.assert_clean(app)
        self.assertEqual(
            [s.value for s in app.subheader],
            ["english 1k", "Latest vs average", "Recurring problems"],
        )
        trends = app.main.dataframe[0].value
        self.assertEqual(list(trends["test"]), ["time 15"])

    def test_nothing_recurring(self) -> None:
        app = self.progress([fixtures.REAL, fixtures.CHART_ERROR])
        self.assertIn(NO_RECURRING, [info.value for info in app.info])
        self.assertIn(
            "Key confusions seen at least twice: none",
            [caption.value for caption in app.main.caption],
        )

    def test_goal_from_the_analysis_page_carries_over(self) -> None:
        app = self.open_folder([fixtures.PROGRESS])
        app.switch_page(ANALYSIS_PAGE).run()
        app.number_input(key=GOAL_KEY).set_value(97.5).run()
        app.switch_page(PROGRESS_PAGE).run()
        self.assert_clean(app)
        self.assertEqual(app.number_input(key=GOAL_KEY).value, 97.5)


GROUPS = {
    "groups": [
        {
            "name": "Left index reach",
            "cause": "The left index finger reaches for r.",
            "words": ["they", "salt"],
            "confusions": ["e→r"],
        }
    ]
}
TEXT = "they sell salt and they tell the century"


class PracticePageTest(UiTest):
    def practice(
        self,
        paths: Iterable[Path],
        *replies: Any,
        key: str | None = "test-key",
    ) -> tuple[AppTest, mock.MagicMock]:
        """Opens the Practice page with a fake client that gives `replies`."""
        self.enterContext(mock.patch.dict(os.environ))
        os.environ.pop(KEY_ENV, None)
        if key is not None:
            os.environ[KEY_ENV] = key
        client = fixtures.fake_claude(*replies)
        self.enterContext(mock.patch.object(ui, "claude_client", return_value=client))
        app = self.open_folder(paths)
        app.switch_page(PRACTICE_PAGE).run()
        self.assert_clean(app)
        return app, client

    def press(self, app: AppTest, key: str) -> AppTest:
        app.button(key=key).click().run()
        self.assert_clean(app)
        return app

    def captions(self, app: AppTest) -> list[str]:
        return [caption.value for caption in app.main.caption]

    def test_without_results(self) -> None:
        app = _start()
        app.switch_page(PRACTICE_PAGE).run()
        self.assert_clean(app)
        self.assertEqual([info.value for info in app.info], [NO_RESULTS])

    def test_needs_two_counted_results(self) -> None:
        app, _ = self.practice([fixtures.REAL, fixtures.ABORTED])
        self.assertEqual([info.value for info in app.info], [PRACTICE_NEEDS_TWO])

    def test_nothing_to_practise(self) -> None:
        app, _ = self.practice([fixtures.REAL, fixtures.CHART_ERROR])
        self.assertEqual([info.value for info in app.info], [NOTHING_TO_PRACTISE])
        self.assertEqual(len(app.button), 0)

    def problem_words(self, app: AppTest) -> list[str]:
        # The first table is the one under "Which results".
        return list(app.main.dataframe[1].value["word"])

    def test_without_the_key(self) -> None:
        app, client = self.practice([fixtures.PROGRESS], key=None)
        self.assertIn(PRACTICE_INTRO, [m.value for m in app.main.markdown])
        self.assertEqual([h.value for h in app.subheader], ["Problems"])
        self.assertEqual(self.problem_words(app), ["century", "salt", "self", "they"])
        problems = app.main.dataframe[1].value
        self.assertEqual(list(problems["typos"])[-1], '"e"→"r" ×2')
        self.assertIn(
            "Key confusions seen at least twice: e→r ×2 (wrong key: neighbour)",
            self.captions(app),
        )
        self.assertEqual([info.value for info in app.info], [NO_KEY])
        self.assertEqual(len(app.button), 0)
        client.beta.messages.create.assert_not_called()

    def test_what_the_problems_are_based_on(self) -> None:
        app, _ = self.practice([fixtures.PROGRESS])
        self.assertIn(
            "Based on the newest 8 results of 8 in these word lists, from "
            "2026-11-10 to 2026-11-13, of every test type. Aborted results "
            "don't count.",
            self.captions(app),
        )
        self.assertEqual(app.main.expander[0].label, "Which results")
        results = app.main.dataframe[0].value
        self.assertEqual(len(results), 8)
        self.assertEqual(list(results["copied"])[0], "2026-11-13 20:30")

    def test_word_list_filter(self) -> None:
        app, _ = self.practice([fixtures.PROGRESS])
        word_lists = app.multiselect(key=WORD_LISTS_KEY)
        self.assertEqual(word_lists.value, ["code python", "english 1k"])
        word_lists.set_value(["english 1k"]).run()
        self.assert_clean(app)
        self.assertEqual(self.problem_words(app), ["century", "salt"])
        self.assertIn("Key confusions seen at least twice: none", self.captions(app))
        app.switch_page(PROGRESS_PAGE).run()
        # The Progress page doesn't filter by word list.
        recurring = app.main.dataframe[1].value
        self.assertEqual(list(recurring["word"]), ["century", "salt", "self", "they"])
        app.switch_page(PRACTICE_PAGE).run()
        self.assert_clean(app)
        self.assertEqual(app.multiselect(key=WORD_LISTS_KEY).value, ["english 1k"])
        self.assertEqual(self.problem_words(app), ["century", "salt"])

    def test_no_word_list_chosen(self) -> None:
        app, _ = self.practice([fixtures.PROGRESS])
        app.multiselect(key=WORD_LISTS_KEY).set_value([]).run()
        self.assert_clean(app)
        self.assertEqual([info.value for info in app.info], [NO_WORD_LISTS])

    def test_what_claude_gets_shows_settings_instructions_and_data(self) -> None:
        app, _ = self.practice([fixtures.PROGRESS])
        self.assertEqual(
            [e.label for e in app.main.expander],
            ["Which results", "Claude settings"] + ["What Claude gets"] * 2,
        )
        blocks = [block.value for block in app.main.code]
        self.assertIn(GROUP_INSTRUCTIONS, blocks)
        self.assertIn(TEXT_INSTRUCTIONS, blocks)
        self.assertTrue(any('"keyboard": "US QWERTY' in block for block in blocks))
        self.assertIn(
            "claude-opus-5-5 · effort high · fallback model if Claude declines: "
            "on · 120 s per attempt",
            self.captions(app),
        )

    def test_claude_settings(self) -> None:
        app, client = self.practice(
            [fixtures.PROGRESS],
            fixtures.claude_message(GROUPS),
            fixtures.claude_message(GROUPS),
        )
        self.assertIn(
            "Claude Opus 5.5 (claude-opus-5-5) · effort high for cause groups, "
            "medium for practice text · 120 s per attempt",
            self.captions(app),
        )
        app.selectbox(key=MODEL_KEY).select("claude-haiku-5-5").run()
        app.select_slider(key=GROUP_EFFORT_KEY).set_value("low").run()
        app.number_input(key=TIMEOUT_KEY).set_value(300.0).run()
        self.assert_clean(app)
        self.assertIn(
            "claude-haiku-5-5 · effort low · fallback model if Claude declines: "
            "none for this model · 300 s per attempt",
            self.captions(app),
        )
        self.press(app, GROUP_BUTTON_KEY)
        sent = client.beta.messages.create.call_args.kwargs
        self.assertEqual(sent["model"], "claude-haiku-5-5")
        self.assertEqual(sent["output_config"]["effort"], "low")
        self.assertEqual(sent["timeout"], 300.0)

        # The settings stay after a page switch, until they are reset.
        app.switch_page(REPLAY_PAGE).run()
        app.switch_page(PRACTICE_PAGE).run()
        self.assert_clean(app)
        self.assertEqual(app.selectbox(key=MODEL_KEY).value, "claude-haiku-5-5")
        self.press(app, RESET_BUTTON_KEY)
        self.assertEqual(app.selectbox(key=MODEL_KEY).value, "claude-opus-5-5")
        self.assertEqual(app.select_slider(key=GROUP_EFFORT_KEY).value, "high")
        self.assertEqual(app.select_slider(key=TEXT_EFFORT_KEY).value, "medium")
        self.assertEqual(app.number_input(key=TIMEOUT_KEY).value, 120.0)
        self.press(app, GROUP_BUTTON_KEY)
        self.assertEqual(
            client.beta.messages.create.call_args.kwargs["model"], "claude-opus-5-5"
        )

    def test_group_then_write_a_text_for_the_group(self) -> None:
        app, client = self.practice(
            [fixtures.PROGRESS],
            fixtures.claude_message(GROUPS),
            fixtures.claude_message({"text": f"  {TEXT}\n"}),
        )
        self.assertEqual(
            [h.value for h in app.subheader],
            ["Problems", "Cause groups", "Practice text"],
        )
        self.assertEqual(app.selectbox(key=FOCUS_KEY).options, [ALL_PROBLEMS])
        client.beta.messages.create.assert_not_called()

        self.press(app, GROUP_BUTTON_KEY)
        groups = app.main.dataframe[2].value
        self.assertEqual(list(groups["group"]), ["Left index reach"])
        self.assertEqual(list(groups["words"]), ["they, salt"])
        self.assertIn("Not in a group: century, self", self.captions(app))
        self.assertIn(GROUPS_BY_CLAUDE, self.captions(app))
        self.assertIn(
            "claude-opus-5-5 used 1,234 input and 56 output tokens.",
            self.captions(app),
        )
        self.assertEqual(
            app.selectbox(key=FOCUS_KEY).options, [ALL_PROBLEMS, "Left index reach"]
        )

        app.selectbox(key=FOCUS_KEY).select("Left index reach").run()
        app.slider(key=LENGTH_KEY).set_value(30).run()
        self.press(app, TEXT_BUTTON_KEY)
        sent = client.beta.messages.create.call_args.kwargs["messages"][0]
        self.assertIn('"name": "Left index reach"', sent["content"])
        self.assertIn('"length_words": 30', sent["content"])
        self.assertIn(TEXT, [block.value for block in app.main.code])
        self.assertIn(TEXT_BY_CLAUDE, self.captions(app))
        self.assertIn("8 words", [m.value for m in app.main.markdown])
        coverage = app.main.dataframe[3].value
        self.assertEqual(list(coverage["word"]), ["salt", "they"])
        self.assertEqual(list(coverage["times in text"]), [1, 2])

    def test_answers_and_inputs_stay_after_a_page_switch(self) -> None:
        app, _ = self.practice(
            [fixtures.PROGRESS],
            fixtures.claude_message(GROUPS),
            fixtures.claude_message({"text": TEXT}),
        )
        self.press(app, GROUP_BUTTON_KEY)
        app.selectbox(key=FOCUS_KEY).select("Left index reach").run()
        self.press(app, TEXT_BUTTON_KEY)
        app.switch_page(PROGRESS_PAGE).run()
        app.switch_page(PRACTICE_PAGE).run()
        self.assert_clean(app)
        self.assertEqual(app.selectbox(key=FOCUS_KEY).value, "Left index reach")
        self.assertIn(GROUPS_BY_CLAUDE, self.captions(app))
        self.assertIn(TEXT, [block.value for block in app.main.code])
        self.assertNotIn(EARLIER_PROBLEMS, self.captions(app))

    def test_a_new_result_marks_the_answer_as_earlier(self) -> None:
        app, _ = self.practice([fixtures.PROGRESS], fixtures.claude_message(GROUPS))
        self.press(app, GROUP_BUTTON_KEY)
        self.assertNotIn(EARLIER_PROBLEMS, self.captions(app))
        folder = Path(app.text_input(key=FOLDER_KEY).value)
        fixtures.copy_to(folder, [fixtures.TYPOS])
        app.run()
        self.assert_clean(app)
        self.assertIn(EARLIER_PROBLEMS, self.captions(app))
        self.assertIn(GROUPS_BY_CLAUDE, self.captions(app))

    def test_an_error_keeps_the_earlier_answer(self) -> None:
        app, _ = self.practice(
            [fixtures.PROGRESS],
            fixtures.claude_message(GROUPS),
            fixtures.api_error(anthropic.OverloadedError, 529),
        )
        self.press(app, GROUP_BUTTON_KEY)
        self.press(app, GROUP_BUTTON_KEY)
        self.assertEqual([error.value for error in app.error], [BUSY])
        self.assertIn(GROUPS_BY_CLAUDE, self.captions(app))


if __name__ == "__main__":
    unittest.main()
