"""Tests for prompts: the shipped prompts.yaml, its checks at load, and the messages for one call."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pandas
import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from packages.vibe_coding_club.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
    Encoding,
    Filter,
)
from packages.vibe_coding_club.vega_lite_chat.config import load_config
from packages.vibe_coding_club.vega_lite_chat.profile import (
    DataProfile,
    profile_frame,
)
from packages.vibe_coding_club.vega_lite_chat.prompts import (
    DEFAULT_PROMPTS,
    PromptBook,
    PromptError,
    build_messages,
    chart_yaml,
    chat_system_prompt,
    load_prompts,
    repair_message,
)

DATA = load_config().data
FIRST_CHART_REQUEST = "この表でいちばん分かりやすいグラフを1つ描いて"


def _shipped() -> dict[str, Any]:
    document = yaml.safe_load(DEFAULT_PROMPTS.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _profile() -> DataProfile:
    frame = pandas.DataFrame(
        {
            "月": pandas.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
            "地域": ["福岡", "東京", "福岡"],
            "売上": [320, 500, 410],
        }
    )
    return profile_frame(frame, sample_rows=3, seed=0, max_listed_values=20)


CURRENT = ChartSpec(
    mark="line",
    x=Encoding(field="月", type="temporal", timeUnit="yearmonth"),
    y=Encoding(field="売上", type="quantitative", aggregate="sum"),
)


class ShippedPromptsTest(unittest.TestCase):
    book: PromptBook

    @classmethod
    def setUpClass(cls) -> None:
        cls.book = load_prompts(data=DATA)

    def test_four_examples_load_and_pass_the_checks(self) -> None:
        self.assertEqual(len(self.book.examples), 4)
        self.assertEqual(self.book.first_chart_request, FIRST_CHART_REQUEST)

    def test_examples_cover_the_designed_cases(self) -> None:
        first, refinement, question, top_n = self.book.examples
        self.assertEqual(first.request, self.book.first_chart_request)
        self.assertIsNone(first.current)
        self.assertIsNotNone(refinement.current)
        self.assertIsNone(question.reply.chart)
        assert top_n.reply.chart is not None
        self.assertTrue(top_n.reply.chart.filters)
        self.assertIsNotNone(top_n.reply.chart.top_n)

    def test_profiles_are_kept_per_sample(self) -> None:
        samples = {example.sample for example in self.book.examples}
        self.assertEqual(set(self.book.example_profiles), samples)
        self.assertNotIn("fukuoka_weather.csv", samples)


class BrokenPromptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def _write(self, document: object) -> Path:
        path = self.directory / "prompts.yaml"
        path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def test_unknown_column_in_a_reply_fails(self) -> None:
        document = _shipped()
        document["examples"][0]["reply"]["chart"]["y"]["field"] = "売上額"

        with self.assertRaises(PromptError) as caught:
            load_prompts(self._write(document), data=DATA)

        self.assertIn("example 1", str(caught.exception))
        self.assertIn("reply", str(caught.exception))
        self.assertIn("売上額", str(caught.exception))

    def test_broken_current_chart_fails(self) -> None:
        document = _shipped()
        document["examples"][1]["current"]["x"]["field"] = "日付"

        with self.assertRaises(PromptError) as caught:
            load_prompts(self._write(document), data=DATA)

        self.assertIn("example 2", str(caught.exception))
        self.assertIn("current", str(caught.exception))

    def test_unknown_sample_fails(self) -> None:
        document = _shipped()
        document["examples"][2]["sample"] = "missing.csv"

        with self.assertRaises(PromptError) as caught:
            load_prompts(self._write(document), data=DATA)

        self.assertIn("missing.csv", str(caught.exception))

    def test_unknown_key_fails(self) -> None:
        document = _shipped()
        document["examples"][0]["notes"] = "typo"

        with self.assertRaises(PromptError):
            load_prompts(self._write(document), data=DATA)

    def test_reply_outside_the_schema_fails(self) -> None:
        document = _shipped()
        document["examples"][0]["reply"]["chart"]["mark"] = "pie"

        with self.assertRaises(PromptError):
            load_prompts(self._write(document), data=DATA)


class BuildMessagesTest(unittest.TestCase):
    book: PromptBook

    @classmethod
    def setUpClass(cls) -> None:
        cls.book = load_prompts(data=DATA)

    def test_order_is_system_then_example_pairs_then_the_request(self) -> None:
        messages = build_messages(self.book, _profile(), None, [], "地域ごとの売上")

        kinds = [type(message) for message in messages]
        self.assertEqual(
            kinds,
            [SystemMessage]
            + [HumanMessage, AIMessage] * len(self.book.examples)
            + [HumanMessage],
        )

    def test_the_schema_requires_filters_right_after_mark(self) -> None:
        # Ollama writes required keys first and may skip optional ones (see ChartSpec).
        schema = AssistantTurn.model_json_schema(by_alias=True)["$defs"]["ChartSpec"]

        self.assertEqual(schema["required"], ["mark", "filters"])
        self.assertEqual(list(schema["properties"])[:2], ["mark", "filters"])
        # Python callers may still leave filters out.
        self.assertEqual(ChartSpec(mark="bar").filters, [])

    def test_system_prompt_carries_the_instructions_and_the_schema(self) -> None:
        system = build_messages(self.book, _profile(), None, [], "x")[0].content
        assert isinstance(system, str)

        self.assertTrue(system.startswith(self.book.system.rstrip()))
        self.assertIn("JSON schema", system)
        # Vega-Lite's key names and the field descriptions reach the model as text.
        self.assertIn("timeUnit", system)
        self.assertIn("Column name exactly as in the profile", system)
        # pydantic's per-property titles are dropped; the `title` property itself stays.
        self.assertNotIn("Timeunit", system)
        self.assertIn("title:", system)

    def test_user_message_format(self) -> None:
        messages = build_messages(
            self.book,
            _profile(),
            CURRENT,
            ["地域で色分けして", "2025年だけ"],
            "積み上げにして",
        )
        last = messages[-1].content
        assert isinstance(last, str)

        headings = [
            "## Data profile",
            "## Current chart",
            "## Recent requests (oldest first)",
            "## Request",
        ]
        positions = [last.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(last.startswith("## Data profile\nrows: 3\n"))
        self.assertIn(chart_yaml(CURRENT).rstrip(), last)
        self.assertIn(
            "## Recent requests (oldest first)\n- 地域で色分けして\n- 2025年だけ\n",
            last,
        )
        self.assertTrue(last.endswith("## Request\n積み上げにして"))

    def test_chat_system_prompt_carries_the_table_and_the_current_chart(self) -> None:
        system = chat_system_prompt(self.book, _profile(), CURRENT)

        self.assertTrue(system.startswith(self.book.chat_system.rstrip()))
        self.assertIn("vega_lite_tool", system)
        self.assertIn("## Data profile\nrows: 3\n", system)
        self.assertTrue(
            system.endswith(f"## Current chart\n{chart_yaml(CURRENT).rstrip()}")
        )
        self.assertTrue(
            chat_system_prompt(self.book, _profile(), None).endswith(
                "## Current chart\nnone"
            )
        )

    def test_nothing_current_or_recent_says_none(self) -> None:
        last = build_messages(self.book, _profile(), None, [], "見せて")[-1].content
        assert isinstance(last, str)

        self.assertIn("## Current chart\nnone\n", last)
        self.assertIn("## Recent requests (oldest first)\nnone\n", last)

    def test_examples_use_their_own_sample_profile(self) -> None:
        messages = build_messages(self.book, _profile(), None, [], "x")

        for number, example in enumerate(self.book.examples):
            human = messages[1 + 2 * number].content
            assert isinstance(human, str)
            first_column = self.book.example_profiles[example.sample].columns[0].name
            self.assertIn(f"name: {first_column}", human)
            self.assertTrue(human.endswith(f"## Request\n{example.request}"))

    def test_example_replies_round_trip(self) -> None:
        messages = build_messages(self.book, _profile(), None, [], "x")

        for number, example in enumerate(self.book.examples):
            reply = messages[2 + 2 * number].content
            assert isinstance(reply, str)
            self.assertEqual(AssistantTurn.model_validate_json(reply), example.reply)
            # Keys follow the schema order, and a question keeps its explicit null.
            self.assertTrue(reply.startswith('{"chart": '))
        question = messages[2 + 2 * 2].content
        assert isinstance(question, str)
        self.assertTrue(question.startswith('{"chart": null, "message": '))

    def test_example_replies_always_carry_filters_after_mark(self) -> None:
        messages = build_messages(self.book, _profile(), None, [], "x")

        for number, example in enumerate(self.book.examples):
            if example.reply.chart is None:
                continue
            reply = messages[2 + 2 * number].content
            assert isinstance(reply, str)
            chart = json.loads(reply)["chart"]
            self.assertEqual(list(chart)[:2], ["mark", "filters"], reply)

    def test_example_replies_are_compact(self) -> None:
        reply = build_messages(self.book, _profile(), None, [], "x")[2].content
        assert isinstance(reply, str)

        self.assertIn('"timeUnit": "yearmonth"', reply)
        self.assertNotIn("null", reply)
        self.assertNotIn('"bin"', reply)
        self.assertIn("月", reply)  # not \u-escaped


class RepairMessageTest(unittest.TestCase):
    def test_lists_the_errors_and_asks_again(self) -> None:
        message = repair_message(["unknown column `売上額` in y", "theta needs arc"])

        self.assertEqual(
            message.content,
            "Your reply was invalid:\n"
            "- unknown column `売上額` in y\n"
            "- theta needs arc\n\n"
            "Reply again with the corrected JSON.",
        )


class ChartYamlTest(unittest.TestCase):
    def test_vega_lite_names_and_no_unset_fields(self) -> None:
        spec = ChartSpec(
            mark="bar",
            x=Encoding(field="月", type="temporal", timeUnit="year"),
            y=Encoding(field="売上", type="quantitative", aggregate="sum"),
            filters=[Filter(field="地域", op="oneOf", value=["福岡", "東京"])],
        )

        text = chart_yaml(spec)

        self.assertEqual(
            yaml.safe_load(text),
            {
                "mark": "bar",
                "x": {"field": "月", "type": "temporal", "timeUnit": "year"},
                "y": {"field": "売上", "type": "quantitative", "aggregate": "sum"},
                "filters": [
                    {"field": "地域", "op": "oneOf", "value": ["福岡", "東京"]}
                ],
            },
        )
        self.assertIn("月", text)
        self.assertNotIn("null", text)
        self.assertNotIn("bin", text)
        self.assertTrue(text.startswith("mark: bar\n"))


if __name__ == "__main__":
    unittest.main()
