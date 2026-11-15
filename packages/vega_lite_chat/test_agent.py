"""Tests for agent.py: the graph answers in prose or calls vega_lite_tool, with scripted models."""

import unittest
from collections.abc import Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from packages.vega_lite_chat.agent import (
    TOOL_NAME,
    ChatContext,
    ChatEvent,
    Finished,
    Repairing,
    Token,
    ToolCalled,
    chat_history,
    draw,
    run_chat,
    tool_result,
)
from packages.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
    Encoding,
)
from packages.vega_lite_chat.config import load_config
from packages.vega_lite_chat.csv_loader import load_csv
from packages.vega_lite_chat.fake_models import (
    GARBLED,
    ScriptedModels,
    calls_tool,
    chart_reply,
)
from packages.vega_lite_chat.llm import (
    OllamaUnavailable,
)
from packages.vega_lite_chat.profile import (
    profile_frame,
)
from packages.vega_lite_chat.prompts import load_prompts
from packages.vega_lite_chat.samples import sample_named
from packages.vega_lite_chat.session import (
    Answer,
    ChatSession,
    Turn,
)
from packages.vega_lite_chat.translator import Attempt

CONFIG = load_config()
PROMPTS = load_prompts(data=CONFIG.data)

LINE = ChartSpec(
    mark="line",
    x=Encoding(field="月", type="temporal", timeUnit="yearmonth"),
    y=Encoding(field="売上（万円）", type="quantitative", aggregate="sum"),
    color=Encoding(field="地域", type="nominal"),
)
BAR = ChartSpec(
    mark="bar",
    x=Encoding(field="月", type="temporal", timeUnit="yearmonth"),
    y=Encoding(field="売上（万円）", type="quantitative", aggregate="sum"),
    color=Encoding(field="地域", type="nominal"),
)
FIRST = chart_reply(LINE, "地域ごとの月別売上の推移を折れ線グラフにしました。")
REFINED = chart_reply(BAR, "棒グラフに変えました。")


def _session() -> ChatSession:
    df = load_csv(sample_named("sales_by_region.csv").read_bytes())
    profile = profile_frame(
        df,
        sample_rows=CONFIG.data.sample_rows,
        seed=CONFIG.data.sample_seed,
        max_listed_values=CONFIG.data.max_listed_values,
    )
    return ChatSession(source_name="sales_by_region.csv", df=df, profile=profile)


def _context(models: ScriptedModels, session: ChatSession | None = None) -> ChatContext:
    return ChatContext(
        session=_session() if session is None else session,
        prompts=PROMPTS,
        config=CONFIG,
        models=models.models(),
    )


def _drawn(reply_chart: ChartSpec, message: str) -> Turn:
    """A turn as vega_lite_tool would have made it, without calling any model."""
    return Turn(
        request="棒にして",
        auto=False,
        reply=AssistantTurn(chart=reply_chart, message=message),
        vega_lite={"mark": reply_chart.mark},
        attempts=(Attempt(raw="{}", errors=()),),
        tool_request="棒グラフにして",
    )


def _finished(events: Sequence[ChatEvent]) -> list[Turn | Answer]:
    return [event.turn for event in events if isinstance(event, Finished)]


class AnswerTest(unittest.TestCase):
    def test_a_question_streams_an_answer_without_the_tool(self) -> None:
        models = ScriptedModels(chat=[AIMessage(content="列は 4 つです。")])
        events = list(run_chat(_context(models), "どんな列がある？"))

        tokens = [event.text for event in events if isinstance(event, Token)]
        self.assertGreater(len(tokens), 1)  # streamed, not in one piece
        self.assertEqual("".join(tokens), "列は 4 つです。")
        self.assertEqual(
            _finished(events),
            [Answer(request="どんな列がある？", text="列は 4 つです。")],
        )
        self.assertEqual(models.chart.calls, [])
        self.assertEqual(models.chat.bound, [TOOL_NAME])

    def test_the_chat_model_sees_its_instructions_the_table_and_the_request(
        self,
    ) -> None:
        models = ScriptedModels(chat=[AIMessage(content="はい。")])
        list(run_chat(_context(models), "どんな列がある？"))

        sent = models.chat.calls[0]
        self.assertIsInstance(sent[0], SystemMessage)
        system = sent[0].text
        self.assertTrue(system.startswith(PROMPTS.chat_system.rstrip()))
        self.assertIn("## Data profile", system)
        self.assertIn("売上（万円）", system)
        self.assertIn("## Current chart\nnone", system)
        self.assertEqual(_shape(sent[-1:]), _shape([HumanMessage("どんな列がある？")]))

    def test_the_current_chart_reaches_the_chat_model(self) -> None:
        session = _session()
        session.add_turn(_drawn(LINE, "描きました。"))
        models = ScriptedModels(chat=[AIMessage(content="折れ線です。")])
        list(run_chat(_context(models, session), "今のグラフは？"))

        self.assertIn("mark: line", models.chat.calls[0][0].text)


class ToolTest(unittest.TestCase):
    def test_a_drawing_request_calls_the_tool(self) -> None:
        models = ScriptedModels(chart=[REFINED], chat=[calls_tool("棒グラフにして")])
        events = list(run_chat(_context(models), "これを棒グラフに"))

        self.assertNotIn(Token, [type(event) for event in events])
        self.assertEqual(events[0], ToolCalled("棒グラフにして"))
        [turn] = _finished(events)
        assert isinstance(turn, Turn)
        self.assertEqual(turn.request, "これを棒グラフに")  # what the user typed
        self.assertEqual(turn.tool_request, "棒グラフにして")
        self.assertFalse(turn.auto)
        self.assertEqual(turn.chart, BAR)
        self.assertIsNotNone(turn.vega_lite)
        self.assertTrue(turn.has_chart)
        # The translator answered the tool's request, and the chat model was called only once.
        self.assertIn("## Request\n棒グラフにして", models.chart.calls[0][-1].text)
        self.assertEqual(len(models.chat.calls), 1)

    def test_repairs_are_reported_while_the_tool_runs(self) -> None:
        models = ScriptedModels(
            chart=[GARBLED, FIRST], chat=[calls_tool("推移を見せて")]
        )
        events = list(run_chat(_context(models), "推移を見せて"))

        repairs = [event for event in events if isinstance(event, Repairing)]
        self.assertEqual(len(repairs), 1)
        self.assertEqual(repairs[0].number, 2)
        self.assertIn("JSON schema", repairs[0].errors[0])
        [turn] = _finished(events)
        assert isinstance(turn, Turn)
        self.assertEqual(len(turn.attempts), 2)
        self.assertTrue(turn.has_chart)

    def test_a_tool_call_without_a_request_becomes_a_failed_turn(self) -> None:
        bad_call = AIMessage(
            content="",
            tool_calls=[{"name": TOOL_NAME, "args": {}, "id": "call-1"}],
        )
        models = ScriptedModels(chat=[bad_call])
        events = list(run_chat(_context(models), "描いて"))

        [turn] = _finished(events)
        assert isinstance(turn, Turn)
        self.assertIsNone(turn.reply)
        self.assertIsNone(turn.tool_request)
        self.assertIn("request", turn.attempts[0].errors[0])
        self.assertEqual(models.chart.calls, [])


class OllamaDownTest(unittest.TestCase):
    def test_the_chat_model_unreachable_raises(self) -> None:
        models = ScriptedModels(chat=[ConnectionError("refused")])
        with self.assertRaises(OllamaUnavailable) as caught:
            list(run_chat(_context(models), "こんにちは"))
        self.assertIn("ollama serve", str(caught.exception))

    def test_the_translator_unreachable_raises(self) -> None:
        down = OllamaUnavailable("Ollama に接続できません。")
        models = ScriptedModels(chart=[down], chat=[calls_tool("棒グラフにして")])
        with self.assertRaises(OllamaUnavailable):
            list(run_chat(_context(models), "棒グラフにして"))


class HistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _session()
        first = Turn(
            request=PROMPTS.first_chart_request,
            auto=True,
            reply=AssistantTurn(chart=LINE, message="折れ線にしました。"),
            vega_lite={"mark": "line"},
            attempts=(),
        )
        self.session.add_turn(first)
        self.session.add_turn(Answer(request="どんな列がある？", text="4 つです。"))
        self.session.add_turn(_drawn(BAR, "棒グラフに変えました。"))

    def test_drawings_appear_as_tool_calls(self) -> None:
        messages = chat_history(self.session, 10)

        self.assertEqual(
            [type(message) for message in messages],
            [HumanMessage, AIMessage, ToolMessage]
            + [HumanMessage, AIMessage]
            + [HumanMessage, AIMessage, ToolMessage],
        )
        first_call = messages[1]
        assert isinstance(first_call, AIMessage)
        self.assertEqual(first_call.tool_calls[0]["name"], TOOL_NAME)
        self.assertEqual(
            first_call.tool_calls[0]["args"], {"request": PROMPTS.first_chart_request}
        )
        # A typed drawing shows the user's words, and the call shows what the tool was given.
        self.assertEqual(messages[5], HumanMessage(content="棒にして"))
        last_call = messages[6]
        assert isinstance(last_call, AIMessage)
        self.assertEqual(last_call.tool_calls[0]["args"], {"request": "棒グラフにして"})
        result = messages[7]
        assert isinstance(result, ToolMessage)
        self.assertEqual(result.tool_call_id, last_call.tool_calls[0]["id"])
        self.assertIn("mark: bar", result.text)
        self.assertIn("棒グラフに変えました。", result.text)

    def test_only_the_last_n_turns(self) -> None:
        self.assertEqual(
            [type(message) for message in chat_history(self.session, 1)],
            [HumanMessage, AIMessage, ToolMessage],
        )
        self.assertEqual(chat_history(self.session, 0), [])

    def test_history_goes_between_the_instructions_and_the_request(self) -> None:
        models = ScriptedModels(chat=[AIMessage(content="はい。")])
        list(run_chat(_context(models, self.session), "ありがとう"))

        sent = models.chat.calls[0]
        history = chat_history(self.session, CONFIG.chat.history_turns)
        # add_messages gives each message an id, so compare what the model reads.
        self.assertEqual(_shape(sent[1:-1]), _shape(history))
        self.assertEqual(_shape(sent[-1:]), _shape([HumanMessage("ありがとう")]))


class DrawTest(unittest.TestCase):
    def test_the_automatic_chart_goes_straight_to_the_translator(self) -> None:
        models = ScriptedModels(chart=[FIRST])
        turn = draw(
            _context(models),
            PROMPTS.first_chart_request,
            auto=True,
            on_attempt=lambda number, errors: None,
        )

        self.assertTrue(turn.auto)
        self.assertIsNone(turn.tool_request)
        self.assertEqual(turn.chart, LINE)
        self.assertEqual(models.chat.calls, [])
        last = models.chart.calls[0][-1].text
        self.assertIn(f"## Request\n{PROMPTS.first_chart_request}", last)


class ToolResultTest(unittest.TestCase):
    def _turn(self, reply: AssistantTurn | None, *, error: str | None = None) -> Turn:
        return Turn(
            request="x",
            auto=False,
            reply=reply,
            vega_lite=None if reply is None else {"mark": "bar"},
            attempts=(Attempt(raw="{", errors=("bad",)),) * 3,
            error=error,
        )

    def test_a_drawing_shows_the_chart_and_the_message(self) -> None:
        text = tool_result(self._turn(AssistantTurn(chart=BAR, message="棒です。")))
        self.assertTrue(text.startswith("Drew this chart:\nmark: bar"))
        self.assertTrue(text.endswith("Told the user: 棒です。"))

    def test_a_question_back(self) -> None:
        text = tool_result(self._turn(AssistantTurn(chart=None, message="どの列？")))
        self.assertEqual(text, "No chart. Told the user: どの列？")

    def test_a_failed_translation(self) -> None:
        self.assertIn("after 3 attempts", tool_result(self._turn(None)))

    def test_a_compiler_bug(self) -> None:
        turn = self._turn(AssistantTurn(chart=BAR, message="棒です。"), error="schema")
        self.assertIn("failed to compile", tool_result(turn))


def _shape(messages: Sequence[BaseMessage]) -> list[tuple[str, str, object]]:
    return [
        (message.type, message.text, getattr(message, "tool_calls", None))
        for message in messages
    ]


if __name__ == "__main__":
    unittest.main()
