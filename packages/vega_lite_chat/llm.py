"""The one place that talks to Ollama, plus the seams (`StructuredModel`, `Models`) the rest calls through."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx
import ollama
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama
from pydantic import ValidationError

from packages.langchain_util.api_client import get_langchain_client
from packages.vega_lite_chat.chart_spec import (
    AssistantTurn,
)
from packages.vega_lite_chat.config import OllamaConfig

# The ollama client turns httpx.ConnectError into the builtin ConnectionError,
# but lets timeouts through as httpx exceptions; both are caught.
_UNREACHABLE = (
    ConnectionError,
    httpx.ConnectError,
    httpx.TimeoutException,
    ollama.ResponseError,
)


class OllamaUnavailable(Exception):
    """Ollama couldn't be reached, timed out, or refused the request. The message is Japanese, for the UI."""


@dataclass(frozen=True)
class RawReply:
    """The model's raw reply and, if it parsed, the turn."""

    text: str  # the model's reply as sent, for the repair request and for showing failures
    turn: AssistantTurn | None  # set when the reply parsed
    parse_error: str | None


# Runtime-checkable because vega_lite_tool's argument schema reaches it through ChatContext, and
# pydantic checks a class it doesn't know with isinstance.
@runtime_checkable
class StructuredModel(Protocol):
    """A model that turns messages into a raw structured reply."""

    def __call__(self, messages: Sequence[BaseMessage]) -> RawReply:
        """Send *messages* and return the raw reply."""


@dataclass(frozen=True)
class Models:
    """The two models a chat turn uses. Tests hand the app fakes of both."""

    chat: BaseChatModel  # answers in prose, and decides when to call vega_lite_tool
    chart: StructuredModel  # the translator inside vega_lite_tool


def ollama_models(config: OllamaConfig, *, reasoning: bool) -> Models:
    """Both models on the same Ollama model; the 考える toggle applies to both."""
    return Models(
        chat=_client(config, reasoning=reasoning),
        chart=ollama_model(config, reasoning=reasoning),
    )


def ollama_model(config: OllamaConfig, *, reasoning: bool) -> StructuredModel:
    """A `StructuredModel` backed by Ollama, constrained to the `AssistantTurn` JSON schema.

    `reasoning` is always a bool: left at None, qwen writes its thinking inside `<think>` tags in the
    reply body, and the JSON stops parsing.
    """
    structured = _client(config, reasoning=reasoning).with_structured_output(
        AssistantTurn, include_raw=True
    )

    def call(messages: Sequence[BaseMessage]) -> RawReply:
        with reaching_ollama(config):
            result = structured.invoke(list(messages))
        if not isinstance(result, dict):
            raise TypeError(
                f"expected the include_raw dict, got {type(result).__name__}"
            )
        raw = result["raw"]
        text = raw.text if isinstance(raw, BaseMessage) else str(raw)
        parsed = result.get("parsed")
        if isinstance(parsed, AssistantTurn):
            return RawReply(text=text, turn=parsed, parse_error=None)
        return RawReply(
            text=text,
            turn=None,
            parse_error=_parse_error(text, result.get("parsing_error")),
        )

    return call


def warm_up(config: OllamaConfig) -> None:
    """Load the model into memory without generating anything: Ollama only loads on an empty prompt."""
    client = ollama.Client(host=config.base_url, timeout=config.timeout_seconds)
    with reaching_ollama(config):
        client.generate(model=config.model, prompt="", keep_alive=config.keep_alive)


@contextmanager
def reaching_ollama(config: OllamaConfig) -> Iterator[None]:
    """Turn every way a call to Ollama can fail to arrive into `OllamaUnavailable`."""
    try:
        yield
    except _UNREACHABLE as error:
        raise _unavailable(error, config) from error


def _client(config: OllamaConfig, *, reasoning: bool) -> ChatOllama:
    return get_langchain_client(
        "ollama",
        model=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
        reasoning=reasoning,
        keep_alive=config.keep_alive,
        client_kwargs={"timeout": config.timeout_seconds},
    )


def _parse_error(text: str, error: object) -> str:
    # LangChain's OutputParserException repeats the whole completion; pydantic's own errors are shorter
    # and point at the field, which is what the repair request needs.
    try:
        AssistantTurn.model_validate_json(text)
    except ValidationError as invalid:
        return "; ".join(
            f"{'.'.join(str(part) for part in issue['loc']) or 'reply'}: {issue['msg']}"
            for issue in invalid.errors(include_url=False)
        )
    return str(error) if error is not None else "the reply did not parse"


def _unavailable(error: Exception, config: OllamaConfig) -> OllamaUnavailable:
    if isinstance(error, httpx.TimeoutException):
        return OllamaUnavailable(
            f"Ollama の応答が {config.timeout_seconds:g} 秒以内に返りませんでした。"
        )
    if isinstance(error, ollama.ResponseError):
        return OllamaUnavailable(
            f"Ollama がリクエストを受け付けませんでした（{error.error}）。"
            f"モデル `{config.model}` が `ollama list` にあるか確かめてください。"
        )
    return OllamaUnavailable(
        f"Ollama に接続できません（{config.base_url}）。"
        "`ollama serve` が動いているか確かめてください。"
    )
