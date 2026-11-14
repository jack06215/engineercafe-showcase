"""The two pages: a start page that loads a CSV, and the chat that answers questions and draws.

main.py only calls `render_app()`; everything Streamlit lives here so the lint macro sees it.
A test can put a model factory in `st.session_state[MODEL_FACTORY_KEY]`; the app then uses it
instead of Ollama and skips the warm-up.
"""

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import streamlit
import yaml
from streamlit.elements.lib.mutable_status_container import StatusContainer

from packages.vibe_coding_club.vega_lite_chat.agent import (
    TOOL_NAME,
    ChatContext,
    Finished,
    Repairing,
    Token,
    ToolCalled,
    draw,
    run_chat,
)
from packages.vibe_coding_club.vega_lite_chat.compiler import (
    with_inline_data,
)
from packages.vibe_coding_club.vega_lite_chat.config import (
    AppConfig,
    load_config,
)
from packages.vibe_coding_club.vega_lite_chat.csv_loader import (
    InputError,
    load_csv,
)
from packages.vibe_coding_club.vega_lite_chat.llm import (
    Models,
    OllamaUnavailable,
    ollama_models,
    warm_up,
)
from packages.vibe_coding_club.vega_lite_chat.profile import (
    profile_frame,
)
from packages.vibe_coding_club.vega_lite_chat.prompts import (
    PromptBook,
    chart_yaml,
    load_prompts,
)
from packages.vibe_coding_club.vega_lite_chat.samples import SAMPLES
from packages.vibe_coding_club.vega_lite_chat.session import (
    Answer,
    ChatSession,
    Turn,
)
from packages.vibe_coding_club.vega_lite_chat.translator import Attempt

TITLE = "CSV グラフチャット"

# st.session_state keys.
SESSION_KEY = "session"  # the ChatSession, absent on the start page
PENDING_KEY = "pending"  # a request Ollama couldn't take, waiting for 再試行
THINKING_KEY = "thinking"  # the 考える toggle
MODEL_FACTORY_KEY = "model_factory"  # Callable[[bool], Models], set by tests

# Widget keys tests click by.
UPLOAD_KEY = "upload"
NEW_FILE_KEY = "new_file"
RETRY_KEY = "retry"


def sample_key(file_name: str) -> str:
    """Return the widget key of the sample button for *file_name*."""
    return f"sample:{file_name}"


def continue_key(index: int) -> str:
    """Return the widget key of the continue button for turn *index*."""
    return f"continue:{index}"


ModelFactory = Callable[[bool], Models]


@dataclass(frozen=True)
class _Resources:
    config: AppConfig
    prompts: PromptBook
    warm_up_error: str | None


@dataclass(frozen=True)
class _Pending:
    request: str
    auto: bool
    error: str


@streamlit.cache_resource(show_spinner="モデルを準備しています…")
def _load_resources(warm: bool) -> _Resources:
    """Once per process: settings, the prompt file (its examples are checked), and the model loaded."""
    config = load_config()
    prompts = load_prompts(data=config.data)
    error = None
    if warm:
        try:
            warm_up(config.ollama)
        except OllamaUnavailable as exc:
            error = str(exc)
    return _Resources(config=config, prompts=prompts, warm_up_error=error)


def render_app() -> None:
    """Render the Streamlit chat app."""
    resources = _load_resources(warm=MODEL_FACTORY_KEY not in streamlit.session_state)
    streamlit.session_state.setdefault(
        THINKING_KEY, resources.config.ollama.thinking_default
    )
    session: ChatSession | None = streamlit.session_state.get(SESSION_KEY)
    _render_sidebar(resources, session)
    if session is None:
        _render_start(resources)
    else:
        _render_chat(resources, session)


def _render_sidebar(resources: _Resources, session: ChatSession | None) -> None:
    with streamlit.sidebar:
        if session is not None:
            streamlit.subheader(session.source_name)
            streamlit.caption(
                f"{session.profile.rows:,} 行 × {len(session.profile.columns)} 列"
            )
            if streamlit.button("新しいファイル", key=NEW_FILE_KEY):
                streamlit.session_state.pop(SESSION_KEY, None)
                streamlit.session_state.pop(PENDING_KEY, None)
                streamlit.rerun()
        streamlit.toggle(
            "考える（遅くなる）",
            key=THINKING_KEY,
            help="オンにすると、モデルが考えてから答えます。1 回あたり数秒から十数秒かかります。次の依頼から効きます。",
        )
        streamlit.caption(f"モデル: {resources.config.ollama.model}")
        if resources.warm_up_error is not None:
            streamlit.warning(resources.warm_up_error)


def _render_start(resources: _Resources) -> None:
    streamlit.title(TITLE)
    streamlit.markdown(
        "CSV を読み込むと、AI が最初のグラフを描きます。"
        "そのあとはチャットで表について質問したり、"
        "「積み上げにして」「2025年だけ」のようにグラフを直したりできます。"
    )
    uploaded = streamlit.file_uploader(
        "CSV ファイル（UTF-8、1 行目が見出し）", type=["csv"], key=UPLOAD_KEY
    )
    if uploaded is not None:
        _start(resources, uploaded.name, uploaded.getvalue(), credit=None)
    streamlit.markdown("**見本で試す**")
    for column, sample in zip(streamlit.columns(len(SAMPLES)), SAMPLES, strict=True):
        with column:
            if streamlit.button(
                sample.label, key=sample_key(sample.file_name), width="stretch"
            ):
                _start(
                    resources,
                    sample.file_name,
                    sample.read_bytes(),
                    credit=sample.credit,
                )


def _start(
    resources: _Resources, source_name: str, data: bytes, *, credit: str | None
) -> None:
    """Load the table, open a session on it, and ask for the first chart."""
    try:
        df = load_csv(data)
    except InputError as error:
        streamlit.error(str(error))
        return
    settings = resources.config.data
    profile = profile_frame(
        df,
        sample_rows=settings.sample_rows,
        seed=settings.sample_seed,
        max_listed_values=settings.max_listed_values,
    )
    session = ChatSession(
        source_name=source_name, df=df, profile=profile, credit=credit
    )
    streamlit.session_state[SESSION_KEY] = session
    streamlit.session_state.pop(PENDING_KEY, None)
    with streamlit.chat_message("assistant"):
        _run_draw(resources, session, resources.prompts.first_chart_request)
    streamlit.rerun()


def _render_chat(resources: _Resources, session: ChatSession) -> None:
    streamlit.title(TITLE)
    if session.credit is not None:
        streamlit.caption(session.credit)
    if session.profile.rows > resources.config.data.row_warning:
        streamlit.warning(
            f"{session.profile.rows:,} 行あります。"
            "ブラウザがすべての行を描くので、表示が遅くなることがあります。"
        )
    for index, turn in enumerate(session.turns):
        _render_turn(index, turn, session)

    pending: _Pending | None = streamlit.session_state.get(PENDING_KEY)
    if pending is not None:
        _render_request(pending.request, auto=pending.auto)
        with streamlit.chat_message("assistant"):
            streamlit.error(pending.error)
            if streamlit.button("再試行", key=RETRY_KEY):
                streamlit.session_state.pop(PENDING_KEY, None)
                if pending.auto:
                    _run_draw(resources, session, pending.request)
                else:
                    _run_chat(resources, session, pending.request)
                streamlit.rerun()

    request = streamlit.chat_input("質問、またはグラフへの注文を入力")
    if request:
        streamlit.session_state.pop(PENDING_KEY, None)
        _render_request(request, auto=False)
        with streamlit.chat_message("assistant"):
            _run_chat(resources, session, request)
        streamlit.rerun()


def _render_request(request: str, *, auto: bool) -> None:
    with streamlit.chat_message("user"):
        streamlit.markdown("（自動）最初のグラフ" if auto else request)


def _render_turn(index: int, turn: Turn | Answer, session: ChatSession) -> None:
    if isinstance(turn, Answer):
        _render_request(turn.request, auto=False)
        with streamlit.chat_message("assistant"):
            streamlit.markdown(
                turn.text or "（返答が空でした。もう一度聞いてみてください。）"
            )
        return
    _render_request(turn.request, auto=turn.auto)
    with streamlit.chat_message("assistant"):
        if turn.tool_request is not None:
            streamlit.caption(
                f"{TOOL_NAME} を呼びました（request: {turn.tool_request}）"
            )
        if turn.reply is None:
            streamlit.error(
                "グラフを作れませんでした。言い方を変えて、もう一度頼んでみてください。"
            )
            _render_attempts(turn.attempts)
            return
        streamlit.markdown(turn.reply.message)
        if turn.error is not None:
            streamlit.error(turn.error)
        if turn.has_chart and turn.vega_lite is not None:
            streamlit.vega_lite_chart(
                session.df, turn.vega_lite, width="stretch", key=f"chart:{index}"
            )
            if session.current == index:
                streamlit.caption("現在のグラフ")
            elif streamlit.button("ここから続ける", key=continue_key(index)):
                session.continue_from(index)
                streamlit.rerun()
        if turn.chart is not None:
            _render_spec(index, turn, session)


def _render_spec(index: int, turn: Turn, session: ChatSession) -> None:
    if turn.chart is None:
        return
    with streamlit.expander("仕様"):
        chart_tab, vega_lite_tab = streamlit.tabs(["ChartSpec", "Vega-Lite"])
        with chart_tab:
            spec_text = chart_yaml(turn.chart)
            streamlit.code(spec_text, language="yaml")
            streamlit.download_button(
                "ChartSpec をダウンロード（.yaml）",
                spec_text,
                file_name=f"chart_spec_{index + 1}.yaml",
                mime="application/yaml",
                key=f"download_spec:{index}",
                on_click="ignore",
            )
        with vega_lite_tab:
            if turn.vega_lite is None:
                streamlit.caption("変換できませんでした。")
                return
            streamlit.code(
                yaml.safe_dump(turn.vega_lite, allow_unicode=True, sort_keys=False),
                language="yaml",
            )
            streamlit.download_button(
                "Vega-Lite をダウンロード（.json、データ入り）",
                json.dumps(
                    with_inline_data(turn.vega_lite, session.df),
                    ensure_ascii=False,
                    indent=2,
                ),
                file_name=f"vega_lite_{index + 1}.json",
                mime="application/json",
                key=f"download_vega_lite:{index}",
                on_click="ignore",
            )


def _render_attempts(attempts: Sequence[Attempt]) -> None:
    with streamlit.expander("各回の返答とエラー"):
        for number, attempt in enumerate(attempts, start=1):
            streamlit.markdown(f"**{number} 回目**")
            streamlit.code(attempt.raw or "（空の返答）", language="json")
            for error in attempt.errors:
                streamlit.markdown(f"- {error}")


def _context(resources: _Resources, session: ChatSession) -> ChatContext:
    reasoning = bool(streamlit.session_state.get(THINKING_KEY))
    factory: ModelFactory | None = streamlit.session_state.get(MODEL_FACTORY_KEY)
    if factory is not None:
        models = factory(reasoning)
    else:
        models = ollama_models(resources.config.ollama, reasoning=reasoning)
    return ChatContext(
        session=session,
        prompts=resources.prompts,
        config=resources.config,
        models=models,
    )


def _run_draw(resources: _Resources, session: ChatSession, request: str) -> None:
    """Draw the automatic first chart: straight to the translator, without the chat model.

    Ollama being unreachable is not a turn: the request is kept for 再試行 instead.
    """
    max_calls = resources.config.translator.max_calls
    with streamlit.status("グラフを作っています…") as status:

        def on_attempt(number: int, errors: Sequence[str]) -> None:
            if number > 1:
                status.update(label=f"修正中（{number}/{max_calls}）: {_short(errors)}")

        try:
            turn = draw(
                _context(resources, session),
                request,
                auto=True,
                on_attempt=on_attempt,
            )
        except OllamaUnavailable as error:
            status.update(label="Ollama に接続できませんでした", state="error")
            streamlit.session_state[PENDING_KEY] = _Pending(request, True, str(error))
            return
        _close_status(status, [turn])
    session.add_turn(turn)


def _run_chat(resources: _Resources, session: ChatSession, request: str) -> None:
    """Run the chat graph on a typed request.

    Stream the prose answer as it comes, or show vega_lite_tool's progress when the chat model calls
    it.

    Ollama being unreachable is not a turn: the request is kept for 再試行 instead.
    """
    max_calls = resources.config.translator.max_calls
    answer = streamlit.empty()
    text = ""
    status: StatusContainer | None = None
    finished: list[Turn | Answer] = []
    try:
        for event in run_chat(_context(resources, session), request):
            match event:
                case Token():
                    text += event.text
                    answer.markdown(text + "▌")
                case ToolCalled():
                    answer.empty()  # anything said before the call is dropped
                    status = streamlit.status(
                        f"{TOOL_NAME} でグラフを作っています…（request: {event.request}）"
                    )
                case Repairing() if status is not None:
                    status.update(
                        label=f"修正中（{event.number}/{max_calls}）: {_short(event.errors)}"
                    )
                case Finished():
                    finished.append(event.turn)
    except OllamaUnavailable as error:
        if status is not None:
            status.update(label="Ollama に接続できませんでした", state="error")
        streamlit.session_state[PENDING_KEY] = _Pending(request, False, str(error))
        return
    if status is not None:
        _close_status(status, finished)
    for turn in finished:
        session.add_turn(turn)


def _close_status(status: StatusContainer, turns: Iterable[Turn | Answer]) -> None:
    failed = any(
        isinstance(turn, Turn) and (turn.reply is None or turn.error is not None)
        for turn in turns
    )
    if failed:
        status.update(label="グラフを作れませんでした", state="error")
    else:
        status.update(label="できました", state="complete")


def _short(errors: Sequence[str], limit: int = 80) -> str:
    text = "; ".join(errors) if errors else "返答を直しています"
    return text if len(text) <= limit else text[: limit - 1] + "…"
