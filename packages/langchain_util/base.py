"""Invoke a LangChain chain with retries, observability, and prompt repair.

`invoke_llm` renders a prompt template, calls a chat model, and parses the
result. `invoke_llm_detailed` returns the same value plus token usage, attempt
count, and latency. `ainvoke_llm`, `stream_llm`, and `astream_llm` mirror it
for async and incremental consumption.

Any `BasePromptTemplate` works, in any dialect LangChain renders -- f-string,
jinja2, or mustache. `langchain_util.prompts` loads jinja2 templates from
`.jinja` files; `examples/` uses them throughout.
"""

import asyncio
import copy
import logging
import random
import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, overload

from langchain_core.callbacks import BaseCallbackHandler, BaseCallbackManager
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import (
    BasePromptTemplate,
    ChatPromptTemplate,
    PromptTemplate,
)
from langchain_core.prompts.string import PromptTemplateFormat
from langchain_core.runnables import Runnable, RunnableConfig
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_random_exponential,
)
from tenacity.stop import stop_base

from packages.langchain_util.observability import Usage, UsageCollector, dump_exchange

# Deliberately `Runnable`, not `RunnableSerializable`: nothing here needs
# serialization, and RunnableLambda -- the natural way to stub a model in a
# test -- is not a RunnableSerializable.
type ChatLLM = Runnable[Any, BaseMessage]
type Parser = Runnable[Any, Any]

DEFAULT_TITLE = "<title>"

TRANSIENT_API_ERRORS: tuple[type[BaseException], ...] = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
"""Provider-side failures that are worth retrying unchanged."""

DEFAULT_RETRY_ON: tuple[type[BaseException], ...] = (
    *TRANSIENT_API_ERRORS,
    OutputParserException,
)
"""Transient API errors plus parse failures.

Deliberately *not* bare `ValueError`: `OutputParserException` subclasses it, but
so do `pydantic.ValidationError` and every ordinary programming mistake, and
retrying those just burns six billed calls on a bug that will never fix itself.
"""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How a failing invocation is retried.

    `deadline` caps total wall-clock time across all attempts; without it a run
    of rate-limit errors can stall for as long as the backoff allows.
    """

    attempts: int = 6
    multiplier: float = 1.0
    max_wait: float = 20.0
    deadline: float | None = None
    retry_on: tuple[type[BaseException], ...] = DEFAULT_RETRY_ON


DEFAULT_RETRY_POLICY = RetryPolicy()


@dataclass(frozen=True, slots=True)
class InvocationResult[T]:
    """A parsed value plus everything observable about how it was produced."""

    value: T
    usage: Usage
    attempts: int
    latency_s: float
    debug_path: Path | None = None


class ChainFactory(Protocol):
    """Builds the runnable that `invoke_llm` executes.

    A custom factory is responsible for keeping the parser's output type: the
    `invoke_llm` overloads infer the return type from `parser`, so a factory
    that drops or replaces the parser makes that inferred type a lie.
    """

    def __call__(
        self,
        *,
        template: BasePromptTemplate[str],
        chat: ChatLLM,
        parser: Parser,
    ) -> Parser: ...


def default_chain_factory(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
) -> Parser:
    """Compose the plain `template | chat | parser` pipeline."""
    return template | chat | parser


def _before_sleep(
    logger: logging.Logger,
    title: str,
) -> Callable[[RetryCallState], None]:
    """Log each retry to the *caller's* logger, with the title closed over.

    Both matter: binding the module logger here would hide retries from the
    logger the caller passed in, and reading the title out of
    `retry_state.kwargs` only works while every argument is passed by keyword.
    """

    def hook(retry_state: RetryCallState) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        logger.warning(
            "Retrying LLM invocation (attempt %d) for %s due to %s: %s",
            retry_state.attempt_number,
            title,
            type(exc).__name__ if exc else "unknown error",
            exc,
        )

    return hook


def _stop_condition(policy: RetryPolicy) -> stop_base:
    stop: stop_base = stop_after_attempt(policy.attempts)
    if policy.deadline is not None:
        stop = stop | stop_after_delay(policy.deadline)

    return stop


def _retry_kwargs(
    policy: RetryPolicy,
    logger: logging.Logger,
    title: str,
) -> dict[str, Any]:
    return {
        "retry": retry_if_exception_type(policy.retry_on),
        "wait": wait_random_exponential(
            multiplier=policy.multiplier,
            max=policy.max_wait,
        ),
        "stop": _stop_condition(policy),
        "before_sleep": _before_sleep(logger, title),
        "reraise": True,
    }


REPAIR_FEEDBACK_VARIABLE = "_repair_feedback"
"""Partial variable that carries parser feedback into a repaired prompt."""

_FEEDBACK_PLACEHOLDER: dict[PromptTemplateFormat, str] = {
    "f-string": f"{{{REPAIR_FEEDBACK_VARIABLE}}}",
    "jinja2": f"{{{{ {REPAIR_FEEDBACK_VARIABLE} }}}}",
    # Triple braces: mustache HTML-escapes a `{{var}}`, which would turn the
    # quotes in a JSON parse error into `&quot;`.
    "mustache": f"{{{{{{{REPAIR_FEEDBACK_VARIABLE}}}}}}}",
}
"""How to reference the feedback variable in each dialect LangChain renders.

Feedback travels as a *value*, never as template text: every formatter
substitutes values without rescanning them, so model output full of `{`, `}`,
`{{ q }}`, or `{% if %}` lands in the prompt verbatim. Splicing that text
straight into the template instead is what used to invent phantom input
variables (f-string) or execute as markup (jinja2).
"""


def _repair_template(
    template: BasePromptTemplate[str],
    error: BaseException,
    title: str,
) -> BasePromptTemplate[str] | None:
    """Append parser feedback to a copy of `template`, or None if unsupported.

    Always derived from the *original* template so feedback never accumulates
    across attempts, and via `model_copy` so `partial_variables` and
    `template_format` survive -- rebuilding with `from_template` silently drops
    partials and breaks every template built with `.partial(...)`.
    """
    feedback = f"\nError in {title} ({type(error).__name__}): {error}"

    if isinstance(template, PromptTemplate):
        placeholder = _FEEDBACK_PLACEHOLDER.get(template.template_format)
        if placeholder is None:
            return None

        return template.model_copy(
            update={
                "template": template.template + placeholder,
                "partial_variables": {
                    **template.partial_variables,
                    REPAIR_FEEDBACK_VARIABLE: feedback,
                },
            },
        )

    if isinstance(template, ChatPromptTemplate):
        # A concrete HumanMessage is a literal, not a template, so its braces
        # are never parsed -- no escaping needed on this path.
        return template.model_copy(
            update={"messages": [*template.messages, HumanMessage(content=feedback)]},
        )

    return None


def _prepare_config(
    config: RunnableConfig | None,
    handlers: Sequence[BaseCallbackHandler],
) -> RunnableConfig:
    """Copy the caller's config and add handlers so nested runs see them.

    Never mutates `config`: callers reuse a single `RunnableConfig` across
    invocations. Handlers are added *inheritably*, because
    `CallbackManager.get_child` propagates `inheritable_handlers` only -- wrap a
    list in a bare `BaseCallbackManager` and your handlers stop firing for the
    model call itself.
    """
    prepared: RunnableConfig = {} if config is None else copy.copy(config)
    if not handlers:
        return prepared

    existing = prepared.get("callbacks")
    if existing is None:
        prepared["callbacks"] = list(handlers)
    elif isinstance(existing, BaseCallbackManager):
        manager = existing.copy()
        for handler in handlers:
            manager.add_handler(handler, inherit=True)
        prepared["callbacks"] = manager
    else:
        prepared["callbacks"] = [*existing, *handlers]

    return prepared


def _normalize_title(title: str | None, input_data: dict[str, Any]) -> str:
    candidate = title if title is not None else input_data.get("title")
    return candidate if isinstance(candidate, str) else DEFAULT_TITLE


def _effective_chat(chat: ChatLLM, dry_run: str | None) -> ChatLLM:
    if dry_run is None:
        return chat

    # FakeListChatModel cycles its responses, so retries stay satisfied.
    return FakeListChatModel(responses=[dry_run])


def _sleep_ceiling(policy: RetryPolicy, attempt: int) -> float:
    return min(policy.max_wait, policy.multiplier * (2**attempt))


def _log_outcome(
    logger: logging.Logger,
    title: str,
    usage: Usage,
    attempts: int,
    latency_s: float,
) -> None:
    logger.info(
        "LLM invocation for %s finished in %.2fs over %d attempt(s): %s",
        title,
        latency_s,
        attempts,
        usage.describe(),
    )
    if usage.raw_output is not None:
        logger.debug("Raw LLM output for %s:\n%s", title, usage.raw_output)


@dataclass
class _Attempt:
    """Mutable per-invocation state shared with the retry closure."""

    template: BasePromptTemplate[str]
    repaired: BasePromptTemplate[str] | None = None
    collectors: list[UsageCollector] = field(default_factory=list)

    def active_template(self) -> BasePromptTemplate[str]:
        return self.repaired if self.repaired is not None else self.template

    def merged_usage(self) -> Usage:
        """Usage from the final attempt, which is the one that produced a value."""
        return self.collectors[-1].usage if self.collectors else Usage()


def _invoke_detailed(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None,
    input_data: dict[str, Any],
    config: RunnableConfig | None,
    title: str | None,
    retry_policy: RetryPolicy,
    repair_prompt_on_parse_error: bool,
    dry_run: str | None,
    debug_dir: str | Path | None,
) -> InvocationResult[Any]:
    normalized_title = _normalize_title(title, input_data)
    factory = chain_factory or default_chain_factory
    active_chat = _effective_chat(chat, dry_run)
    state = _Attempt(template=template)

    logger.info("Invoking LLM chain for %s...", normalized_title)
    if dry_run is not None:
        logger.warning(
            "Dry run for %s: no provider call will be made", normalized_title
        )

    started = time.perf_counter()
    retrying = Retrying(**_retry_kwargs(retry_policy, logger, normalized_title))

    def run_once() -> Any:
        collector = UsageCollector()
        state.collectors.append(collector)
        chain = factory(
            template=state.active_template(),
            chat=active_chat,
            parser=parser,
        )
        try:
            return chain.invoke(
                input_data,
                _prepare_config(config, [collector]),
            )
        except OutputParserException as exc:
            if repair_prompt_on_parse_error:
                state.repaired = _repair_template(
                    state.template,
                    exc,
                    normalized_title,
                )
            raise

    try:
        value = retrying(run_once)
    except BaseException as exc:
        failed_usage = state.merged_usage()
        failed_attempts = int(
            retrying.statistics.get("attempt_number", len(state.collectors))
        )
        logger.exception(
            "LLM invocation failed after %d attempt(s) in %.2fs for %s",
            failed_attempts,
            time.perf_counter() - started,
            normalized_title,
        )
        # Surfacing the unparseable output here is what callers used to need a
        # custom logging chain_factory for.
        if failed_usage.raw_output is not None:
            logger.debug(
                "Last raw LLM output for %s:\n%s",
                normalized_title,
                failed_usage.raw_output,
            )
        dump_exchange(
            title=normalized_title,
            usage=failed_usage,
            error=exc,
            attempts=failed_attempts,
            directory=debug_dir,
        )
        raise

    latency_s = time.perf_counter() - started
    attempts = int(retrying.statistics.get("attempt_number", len(state.collectors)))
    usage = state.merged_usage()
    _log_outcome(logger, normalized_title, usage, attempts, latency_s)

    debug_path = dump_exchange(
        title=normalized_title,
        usage=usage,
        parsed=value,
        attempts=attempts,
        directory=debug_dir,
    )

    return InvocationResult(
        value=value,
        usage=usage,
        attempts=attempts,
        latency_s=latency_s,
        debug_path=debug_path,
    )


@overload
def invoke_llm_detailed(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: StrOutputParser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = ...,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> InvocationResult[str]: ...


@overload
def invoke_llm_detailed[T: BaseModel](
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: PydanticOutputParser[T],
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = ...,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> InvocationResult[T]: ...


@overload
def invoke_llm_detailed(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = ...,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> InvocationResult[Any]: ...


def invoke_llm_detailed(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> InvocationResult[Any]:
    """Invoke an LLM and return the parsed value with usage metadata.

    Args:
        template: Prompt template to render.
        chat: Chat model runnable.
        parser: Output parser; determines the inferred return type.
        logger: Caller's logger. Retries and failures are reported here.
        chain_factory: Custom chain composition. Must preserve the parser's
            output type -- see `ChainFactory`.
        input: Template variables. A "title" key is used for log messages when
            `title` is not given.
        config: Runnable config. Copied, never mutated.
        title: Label for log messages.
        retry_policy: Attempts, backoff, deadline, and retryable exceptions.
        repair_prompt_on_parse_error: On a parse failure, append the error to a
            copy of the prompt so the next attempt can correct itself.
        dry_run: If set, bypass the provider and treat this string as the model
            output. The real parser still runs, so prompt and schema wiring can
            be exercised without spending anything.
        debug_dir: Write a redacted prompt/response dump here. Defaults to
            `$LANGCHAIN_UTIL_DEBUG_DIR`.

    Returns:
        The parsed value plus token usage, attempt count, and latency.
    """
    return _invoke_detailed(
        template=template,
        chat=chat,
        parser=parser,
        logger=logger,
        chain_factory=chain_factory,
        input_data=input or {},
        config=config,
        title=title,
        retry_policy=retry_policy,
        repair_prompt_on_parse_error=repair_prompt_on_parse_error,
        dry_run=dry_run,
        debug_dir=debug_dir,
    )


@overload
def invoke_llm(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: StrOutputParser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = ...,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> str: ...


@overload
def invoke_llm[T: BaseModel](
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: PydanticOutputParser[T],
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = ...,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> T: ...


@overload
def invoke_llm(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = ...,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> Any: ...


def invoke_llm(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> Any:
    """Invoke an LLM with retries and return just the parsed value.

    See `invoke_llm_detailed` for the full argument reference and for access to
    token usage, raw output, attempt count, and latency.
    """
    return invoke_llm_detailed(
        template=template,
        chat=chat,
        parser=parser,
        logger=logger,
        chain_factory=chain_factory,
        input=input,
        config=config,
        title=title,
        retry_policy=retry_policy,
        repair_prompt_on_parse_error=repair_prompt_on_parse_error,
        dry_run=dry_run,
        debug_dir=debug_dir,
    ).value


async def ainvoke_llm(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    repair_prompt_on_parse_error: bool = True,
    dry_run: str | None = None,
    debug_dir: str | Path | None = None,
) -> Any:
    """Async counterpart of `invoke_llm`.

    Returns `Any` rather than the parser's type: overload resolution across an
    awaited call adds noise for little gain here, so annotate at the call site
    if you need the precise type.
    """
    input_data = input or {}
    normalized_title = _normalize_title(title, input_data)
    factory = chain_factory or default_chain_factory
    active_chat = _effective_chat(chat, dry_run)
    state = _Attempt(template=template)

    logger.info("Invoking LLM chain for %s (async)...", normalized_title)
    started = time.perf_counter()

    async def run_once() -> Any:
        collector = UsageCollector()
        state.collectors.append(collector)
        chain = factory(
            template=state.active_template(),
            chat=active_chat,
            parser=parser,
        )
        try:
            return await chain.ainvoke(
                input_data,
                _prepare_config(config, [collector]),
            )
        except OutputParserException as exc:
            if repair_prompt_on_parse_error:
                state.repaired = _repair_template(
                    state.template,
                    exc,
                    normalized_title,
                )
            raise

    retrying = AsyncRetrying(**_retry_kwargs(retry_policy, logger, normalized_title))

    try:
        value: Any = await retrying(run_once)
    except BaseException as exc:
        logger.exception(
            "Async LLM invocation failed for %s",
            normalized_title,
        )
        dump_exchange(
            title=normalized_title,
            usage=state.merged_usage(),
            error=exc,
            attempts=len(state.collectors),
            directory=debug_dir,
        )
        raise

    latency_s = time.perf_counter() - started
    usage = state.merged_usage()
    _log_outcome(logger, normalized_title, usage, len(state.collectors), latency_s)
    dump_exchange(
        title=normalized_title,
        usage=usage,
        parsed=value,
        attempts=len(state.collectors),
        directory=debug_dir,
    )

    return value


def stream_llm(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    dry_run: str | None = None,
) -> Iterator[Any]:
    """Stream chunks from the chain.

    Retries only while nothing has been yielded yet. Once a chunk reaches the
    consumer, restarting would replay output they already have, so a later
    failure propagates instead.
    """
    input_data = input or {}
    normalized_title = _normalize_title(title, input_data)
    factory = chain_factory or default_chain_factory
    active_chat = _effective_chat(chat, dry_run)
    chain = factory(template=template, chat=active_chat, parser=parser)
    prepared = _prepare_config(config, [])

    logger.info("Streaming LLM chain for %s...", normalized_title)

    for attempt in range(1, retry_policy.attempts + 1):
        produced = False
        try:
            for chunk in chain.stream(input_data, prepared):
                produced = True
                yield chunk
            return
        except Exception as exc:
            retryable = isinstance(exc, retry_policy.retry_on)
            if produced or not retryable or attempt == retry_policy.attempts:
                logger.exception("Streaming failed for %s", normalized_title)
                raise

            logger.warning(
                "Retrying stream (attempt %d) for %s due to %s: %s",
                attempt,
                normalized_title,
                type(exc).__name__,
                exc,
            )
            time.sleep(random.uniform(0, _sleep_ceiling(retry_policy, attempt)))


async def astream_llm(
    *,
    template: BasePromptTemplate[str],
    chat: ChatLLM,
    parser: Parser,
    logger: logging.Logger,
    chain_factory: ChainFactory | None = None,
    input: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    title: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    dry_run: str | None = None,
) -> AsyncIterator[Any]:
    """Async counterpart of `stream_llm`, with the same retry semantics."""
    input_data = input or {}
    normalized_title = _normalize_title(title, input_data)
    factory = chain_factory or default_chain_factory
    active_chat = _effective_chat(chat, dry_run)
    chain = factory(template=template, chat=active_chat, parser=parser)
    prepared = _prepare_config(config, [])

    logger.info("Streaming LLM chain for %s (async)...", normalized_title)

    for attempt in range(1, retry_policy.attempts + 1):
        produced = False
        try:
            async for chunk in chain.astream(input_data, prepared):
                produced = True
                yield chunk
            return
        except Exception as exc:
            retryable = isinstance(exc, retry_policy.retry_on)
            if produced or not retryable or attempt == retry_policy.attempts:
                logger.exception("Async streaming failed for %s", normalized_title)
                raise

            logger.warning(
                "Retrying async stream (attempt %d) for %s due to %s: %s",
                attempt,
                normalized_title,
                type(exc).__name__,
                exc,
            )
            await asyncio.sleep(
                random.uniform(0, _sleep_ceiling(retry_policy, attempt))
            )
