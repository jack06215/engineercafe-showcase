"""Tests for translator: the repair loop, driven by a scripted stand-in for the model."""

import unittest
from collections.abc import Sequence

import pandas
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from packages.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
    Encoding,
)
from packages.vega_lite_chat.llm import (
    OllamaUnavailable,
    RawReply,
)
from packages.vega_lite_chat.profile import (
    DataProfile,
    profile_frame,
)
from packages.vega_lite_chat.translator import (
    Attempt,
    translate,
)

GOOD_CHART = ChartSpec(
    mark="bar",
    x=Encoding(field="地域", type="nominal"),
    y=Encoding(field="売上", type="quantitative", aggregate="sum"),
)
# 売上額 is not a column, so check_chart rejects it.
BAD_CHART = ChartSpec(
    mark="bar",
    x=Encoding(field="地域", type="nominal"),
    y=Encoding(field="売上額", type="quantitative", aggregate="sum"),
)


def _profile() -> DataProfile:
    frame = pandas.DataFrame(
        {
            "月": pandas.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
            "地域": ["福岡", "東京", "福岡"],
            "売上": [320, 500, 410],
        }
    )
    return profile_frame(frame, sample_rows=3, seed=0, max_listed_values=20)


def _reply(chart: ChartSpec | None, message: str = "ok") -> RawReply:
    turn = AssistantTurn(chart=chart, message=message)
    return RawReply(text=turn.model_dump_json(), turn=turn, parse_error=None)


UNPARSED = RawReply(
    text='{"chart": {"mark": "pie"',
    turn=None,
    parse_error="reply: Invalid JSON: EOF while parsing an object",
)


class ScriptedModel:
    """Returns (or raises) the scripted replies in order and records what it was sent."""

    def __init__(self, *script: RawReply | Exception) -> None:
        self.script = list(script)
        self.calls: list[list[BaseMessage]] = []

    def __call__(self, messages: Sequence[BaseMessage]) -> RawReply:
        self.calls.append(list(messages))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


MESSAGES: list[BaseMessage] = [
    SystemMessage(content="system"),
    HumanMessage(content="地域ごとの売上"),
]


class TranslateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _profile()
        self.progress: list[tuple[int, tuple[str, ...]]] = []

    def test_first_reply_passes(self) -> None:
        model = ScriptedModel(_reply(GOOD_CHART, "地域ごとの売上です。"))

        result = translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        self.assertIsNotNone(result.turn)
        assert result.turn is not None
        self.assertEqual(result.turn.chart, GOOD_CHART)
        self.assertEqual(result.turn.message, "地域ごとの売上です。")
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0].errors, ())
        self.assertEqual(model.calls, [MESSAGES])

    def test_two_failures_then_a_pass(self) -> None:
        model = ScriptedModel(_reply(BAD_CHART), UNPARSED, _reply(GOOD_CHART))

        result = translate(
            model,
            MESSAGES,
            self.profile,
            max_calls=3,
            on_attempt=lambda number, errors: self.progress.append(
                (number, tuple(errors))
            ),
        )

        assert result.turn is not None
        self.assertEqual(result.turn.chart, GOOD_CHART)
        self.assertEqual(len(result.attempts), 3)
        self.assertTrue(result.attempts[0].errors)
        self.assertTrue(result.attempts[1].errors)
        self.assertEqual(result.attempts[2].errors, ())
        self.assertEqual(len(model.calls), 3)
        # Progress: nothing to report before the first call, then each previous failure.
        self.assertEqual([number for number, _ in self.progress], [1, 2, 3])
        self.assertEqual(self.progress[0][1], ())
        self.assertEqual(self.progress[1][1], result.attempts[0].errors)
        self.assertEqual(self.progress[2][1], result.attempts[1].errors)

    def test_every_attempt_fails(self) -> None:
        model = ScriptedModel(_reply(BAD_CHART), _reply(BAD_CHART), _reply(BAD_CHART))

        result = translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        self.assertIsNone(result.turn)
        self.assertEqual(len(result.attempts), 3)
        self.assertTrue(all(attempt.errors for attempt in result.attempts))
        self.assertEqual(model.script, [])

    def test_max_calls_is_respected(self) -> None:
        model = ScriptedModel(_reply(BAD_CHART), _reply(GOOD_CHART))

        result = translate(
            model, MESSAGES, self.profile, max_calls=1, on_attempt=lambda *_: None
        )

        self.assertIsNone(result.turn)
        self.assertEqual(len(model.calls), 1)

    def test_unknown_column_error_names_it(self) -> None:
        model = ScriptedModel(_reply(BAD_CHART), _reply(GOOD_CHART))

        result = translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        self.assertIn("売上額", " ".join(result.attempts[0].errors))

    def test_parse_failure_is_repaired(self) -> None:
        model = ScriptedModel(UNPARSED, _reply(GOOD_CHART))

        result = translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        assert result.turn is not None
        self.assertEqual(
            result.attempts[0],
            Attempt(
                raw=UNPARSED.text,
                errors=(
                    (
                        "the reply does not match the JSON schema: "
                        "reply: Invalid JSON: EOF while parsing an object"
                    ),
                ),
            ),
        )

    def test_clarifying_question_is_not_checked(self) -> None:
        model = ScriptedModel(_reply(None, "どの列で色分けしますか？"))

        result = translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        assert result.turn is not None
        self.assertIsNone(result.turn.chart)
        self.assertEqual(result.turn.message, "どの列で色分けしますか？")
        self.assertEqual(len(result.attempts), 1)

    def test_repair_request_carries_the_reply_and_the_errors(self) -> None:
        bad = _reply(BAD_CHART)
        model = ScriptedModel(bad, _reply(GOOD_CHART))

        result = translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        second_call = model.calls[1]
        self.assertEqual(second_call[: len(MESSAGES)], MESSAGES)
        self.assertEqual(len(second_call), len(MESSAGES) + 2)
        echoed, repair = second_call[len(MESSAGES) :]
        self.assertIsInstance(echoed, AIMessage)
        self.assertEqual(echoed.content, bad.text)
        self.assertIsInstance(repair, HumanMessage)
        assert isinstance(repair.content, str)
        for error in result.attempts[0].errors:
            self.assertIn(f"- {error}", repair.content)
        self.assertIn("Reply again with the corrected JSON.", repair.content)

    def test_conversation_keeps_growing(self) -> None:
        model = ScriptedModel(_reply(BAD_CHART), UNPARSED, _reply(GOOD_CHART))

        translate(
            model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        self.assertEqual(
            [len(call) for call in model.calls],
            [len(MESSAGES), len(MESSAGES) + 2, len(MESSAGES) + 4],
        )

    def test_caller_messages_are_not_mutated(self) -> None:
        messages = list(MESSAGES)
        model = ScriptedModel(_reply(BAD_CHART), _reply(GOOD_CHART))

        translate(
            model, messages, self.profile, max_calls=3, on_attempt=lambda *_: None
        )

        self.assertEqual(messages, MESSAGES)

    def test_ollama_unavailable_propagates_uncounted(self) -> None:
        model = ScriptedModel(OllamaUnavailable("Ollama に接続できません"))

        with self.assertRaises(OllamaUnavailable):
            translate(
                model,
                MESSAGES,
                self.profile,
                max_calls=3,
                on_attempt=lambda number, errors: self.progress.append(
                    (number, tuple(errors))
                ),
            )

        self.assertEqual(len(model.calls), 1)
        self.assertEqual(self.progress, [(1, ())])

    def test_ollama_unavailable_after_a_failure_still_propagates(self) -> None:
        model = ScriptedModel(_reply(BAD_CHART), OllamaUnavailable("timeout"))

        with self.assertRaises(OllamaUnavailable):
            translate(
                model, MESSAGES, self.profile, max_calls=3, on_attempt=lambda *_: None
            )


if __name__ == "__main__":
    unittest.main()
