"""The chat: a LangGraph graph that answers in prose, or calls vega_lite_tool when asked to draw.

    START → chat ──(tool call)──→ tools (vega_lite_tool) → END
              └──(no tool call)──────────────────────────→ END

The chat model streams a prose answer token by token. Asked for a chart, it calls vega_lite_tool
instead, which runs the translator (repair loop, checks, compiler) and returns the new `Turn` as the
tool message's artifact. The graph ends there: the translator already wrote the reply, so the chat
model isn't called a second time. No Streamlit here; `run_chat` yields events that ui.py draws.
"""

import json
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import tool_call
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, ToolRuntime, tools_condition
from langgraph.runtime import Runtime

from packages.common.logging_util import get_logger
from packages.vega_lite_chat.compiler import (
    compile_chart,
    vega_lite_errors,
)
from packages.vega_lite_chat.config import AppConfig
from packages.vega_lite_chat.llm import (
    Models,
    reaching_ollama,
)
from packages.vega_lite_chat.prompts import (
    PromptBook,
    build_messages,
    chart_yaml,
    chat_system_prompt,
)
from packages.vega_lite_chat.session import (
    Answer,
    ChatSession,
    Turn,
)
from packages.vega_lite_chat.translator import (
    Attempt,
    translate,
)

LOGGER = get_logger(__name__)

TOOL_NAME = "vega_lite_tool"
CHAT_NODE = "chat"
TOOLS_NODE = "tools"  # the name tools_condition routes to


@dataclass(frozen=True)
class ChatContext:
    """What a turn needs besides the conversation. LangGraph hands it to the chat node and the tool."""

    session: ChatSession
    prompts: PromptBook
    config: AppConfig
    models: Models


class ChatState(TypedDict):
    """The LangGraph state: the conversation so far."""

    messages: Annotated[list[AnyMessage], add_messages]


@dataclass(frozen=True)
class Token:
    """Stream event: the next piece of the chat model's answer."""

    text: str  # the next piece of the chat model's prose answer


@dataclass(frozen=True)
class ToolCalled:
    """Stream event: the chat model asked for a chart."""

    request: str  # what the chat model passed to vega_lite_tool


@dataclass(frozen=True)
class Repairing:
    """Stream event: the translator retries after a failed attempt."""

    number: int  # the attempt about to start, 2 or more
    errors: tuple[str, ...]  # what was wrong with the previous one


@dataclass(frozen=True)
class Finished:
    """Stream event: the turn is complete."""

    turn: Turn | Answer  # ready for session.add_turn


ChatEvent = Token | ToolCalled | Repairing | Finished


def draw(
    context: ChatContext,
    request: str,
    *,
    on_attempt: Callable[[int, Sequence[str]], None],
    auto: bool = False,
    tool_request: str | None = None,
) -> Turn:
    """Translate a request against the current chart and compile the result: vega_lite_tool's work.

    `request` is what the user typed, or first_chart_request with `auto`. When the chat model passed
    the tool a `tool_request`, the translator answers that instead. `OllamaUnavailable` passes
    through, and no turn is made.
    """
    session = context.session
    config = context.config
    messages = build_messages(
        context.prompts,
        session.profile,
        session.current_chart(),
        session.recent_requests(config.translator.recent_requests),
        request if tool_request is None else tool_request,
    )
    translation = translate(
        context.models.chart,
        messages,
        session.profile,
        max_calls=config.translator.max_calls,
        on_attempt=on_attempt,
    )
    reply = translation.turn
    vega_lite = None
    error = None
    if reply is not None and reply.chart is not None:
        vega_lite = compile_chart(
            reply.chart, session.profile, height=config.chart.height
        )
        problems = vega_lite_errors(vega_lite)
        if problems:
            # Our compiler's bug, not the model's: show it and log the spec, never repair it.
            LOGGER.error(
                "compiled spec fails the Vega-Lite schema: %s; spec=%s",
                problems,
                json.dumps(vega_lite, ensure_ascii=False),
            )
            error = f"グラフの変換に失敗しました（アプリの不具合です）: {problems[0]}"
    return Turn(
        request=request,
        auto=auto,
        reply=reply,
        vega_lite=vega_lite,
        attempts=translation.attempts,
        error=error,
        tool_request=tool_request,
    )


def tool_result(turn: Turn) -> str:
    """What the chat model reads back from vega_lite_tool, in this turn and in later turns' history."""
    if turn.reply is None:
        return (
            f"No chart: no valid chart after {len(turn.attempts)} attempts. "
            "The user was asked to rephrase."
        )
    if turn.error is not None:
        return f"No chart: the app failed to compile it ({turn.error})."
    if turn.chart is None:
        return f"No chart. Told the user: {turn.reply.message}"
    return (
        f"Drew this chart:\n{chart_yaml(turn.chart).rstrip()}\n"
        f"Told the user: {turn.reply.message}"
    )


@tool(TOOL_NAME, response_format="content_and_artifact", parse_docstring=True)
def vega_lite_tool(
    request: str, runtime: ToolRuntime[ChatContext, ChatState]
) -> tuple[str, Turn]:
    """Draw a new chart of the uploaded table, or change the current chart.

    Call it whenever the user wants something drawn or the chart changed. It knows the table's
    columns and the current chart.

    Args:
        request: The user's request, copied word for word in the user's language.
        runtime: Injected by LangGraph. The model never sees or sets it.
    """

    def on_attempt(number: int, errors: Sequence[str]) -> None:
        if number > 1:
            runtime.stream_writer(Repairing(number, tuple(errors)))

    turn = draw(
        runtime.context,
        _typed_request(runtime.state["messages"], fallback=request),
        tool_request=request,
        on_attempt=on_attempt,
    )
    return tool_result(turn), turn


def chat_reply(context: ChatContext, messages: Sequence[BaseMessage]) -> AIMessage:
    """One call to the chat model: its instructions and the table, then `messages`."""
    session = context.session
    system = SystemMessage(
        content=chat_system_prompt(
            context.prompts, session.profile, session.current_chart()
        )
    )
    model = context.models.chat.bind_tools([vega_lite_tool])
    return model.invoke([system, *messages])


def _chat_node(state: ChatState, runtime: Runtime[ChatContext]) -> ChatState:
    return {"messages": [chat_reply(runtime.context, state["messages"])]}


def chat_history(session: ChatSession, n: int) -> list[AnyMessage]:
    """The last `n` turns as messages.

    A drawing appears as its vega_lite_tool call and result, the way the chat model made it, so the
    history keeps showing the model when to call the tool.
    """
    start = max(len(session.turns) - n, 0)
    messages: list[AnyMessage] = []
    for index, turn in enumerate(session.turns[start:], start=start):
        messages.append(HumanMessage(content=turn.request))
        if isinstance(turn, Answer):
            messages.append(AIMessage(content=turn.text))
            continue
        call_id = f"turn-{index}"
        call = tool_call(
            name=TOOL_NAME, args={"request": turn.translator_request}, id=call_id
        )
        messages.append(AIMessage(content="", tool_calls=[call]))
        messages.append(ToolMessage(content=tool_result(turn), tool_call_id=call_id))
    return messages


def build_graph() -> CompiledStateGraph[ChatState, ChatContext, ChatState, ChatState]:
    """Build the graph: the chat model, then the chart tool if it calls it."""
    graph = StateGraph(ChatState, context_schema=ChatContext)
    graph.add_node(CHAT_NODE, _chat_node)
    graph.add_node(TOOLS_NODE, ToolNode([vega_lite_tool]))
    graph.add_edge(START, CHAT_NODE)
    graph.add_conditional_edges(CHAT_NODE, tools_condition)  # tools, or END
    graph.add_edge(TOOLS_NODE, END)  # the translator's message is the reply
    return graph.compile()


GRAPH = build_graph()


def run_chat(context: ChatContext, request: str) -> Iterator[ChatEvent]:
    """Run the graph on `request`, after the last few turns.

    Yields a prose answer as it streams (`Token`s), then `Finished` with the `Answer`; or, when the
    chat model calls the tool, `ToolCalled`, any `Repairing`, then `Finished` with the `Turn`.
    Raises `OllamaUnavailable` when Ollama can't be reached; nothing is finished then.
    """
    state = ChatState(
        messages=[
            *chat_history(context.session, context.config.chat.history_turns),
            HumanMessage(content=request),
        ]
    )
    calls: dict[str, dict[str, Any]] = {}  # tool call id → its arguments
    with reaching_ollama(context.config.ollama):
        for part in GRAPH.stream(
            state,
            context=context,
            stream_mode=["messages", "custom", "updates"],
            version="v2",  # typed parts: {"type": mode, "data": ...}
        ):
            if part["type"] == "messages":
                chunk, metadata = part["data"]
                if (
                    metadata.get("langgraph_node") == CHAT_NODE
                    and isinstance(chunk, AIMessage)
                    and chunk.text
                ):
                    yield Token(chunk.text)
            elif part["type"] == "custom":
                if isinstance(part["data"], Repairing):
                    yield part["data"]
            elif part["type"] == "updates":  # the messages each node added
                for update in part["data"].values():
                    for message in (update or {}).get("messages", []):
                        yield from _node_message(message, request, calls)


def _node_message(
    message: AnyMessage, request: str, calls: dict[str, dict[str, Any]]
) -> Iterator[ChatEvent]:
    if isinstance(message, ToolMessage):
        yield Finished(_drawn(message, request, calls))
    elif isinstance(message, AIMessage) and message.tool_calls:
        for call in message.tool_calls:
            calls[call["id"] or ""] = call["args"]
            yield ToolCalled(str(call["args"].get("request", "")))
    elif isinstance(message, AIMessage):
        yield Finished(Answer(request=request, text=message.text))


def _drawn(
    message: ToolMessage, request: str, calls: dict[str, dict[str, Any]]
) -> Turn:
    if isinstance(message.artifact, Turn):
        return message.artifact
    # The tool never ran: ToolNode answered a call whose arguments didn't validate with the error.
    args = calls.get(message.tool_call_id, {})
    attempt = Attempt(raw=json.dumps(args, ensure_ascii=False), errors=(message.text,))
    tool_request = args.get("request")
    return Turn(
        request=request,
        auto=False,
        reply=None,
        vega_lite=None,
        attempts=(attempt,),
        tool_request=tool_request if isinstance(tool_request, str) else None,
    )


def _typed_request(messages: Sequence[AnyMessage], *, fallback: str) -> str:
    """The user's own words: the latest human message in the graph's state."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.text
    return fallback
