"""UI tests: drive the app headlessly with streamlit.testing's AppTest and scripted models."""

import unittest
from pathlib import Path

from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from packages.vibe_coding_club.vega_lite_chat.chart_spec import (
    ChartSpec,
    Encoding,
)
from packages.vibe_coding_club.vega_lite_chat.fake_models import (
    GARBLED,
    ScriptedModels,
    calls_tool,
    chart_reply,
)
from packages.vibe_coding_club.vega_lite_chat.llm import (
    OllamaUnavailable,
)
from packages.vibe_coding_club.vega_lite_chat.session import (
    Answer,
    ChatSession,
)
from packages.vibe_coding_club.vega_lite_chat.ui import (
    MODEL_FACTORY_KEY,
    NEW_FILE_KEY,
    RETRY_KEY,
    SESSION_KEY,
    UPLOAD_KEY,
    continue_key,
    sample_key,
)

APP = Path(__file__).with_name("main.py")
TIMEOUT = 60  # the first run imports pandas, langchain and the Vega-Lite schema
SALES = "sales_by_region.csv"

LINE = ChartSpec(
    mark="line",
    x=Encoding(field="月", type="temporal", timeUnit="yearmonth"),
    y=Encoding(field="売上（万円）", type="quantitative", aggregate="sum"),
    color=Encoding(field="地域", type="nominal"),
)
STACKED = ChartSpec(
    mark="bar",
    x=Encoding(field="月", type="temporal", timeUnit="yearmonth"),
    y=Encoding(
        field="売上（万円）", type="quantitative", aggregate="sum", stack="zero"
    ),
    color=Encoding(field="地域", type="nominal"),
)

FIRST = chart_reply(LINE, "地域ごとの月別売上の推移を折れ線グラフにしました。")
REFINED = chart_reply(STACKED, "地域で積み上げた棒グラフにしました。")


def _start(models: ScriptedModels) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    app.session_state[MODEL_FACTORY_KEY] = models.factory
    return app.run()


def _session(app: AppTest) -> ChatSession:
    session = app.session_state[SESSION_KEY]
    assert isinstance(session, ChatSession)
    return session


class UiTest(unittest.TestCase):
    def assert_clean(self, app: AppTest) -> None:
        self.assertFalse(app.exception, [e.value for e in app.exception])

    def assert_shows(self, app: AppTest, text: str) -> None:
        shown = [m.value for m in app.markdown]
        self.assertTrue(any(text in value for value in shown), shown)

    def test_start_page(self) -> None:
        app = _start(ScriptedModels())
        self.assert_clean(app)
        self.assertNotIn(SESSION_KEY, app.session_state)
        self.assertEqual(len(app.file_uploader), 1)
        self.assertEqual(len(app.chat_input), 0)

    def test_sample_then_request_refines_the_chart(self) -> None:
        models = ScriptedModels(
            chart=[FIRST, REFINED], chat=[calls_tool("地域で積み上げにして")]
        )
        app = _start(models)
        app.button(key=sample_key(SALES)).click().run()
        self.assert_clean(app)
        session = _session(app)
        self.assertEqual(session.source_name, SALES)
        self.assertEqual(len(session.turns), 1)
        self.assertTrue(session.turns[0].auto)
        self.assertEqual(session.current, 0)
        self.assertIsNotNone(session.turns[0].vega_lite)
        self.assert_shows(app, "（自動）最初のグラフ")
        self.assert_shows(app, "地域ごとの月別売上の推移を折れ線グラフにしました。")
        self.assertEqual(len(app.chat_input), 1)

        app.chat_input[0].set_value("地域で積み上げにして").run()
        self.assert_clean(app)
        session = _session(app)
        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[1].request, "地域で積み上げにして")
        self.assertEqual(session.current, 1)
        self.assertEqual(session.current_chart(), STACKED)
        self.assertEqual(session.turns[1].tool_request, "地域で積み上げにして")
        self.assert_shows(app, "地域で積み上げた棒グラフにしました。")
        self.assertTrue(
            any("vega_lite_tool を呼びました" in c.value for c in app.caption),
            [c.value for c in app.caption],
        )
        # The refinement started from the first chart, and the request reached the translator.
        last_message = str(models.chart.calls[-1][-1].content)
        self.assertIn("地域で積み上げにして", last_message)
        self.assertIn("line", last_message)
        self.assertEqual(models.reasoning, [False, False])

    def test_a_question_gets_an_answer_and_no_chart(self) -> None:
        answer = "この表には 月・地域・売上（万円）・件数 の 4 つの列があります。"
        models = ScriptedModels(chart=[FIRST], chat=[AIMessage(content=answer)])
        app = _start(models)
        app.button(key=sample_key(SALES)).click().run()
        app.chat_input[0].set_value("どんな列がある？").run()
        self.assert_clean(app)
        session = _session(app)
        self.assertEqual(
            session.turns[1], Answer(request="どんな列がある？", text=answer)
        )
        self.assertEqual(session.current, 0)  # the chart stays
        self.assertEqual(len(models.chart.calls), 1)  # only the first chart
        self.assert_shows(app, answer)
        self.assert_shows(app, "どんな列がある？")

    def test_continue_from_an_earlier_chart(self) -> None:
        models = ScriptedModels(
            chart=[FIRST, REFINED], chat=[calls_tool("地域で積み上げにして")]
        )
        app = _start(models)
        app.button(key=sample_key(SALES)).click().run()
        app.chat_input[0].set_value("地域で積み上げにして").run()
        self.assertEqual(_session(app).current, 1)
        app.button(key=continue_key(0)).click().run()
        self.assert_clean(app)
        self.assertEqual(_session(app).current, 0)
        self.assertEqual(_session(app).current_chart(), LINE)

    def test_new_file_returns_to_the_start_page(self) -> None:
        app = _start(ScriptedModels(chart=[FIRST]))
        app.button(key=sample_key(SALES)).click().run()
        app.button(key=NEW_FILE_KEY).click().run()
        self.assert_clean(app)
        self.assertNotIn(SESSION_KEY, app.session_state)
        self.assertEqual(len(app.file_uploader), 1)

    def test_a_non_utf8_upload_shows_an_error(self) -> None:
        app = _start(ScriptedModels())
        content = "月,売上\n2025-01,100\n".encode("cp932")
        app.file_uploader(key=UPLOAD_KEY).upload("sjis.csv", content, "text/csv").run()
        self.assert_clean(app)
        self.assertNotIn(SESSION_KEY, app.session_state)
        self.assertTrue(
            any("UTF-8" in e.value for e in app.error), [e.value for e in app.error]
        )

    def test_a_large_upload_warns(self) -> None:
        rows = "".join(f"2025-01-{day % 28 + 1:02d},{day}\n" for day in range(1_001))
        app = _start(
            ScriptedModels(chart=[chart_reply(None, "どんなグラフにしますか？")])
        )
        content = ("日付,売上\n" + rows).encode("utf-8")
        app.file_uploader(key=UPLOAD_KEY).upload("big.csv", content, "text/csv").run()
        self.assert_clean(app)
        self.assertEqual(_session(app).profile.rows, 1_001)
        self.assertTrue(
            any("1,001 行" in w.value for w in app.warning),
            [w.value for w in app.warning],
        )

    def test_ollama_down_then_retry(self) -> None:
        down = OllamaUnavailable("Ollama に接続できません。")
        app = _start(ScriptedModels(chart=[down, FIRST]))
        app.button(key=sample_key(SALES)).click().run()
        self.assert_clean(app)
        self.assertEqual(_session(app).turns, [])
        self.assertTrue(any("Ollama に接続できません" in e.value for e in app.error))
        app.button(key=RETRY_KEY).click().run()
        self.assert_clean(app)
        session = _session(app)
        self.assertEqual(len(session.turns), 1)
        self.assertTrue(session.turns[0].auto)
        self.assertEqual(session.current, 0)
        self.assertNotIn(RETRY_KEY, [button.key for button in app.button])

    def test_ollama_down_while_chatting_then_retry(self) -> None:
        models = ScriptedModels(
            chart=[FIRST],
            chat=[ConnectionError("refused"), AIMessage(content="こんにちは。")],
        )
        app = _start(models)
        app.button(key=sample_key(SALES)).click().run()
        app.chat_input[0].set_value("こんにちは").run()
        self.assert_clean(app)
        self.assertEqual(len(_session(app).turns), 1)
        self.assertTrue(any("ollama serve" in e.value for e in app.error))
        app.button(key=RETRY_KEY).click().run()
        self.assert_clean(app)
        session = _session(app)
        self.assertEqual(
            session.turns[1], Answer(request="こんにちは", text="こんにちは。")
        )
        self.assertNotIn(RETRY_KEY, [button.key for button in app.button])

    def test_three_bad_replies_become_a_failed_turn(self) -> None:
        app = _start(ScriptedModels(chart=[GARBLED, GARBLED, GARBLED]))
        app.button(key=sample_key(SALES)).click().run()
        self.assert_clean(app)
        session = _session(app)
        self.assertEqual(len(session.turns), 1)
        self.assertIsNone(session.turns[0].reply)
        self.assertEqual(len(session.turns[0].attempts), 3)
        self.assertIsNone(session.current)
        self.assertTrue(any("グラフを作れませんでした" in e.value for e in app.error))


if __name__ == "__main__":
    unittest.main()
