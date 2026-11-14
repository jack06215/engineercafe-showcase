"""Scripted stand-ins for both models, shared by test_agent and test_ui. No Ollama involved."""

import json
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call, tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from packages.vibe_coding_club.vega_lite_chat.agent import TOOL_NAME
from packages.vibe_coding_club.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
)
from packages.vibe_coding_club.vega_lite_chat.llm import (
    Models,
    RawReply,
)


def chart_reply(chart: ChartSpec | None, message: str) -> RawReply:
    """A translator reply that parsed."""
    turn = AssistantTurn(chart=chart, message=message)
    return RawReply(text=turn.model_dump_json(), turn=turn, parse_error=None)


GARBLED = RawReply(text="{", turn=None, parse_error="Invalid JSON: EOF")


def calls_tool(request: str) -> AIMessage:
    """A chat model reply that calls vega_lite_tool with `request`."""
    return AIMessage(
        content="",
        tool_calls=[tool_call(name=TOOL_NAME, args={"request": request}, id="call-1")],
    )


class ScriptedModel:
    """The translator's model: answers with the scripted replies in order; an exception in the
    script is raised instead."""

    def __init__(self, *script: RawReply | Exception) -> None:
        self.script = list(script)
        self.calls: list[list[BaseMessage]] = []

    def __call__(self, messages: Sequence[BaseMessage]) -> RawReply:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("the chart model was called more often than scripted")
        reply = self.script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ScriptedChat(BaseChatModel):
    """The chat model: streams the scripted replies in order, a character at a time, then any tool
    calls; an exception in the script is raised instead."""

    script: list[Any]  # AIMessage | Exception
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    bound: list[str] = Field(default_factory=list)  # the names of the tools bound

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self.bound.extend(str(getattr(tool, "name", tool)) for tool in tools)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        reply = self._next(messages)
        for char in reply.text:
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=char))
            if run_manager is not None:
                run_manager.on_llm_new_token(char, chunk=chunk)
            yield chunk
        chunks = [
            tool_call_chunk(
                name=call["name"],
                args=json.dumps(call["args"], ensure_ascii=False),
                id=call["id"],
                index=index,
            )
            for index, call in enumerate(reply.tool_calls)
        ]
        if chunks:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_call_chunks=chunks)
            )

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("the chat model was called more often than scripted")
        reply = self.script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if not isinstance(reply, AIMessage):
            raise TypeError(f"scripted a {type(reply).__name__}, not an AIMessage")
        return reply


class ScriptedModels:
    """Both fakes, handed out as `Models`; `factory` stands in for `llm.ollama_models`."""

    def __init__(
        self,
        chart: Sequence[RawReply | Exception] = (),
        chat: Sequence[AIMessage | Exception] = (),
    ) -> None:
        self.chart = ScriptedModel(*chart)
        self.chat = ScriptedChat(script=list(chat))
        self.reasoning: list[bool] = []

    def models(self) -> Models:
        return Models(chat=self.chat, chart=self.chart)

    def factory(self, reasoning: bool) -> Models:
        self.reasoning.append(reasoning)
        return self.models()
