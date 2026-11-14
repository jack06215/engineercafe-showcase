"""UI tests: drive the page with AppTest against run folders written by hand. No agent starts."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from streamlit.testing.v1 import AppTest

from packages.vega_lite_ai import ui
from packages.vega_lite_ai.runs import (
    CHART,
    DATA,
    LOG,
    MAX_BUDGET_USD,
    RunError,
    append_event,
    write_pid,
    write_report,
)
from packages.vega_lite_ai.ui import (
    OUTPUT_KEY,
    START_KEY,
    STOP_KEY,
    describe_event,
)

APP = Path(__file__).with_name("main.py")
TIMEOUT = 60
CHART_SPEC = {
    "mark": {"type": "line"},
    "encoding": {
        "x": {"field": "年", "type": "ordinal"},
        "y": {"field": "人口", "type": "quantitative"},
    },
    "data": {"values": [{"年": 2024, "人口": 1000}, {"年": 2025, "人口": 1100}]},
}
RECORDED: dict[str, Any] = {
    "sources": [
        {
            "file": "raw/01_suikei.xlsx",
            "url": "https://www.city.fukuoka.lg.jp/a.xlsx",
            "final_url": "https://www.city.fukuoka.lg.jp/b.xlsx",
            "sha256": "abcdef0123456789",
            "bytes": 10,
        }
    ],
    "gate_failures": 2,
    "files": {},
    "not_checked": ["数値が正しいことは確認していません"],
    "permission_denials": [{"tool_name": "Edit"}, {"tool_name": "Edit"}],
    "result": "success",
    "cost_usd": 1.25,
    "turns": 30,
    "duration_ms": 90_000,
    "models": ["claude-opus-5-5"],
}
AGENT = {
    "dataset": "過去の推計人口",
    "why_this_dataset": "長期の推移が分かるため",
    "columns_plotted": ["年", "人口"],
    "data_checks": ["男 + 女 = 人口"],
    "caveats": ["2021 年以降は改定値"],
    "not_verified": ["ブラウザでの表示"],
}


def report(status: str, **fields: Any) -> dict[str, Any]:
    return {
        "status": status,
        "topic": "人口",
        "no_chart_reason": None,
        "error": None,
        "recorded": RECORDED,
        "agent": AGENT,
        **fields,
    }


class UiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def make_run(
        self, name: str = "20261101-100000", topic: str = "人口の推移"
    ) -> Path:
        run_dir = self.root / name
        run_dir.mkdir()
        append_event(run_dir, "started", topic=topic)
        return run_dir

    def make_chart_run(self, name: str = "20261101-100000") -> Path:
        run_dir = self.make_run(name)
        (run_dir / CHART).write_text(json.dumps(CHART_SPEC), encoding="utf-8")
        (run_dir / DATA).write_text("年,人口\n2024,1000\n", encoding="utf-8")
        write_report(run_dir, report("chart"))
        return run_dir

    def start(self, start_run: Any = None) -> AppTest:
        app = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
        app.session_state[OUTPUT_KEY] = self.root
        if start_run is not None:
            app.session_state[START_KEY] = start_run
        return app.run()

    def assert_clean(self, app: AppTest) -> None:
        self.assertFalse(app.exception, [e.value for e in app.exception])

    def shown(self, app: AppTest) -> str:
        parts = [
            element.value
            for elements in (
                app.markdown,
                app.code,
                app.info,
                app.warning,
                app.error,
                app.caption,
                app.header,
            )
            for element in elements
        ]
        return "\n".join(str(part) for part in parts)

    def charts(self, app: AppTest) -> list[Any]:
        return list(app.get("vega_lite_chart"))


class StartPageTest(UiTestCase):
    def test_an_empty_output_folder_shows_just_the_form(self) -> None:
        app = self.start()
        self.assert_clean(app)
        self.assertEqual(len(app.text_input), 1)
        self.assertEqual(len(app.sidebar.radio), 0)

    def test_says_what_a_run_can_cost(self) -> None:
        self.assertIn(f"${MAX_BUDGET_USD:.2f}", self.shown(self.start()))

    def test_outside_bazel_run_it_says_what_to_do(self) -> None:
        app = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
        with mock.patch.dict(os.environ, clear=True):
            app.run()
        self.assert_clean(app)
        self.assertIn("bazel run", self.shown(app))


class StartingTest(UiTestCase):
    def test_a_blank_topic_starts_nothing(self) -> None:
        started: list[str] = []

        def start_run(_root: Path, topic: str) -> Path:
            started.append(topic)
            return self.make_run()

        app = self.start(start_run)
        app.text_input[0].input("   ")
        app.button[0].click().run()
        self.assert_clean(app)
        self.assertEqual(started, [])
        self.assertIn("テーマを入力", self.shown(app))

    def test_a_topic_starts_a_run_and_follows_it(self) -> None:
        started: list[str] = []

        def start_run(_root: Path, topic: str) -> Path:
            started.append(topic)
            run_dir = self.make_run(topic=topic)
            write_pid(run_dir, os.getpid())
            return run_dir

        app = self.start(start_run)
        app.text_input[0].input(" 人口の推移 ")
        app.button[0].click().run()
        self.assert_clean(app)
        self.assertEqual(started, ["人口の推移"])
        self.assertIn("実行中: 人口の推移", self.shown(app))

    def test_a_refused_start_shows_why(self) -> None:
        def start_run(_root: Path, _topic: str) -> Path:
            raise RunError("実行中のものがあります")

        app = self.start(start_run)
        app.text_input[0].input("人口")
        app.button[0].click().run()
        self.assert_clean(app)
        self.assertIn("実行中のものがあります", self.shown(app))


class WatchingTest(UiTestCase):
    def active_run(self) -> Path:
        run_dir = self.make_run()
        write_pid(run_dir, os.getpid())
        append_event(run_dir, "tool", who="main", name="Agent", detail="データ探し")
        append_event(run_dir, "gate_failed", errors=["unknown column `人`"])
        return run_dir

    def test_shows_the_live_log(self) -> None:
        self.active_run()
        app = self.start()
        self.assert_clean(app)
        shown = self.shown(app)
        self.assertIn("実行中: 人口の推移", shown)
        self.assertIn("finder に依頼: データ探し", shown)
        self.assertIn("unknown column `人`", shown)

    def test_a_second_run_cannot_be_started_meanwhile(self) -> None:
        self.active_run()
        app = self.start()
        submit = next(button for button in app.button if button.label == "グラフを作る")
        self.assertTrue(submit.disabled)

    def test_stop_signals_the_agent(self) -> None:
        run_dir = self.active_run()
        app = self.start()
        with mock.patch.object(ui, "stop_run") as stop_run:
            app.button(key=STOP_KEY).click().run()
        self.assert_clean(app)
        stop_run.assert_called_once_with(run_dir)


class ResultTest(UiTestCase):
    def test_a_chart_comes_with_its_data_and_its_record(self) -> None:
        self.make_chart_run()
        app = self.start()
        self.assert_clean(app)
        self.assertEqual(len(self.charts(app)), 1)
        self.assertEqual(len(app.dataframe), 1)
        shown = self.shown(app)
        self.assertIn("過去の推計人口", shown)
        self.assertIn("男 + 女 = 人口", shown)
        self.assertIn("ブラウザでの表示", shown)
        self.assertIn("raw/01_suikei.xlsx", shown)
        self.assertIn("Edit × 2", shown)

    def test_always_says_what_the_gate_did_not_check(self) -> None:
        self.make_chart_run()
        warnings = [warning.value for warning in self.start().warning]
        self.assertTrue(any("数値が正しいこと" in text for text in warnings), warnings)

    def test_shows_the_numbers_code_recorded(self) -> None:
        self.make_chart_run()
        metrics = {metric.label: metric.value for metric in self.start().metric}
        self.assertEqual(
            metrics,
            {"費用": "$1.25", "ターン": "30", "時間": "1.5 分", "チェック不合格": "2"},
        )

    def test_a_run_with_no_chart_says_why(self) -> None:
        run_dir = self.make_run()
        write_report(
            run_dir, report("no_chart", no_chart_reason="合うデータがありません")
        )
        app = self.start()
        self.assert_clean(app)
        self.assertEqual(self.charts(app), [])
        self.assertIn("合うデータがありません", self.shown(app))

    def test_a_failed_run_says_what_ended_it(self) -> None:
        run_dir = self.make_run()
        failed = {**RECORDED, "result": "error_max_budget_usd"}
        write_report(run_dir, report("failed", recorded=failed, agent=None))
        app = self.start()
        self.assert_clean(app)
        self.assertEqual(self.charts(app), [])
        self.assertIn("error_max_budget_usd", self.shown(app))

    def test_a_stopped_run_has_empty_numbers_rather_than_a_crash(self) -> None:
        run_dir = self.make_run()
        stopped = {
            **RECORDED,
            "cost_usd": None,
            "turns": None,
            "duration_ms": None,
            "result": None,
            "permission_denials": None,
        }
        write_report(run_dir, report("stopped", recorded=stopped, agent=None))
        app = self.start()
        self.assert_clean(app)
        self.assertIn("途中で停止", self.shown(app))
        self.assertEqual(app.metric[0].value, "—")

    def test_a_crash_with_no_report_shows_the_process_log(self) -> None:
        run_dir = self.make_run()
        (run_dir / LOG).write_text("Traceback: boom", encoding="utf-8")
        app = self.start()
        self.assert_clean(app)
        self.assertIn("Traceback: boom", self.shown(app))


class PastRunsTest(UiTestCase):
    def test_the_newest_run_shows_first_and_an_older_one_on_request(self) -> None:
        self.make_chart_run("20261101-100000")
        newer = self.make_run("20261101-110000")
        write_report(newer, report("no_chart", no_chart_reason="ありません"))
        app = self.start()
        radio = app.sidebar.radio[0]
        self.assertEqual(radio.value, "20261101-110000")
        self.assertEqual(self.charts(app), [])
        radio.set_value("20261101-100000").run()
        self.assert_clean(app)
        self.assertEqual(len(self.charts(app)), 1)


class DescribeEventTest(unittest.TestCase):
    def test_every_event_a_run_writes_has_a_line_or_is_meant_to_be_silent(self) -> None:
        for event in (
            {"kind": "text", "text": "x"},
            {"kind": "download", "file": "raw/a"},
            {"kind": "download_failed", "message": "x"},
            {"kind": "gate_passed"},
            {"kind": "stop_blocked", "reason": "x"},
            {"kind": "denied", "reason": "x"},
            {"kind": "no_chart", "reason": "x"},
            {"kind": "tool", "who": "main", "name": "StructuredOutput"},
            {"kind": "tool", "who": "main", "name": "Bash", "detail": "ls"},
            {"kind": "tool", "who": "finder", "name": "WebFetch", "detail": "u"},
        ):
            self.assertIsNotNone(describe_event(event), event)
        for event in (
            {"kind": "started", "topic": "x"},
            {"kind": "finished", "status": "chart"},
            {"kind": "tool", "who": "main", "name": "submit_chart"},
        ):
            self.assertIsNone(describe_event(event), event)


if __name__ == "__main__":
    unittest.main()
