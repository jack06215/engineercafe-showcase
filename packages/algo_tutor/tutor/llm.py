"""The one place that talks to a model (SPEC §12.3).

`chat_model` builds the LangChain client from a task's merged config;
`ask` sends one structured request, makes one repair call if the reply
doesn't parse, and turns every failure into a `TutorError` with a SPEC §12.1
kind. Tests hand `ask` a scripted chat model instead of a real one.
"""

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import ollama
import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from pydantic import BaseModel, ValidationError

from packages.algo_tutor.config import TaskConfig
from packages.algo_tutor.domain.enums import TutorErrorKind
from packages.algo_tutor.tutor.language import OutputLanguage, pin
from packages.langchain_util.api_client import get_langchain_client


class TutorError(Exception):
    """Why a tutor call produced nothing. `kind` is what the panel shows."""

    def __init__(self, kind: TutorErrorKind, message: str) -> None:
        """Store the error *kind* with its *message*."""
        super().__init__(message)
        self.kind = kind
        self.message = message


ChatFactory = Callable[[TaskConfig], BaseChatModel]


def chat_model(task: TaskConfig) -> BaseChatModel:
    """The task's chat client, built from the merged config.

    It comes from `langchain_util.get_langchain_client`. `reasoning` is Ollama's
    thinking switch, so only Ollama gets it; the OpenAI clients don't retry, so
    the timeout is the ceiling.
    """
    match task.provider:
        case "ollama":
            return get_langchain_client(
                "ollama",
                model=task.model,
                temperature=task.temperature,
                reasoning=task.reasoning,
                client_kwargs={"timeout": task.timeout_s},
                verbose=False,
            )
        case "openai":
            return get_langchain_client(
                "openai",
                model=task.model,
                temperature=task.temperature,
                timeout=task.timeout_s,
                max_retries=0,
                verbose=False,
            )
        case "azure":
            return get_langchain_client(
                "azure",
                temperature=task.temperature,
                timeout=task.timeout_s,
                max_retries=0,
                verbose=False,
            )


@dataclass(frozen=True)
class Answer[T: BaseModel]:
    """A validated model reply, and whether it needed a repair."""

    value: T
    repaired: bool
    latency_ms: int


def ask[T: BaseModel](
    chat: BaseChatModel,
    schema: type[T],
    instructions: str,
    context: dict[str, Any],
    language: OutputLanguage,
    task: TaskConfig,
) -> Answer[T]:
    """One structured call with one repair (SPEC §12.3).

    The context goes in as JSON in a single user message; it is data, which
    every system prompt says too. Still invalid after the repair is
    `invalid_output`.
    """
    messages: list[BaseMessage] = [
        SystemMessage(f"{instructions}\n{pin(language)}"),
        HumanMessage(json.dumps(context, ensure_ascii=False, indent=1, default=str)),
    ]
    started = time.monotonic()
    text = _invoke(chat, schema, messages, task)
    value, error = _parse(schema, text)
    repaired = False
    if value is None:
        repaired = True
        messages += [
            AIMessage(text),
            HumanMessage(
                f"That reply doesn't match the required JSON schema: {error}. "
                f"Send the whole JSON object again, fixed, and nothing else. {pin(language)}"
            ),
        ]
        text = _invoke(chat, schema, messages, task)
        value, error = _parse(schema, text)
        if value is None:
            raise TutorError(
                TutorErrorKind.INVALID_OUTPUT,
                f"Still invalid after one repair: {error}",
            )
    return Answer(
        value=value,
        repaired=repaired,
        latency_ms=round((time.monotonic() - started) * 1000),
    )


def _invoke(
    chat: BaseChatModel,
    schema: type[BaseModel],
    messages: Sequence[BaseMessage],
    task: TaskConfig,
) -> str:
    """The model's raw reply text.

    Real providers are constrained to the schema; anything else (the tests'
    scripted model) is called as is.
    """
    try:
        if isinstance(chat, ChatOllama | ChatOpenAI | AzureChatOpenAI):
            structured = chat.with_structured_output(
                schema, method="json_schema", include_raw=True
            )
            result = structured.invoke(list(messages))
            raw = result["raw"] if isinstance(result, dict) else result
        else:
            raw = chat.invoke(list(messages))
    except TutorError:
        raise
    except Exception as exc:
        # Every provider failure becomes a panel message (SPEC §12.1).
        raise classify(exc, task) from exc
    return raw.text if isinstance(raw, BaseMessage) else str(raw)


def _parse[T: BaseModel](schema: type[T], text: str) -> tuple[T | None, str]:
    try:
        return schema.model_validate_json(_strip_fence(text)), ""
    except ValidationError as invalid:
        issues = [
            f"{'.'.join(str(part) for part in issue['loc']) or 'reply'}: {issue['msg']}"
            for issue in invalid.errors(include_url=False)
        ]
        return None, "; ".join(issues)


def _strip_fence(text: str) -> str:
    """Some models wrap JSON in a ```json fence even when constrained."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.removesuffix("```").strip()
    return body


def classify(exc: BaseException, task: TaskConfig) -> TutorError:
    """A SPEC §12.1 kind for whatever a call raised."""
    where = f"{task.provider} {task.model}"
    # Timeouts first: openai's APITimeoutError is an APIConnectionError.
    if isinstance(exc, httpx.TimeoutException | openai.APITimeoutError | TimeoutError):
        return TutorError(
            TutorErrorKind.TIMEOUT, f"{where} didn't answer within {task.timeout_s:g} s"
        )
    if isinstance(
        exc, ConnectionError | httpx.ConnectError | openai.APIConnectionError
    ):
        hint = " Is `ollama serve` running?" if task.provider == "ollama" else ""
        return TutorError(
            TutorErrorKind.UNAVAILABLE, f"Couldn't reach {task.provider}.{hint}"
        )
    if isinstance(exc, ollama.ResponseError) and (
        exc.status_code == 404 or "not found" in str(exc.error).lower()
    ):
        return TutorError(
            TutorErrorKind.MODEL_MISSING,
            f"Model {task.model!r} isn't installed. Run `ollama pull {task.model}` or change config.yaml.",
        )
    if isinstance(exc, openai.NotFoundError):
        return TutorError(
            TutorErrorKind.MODEL_MISSING, f"{task.provider} has no model {task.model!r}"
        )
    return TutorError(TutorErrorKind.ERROR, f"{type(exc).__name__}: {exc}")
