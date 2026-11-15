"""Tests for session.py: which turn holds the current chart, and which requests count as recent."""

import unittest

import pandas

from packages.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
    Encoding,
)
from packages.vega_lite_chat.profile import (
    profile_frame,
)
from packages.vega_lite_chat.session import (
    Answer,
    ChatSession,
    Turn,
)
from packages.vega_lite_chat.translator import Attempt

LINE = ChartSpec(
    mark="line",
    x=Encoding(field="月", type="temporal"),
    y=Encoding(field="売上", type="quantitative"),
)
BAR = ChartSpec(
    mark="bar",
    x=Encoding(field="月", type="temporal"),
    y=Encoding(field="売上", type="quantitative"),
)
VEGA_LITE = {"mark": "line"}  # the session never looks inside it


def _session() -> ChatSession:
    df = pandas.DataFrame({"月": ["2025-01", "2025-02"], "売上": [1, 2]})
    profile = profile_frame(df, sample_rows=2, seed=0, max_listed_values=20)
    return ChatSession(source_name="sales.csv", df=df, profile=profile)


def _chart_turn(request: str, chart: ChartSpec, *, auto: bool = False) -> Turn:
    return Turn(
        request=request,
        auto=auto,
        reply=AssistantTurn(chart=chart, message="描きました。"),
        vega_lite=VEGA_LITE,
        attempts=(Attempt(raw="{}", errors=()),),
    )


def _question_turn(request: str) -> Turn:
    return Turn(
        request=request,
        auto=False,
        reply=AssistantTurn(chart=None, message="どの列ですか？"),
        vega_lite=None,
        attempts=(Attempt(raw="{}", errors=()),),
    )


def _failed_turn(request: str) -> Turn:
    attempt = Attempt(raw="{", errors=("not JSON",))
    return Turn(
        request=request, auto=False, reply=None, vega_lite=None, attempts=(attempt,) * 3
    )


class CurrentChartTest(unittest.TestCase):
    def test_starts_without_a_chart(self) -> None:
        session = _session()
        self.assertIsNone(session.current)
        self.assertIsNone(session.current_chart())

    def test_a_chart_turn_becomes_current(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        session.add_turn(_chart_turn("棒にして", BAR))
        self.assertEqual(session.current, 1)
        self.assertEqual(session.current_chart(), BAR)

    def test_a_question_keeps_the_current_chart(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        session.add_turn(_question_turn("利益で"))
        self.assertEqual(session.current, 0)
        self.assertEqual(session.current_chart(), LINE)

    def test_a_failed_turn_keeps_the_current_chart(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        session.add_turn(_failed_turn("???"))
        self.assertEqual(session.current, 0)

    def test_a_compiler_bug_keeps_the_current_chart(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        broken = Turn(
            request="棒にして",
            auto=False,
            reply=AssistantTurn(chart=BAR, message="描きました。"),
            vega_lite=VEGA_LITE,
            attempts=(),
            error="schema",
        )
        session.add_turn(broken)
        self.assertEqual(session.current, 0)
        self.assertFalse(broken.has_chart)

    def test_an_answer_keeps_the_current_chart(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        session.add_turn(Answer(request="どんな列がある？", text="2 つです。"))
        self.assertEqual(session.current, 0)
        self.assertEqual(session.current_chart(), LINE)
        with self.assertRaises(ValueError):
            session.continue_from(1)

    def test_continue_from_an_earlier_chart(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        session.add_turn(_chart_turn("棒にして", BAR))
        session.continue_from(0)
        self.assertEqual(session.current, 0)
        self.assertEqual(session.current_chart(), LINE)

    def test_continue_from_a_turn_without_a_chart_is_refused(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        session.add_turn(_question_turn("利益で"))
        with self.assertRaises(ValueError):
            session.continue_from(1)
        with self.assertRaises(IndexError):
            session.continue_from(5)
        self.assertEqual(session.current, 0)


class RecentRequestsTest(unittest.TestCase):
    def test_the_automatic_request_never_counts(self) -> None:
        session = _session()
        session.add_turn(
            _chart_turn("この表でいちばん分かりやすいグラフ", LINE, auto=True)
        )
        self.assertEqual(session.recent_requests(3), [])

    def test_the_last_n_typed_requests_oldest_first(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("最初", LINE, auto=True))
        for request in ["地域で色分け", "2025年だけ", "利益で", "積み上げにして"]:
            session.add_turn(_question_turn(request))
        self.assertEqual(
            session.recent_requests(3), ["2025年だけ", "利益で", "積み上げにして"]
        )
        self.assertEqual(session.recent_requests(0), [])

    def test_failed_and_question_turns_still_count(self) -> None:
        session = _session()
        session.add_turn(_failed_turn("???"))
        session.add_turn(_question_turn("利益で"))
        self.assertEqual(session.recent_requests(3), ["???", "利益で"])

    def test_answers_never_count(self) -> None:
        session = _session()
        session.add_turn(_chart_turn("棒にして", BAR))
        session.add_turn(Answer(request="どんな列がある？", text="2 つです。"))
        self.assertEqual(session.recent_requests(3), ["棒にして"])

    def test_a_reworded_request_counts_as_the_tool_got_it(self) -> None:
        session = _session()
        turn = Turn(
            request="売上がいちばん多い地域は？",
            auto=False,
            reply=AssistantTurn(chart=BAR, message="描きました。"),
            vega_lite=VEGA_LITE,
            attempts=(),
            tool_request="地域別の売上の合計を棒グラフで",
        )
        session.add_turn(turn)
        self.assertEqual(turn.translator_request, "地域別の売上の合計を棒グラフで")
        self.assertEqual(session.recent_requests(3), ["地域別の売上の合計を棒グラフで"])


if __name__ == "__main__":
    unittest.main()
