"""Token usage, cost, and on-disk debugging for LLM invocations.

`UsageCollector` is a callback handler that records what a chain actually sent
and received. It only works if it is registered as an *inheritable* handler --
a handler attached non-inheritably sees the outer chain start and nothing else,
because `CallbackManager.get_child` propagates `inheritable_handlers` only.
`langchain_util.base` wires it up correctly; see `_prepare_config` there.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

_LOGGER = logging.getLogger(__name__)

DEBUG_DIR_ENV = "LANGCHAIN_UTIL_DEBUG_DIR"
"""Set this to a directory path to dump every prompt/response pair to disk."""


@dataclass(frozen=True, slots=True)
class Pricing:
    """Price per one million tokens, in whatever currency you register."""

    input_per_1m: float
    output_per_1m: float


MODEL_PRICING: dict[str, Pricing] = {}
"""Model name -> price.

Deliberately empty: published prices change, and a stale hard-coded table is
worse than no table because it silently reports wrong numbers. Register the
models you actually use at startup, e.g.

    register_pricing("gpt-4o-mini", input_per_1m=0.15, output_per_1m=0.60)

`Usage.cost` returns None -- and cost logging stays silent -- for any model
with no registered price.
"""

_SECRET_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "LLM_ZSH_PYTHON_OPENAI_API_KEY",
    "OPENAI_API_KEY",
)

_API_KEY_PATTERN = re.compile(
    r"\b(?:sk|xoxb|xoxp|ghp|gho|github_pat)-[A-Za-z0-9_\-]{8,}"
)


def register_pricing(
    model: str,
    *,
    input_per_1m: float,
    output_per_1m: float,
) -> None:
    """Register the token price for a model so `Usage.cost` can be computed."""
    MODEL_PRICING[model] = Pricing(
        input_per_1m=input_per_1m,
        output_per_1m=output_per_1m,
    )


def redact(text: str) -> str:
    """Strip credentials from text before it is written to disk or logged."""
    for name in _SECRET_ENV_NAMES:
        value = os.getenv(name)
        if value and len(value) > 8:
            text = text.replace(value, f"<{name}>")

    return _API_KEY_PATTERN.sub("<redacted-key>", text)


@dataclass
class Usage:
    """What a single `invoke_llm` call sent, received, and spent."""

    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    prompts: list[str] = field(default_factory=list)
    raw_outputs: list[str] = field(default_factory=list)

    @property
    def prompt(self) -> str | None:
        """The last fully rendered prompt sent to the model."""
        return self.prompts[-1] if self.prompts else None

    @property
    def raw_output(self) -> str | None:
        """The last raw model output, before parsing."""
        return self.raw_outputs[-1] if self.raw_outputs else None

    @property
    def cost(self) -> float | None:
        """Cost of this invocation, or None if the model has no registered price."""
        pricing = MODEL_PRICING.get(self.model or "")
        if pricing is None:
            return None

        return (
            self.input_tokens * pricing.input_per_1m
            + self.output_tokens * pricing.output_per_1m
        ) / 1_000_000

    def describe(self) -> str:
        """One-line human summary, suitable for a log record."""
        tokens = (
            f"tokens={self.total_tokens}"
            f" (in={self.input_tokens} out={self.output_tokens})"
        )
        parts = [
            f"model={self.model or 'unknown'}",
            tokens,
            f"llm_calls={self.llm_calls}",
        ]
        cost = self.cost
        if cost is not None:
            parts.append(f"cost={cost:.6f}")

        return " ".join(parts)


class UsageCollector(BaseCallbackHandler):
    """Collects rendered prompts, raw outputs, and token counts from a chain."""

    def __init__(self) -> None:
        self.usage = Usage()

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self.usage.prompts.extend(prompts)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        for conversation in messages:
            rendered = "\n".join(
                f"{message.type}: {message.text}" for message in conversation
            )
            self.usage.prompts.append(rendered)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self.usage.llm_calls += 1

        counted_from_message = False
        for generations in response.generations:
            for generation in generations:
                if generation.text:
                    self.usage.raw_outputs.append(generation.text)
                counted_from_message |= self._absorb_generation(generation)

        self._absorb_llm_output(response.llm_output, counted=counted_from_message)

    def _absorb_generation(self, generation: object) -> bool:
        """Read usage off the AIMessage, the modern chat-model location."""
        message = getattr(generation, "message", None)
        if message is None:
            return False

        self.usage.model = self.usage.model or _model_name(
            getattr(message, "response_metadata", None)
        )

        metadata = getattr(message, "usage_metadata", None)
        if not metadata:
            return False

        self.usage.input_tokens += int(metadata.get("input_tokens", 0))
        self.usage.output_tokens += int(metadata.get("output_tokens", 0))
        self.usage.total_tokens += int(metadata.get("total_tokens", 0))
        return True

    def _absorb_llm_output(
        self,
        llm_output: dict[str, Any] | None,
        *,
        counted: bool,
    ) -> None:
        """Fall back to `llm_output['token_usage']` for older integrations."""
        if not llm_output:
            return

        self.usage.model = self.usage.model or _model_name(llm_output)

        if counted:
            return

        token_usage = llm_output.get("token_usage") or {}
        if not isinstance(token_usage, dict):
            return

        self.usage.input_tokens += int(token_usage.get("prompt_tokens", 0))
        self.usage.output_tokens += int(token_usage.get("completion_tokens", 0))
        self.usage.total_tokens += int(token_usage.get("total_tokens", 0))


def _model_name(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None

    for key in ("model_name", "model", "model_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def _slugify(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return slug[:60] or "untitled"


def dump_exchange(
    *,
    title: str,
    usage: Usage,
    parsed: object = None,
    error: BaseException | None = None,
    attempts: int = 1,
    directory: str | Path | None = None,
) -> Path | None:
    """Write a prompt/response record to disk for debugging.

    No-ops unless `directory` is given or `LANGCHAIN_UTIL_DEBUG_DIR` is set.
    Credentials are redacted. Returns the file written, if any.
    """
    target = directory or os.getenv(DEBUG_DIR_ENV)
    if not target:
        return None

    payload = {
        "title": title,
        "timestamp": datetime.now(UTC).isoformat(),
        "attempts": attempts,
        "model": usage.model,
        "tokens": {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "total": usage.total_tokens,
        },
        "cost": usage.cost,
        "llm_calls": usage.llm_calls,
        "prompts": [redact(prompt) for prompt in usage.prompts],
        "raw_outputs": [redact(output) for output in usage.raw_outputs],
        "parsed": None if parsed is None else redact(_stringify(parsed)),
        "error": None
        if error is None
        else f"{type(error).__name__}: {redact(str(error))}",
    }

    try:
        directory_path = Path(target)
        directory_path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        path = directory_path / f"{stamp}-{_slugify(title)}.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError:
        # Debug tracing must never break the caller's actual work.
        _LOGGER.warning("Could not write LLM debug dump to %s", target, exc_info=True)
        return None

    return path


def _stringify(value: object) -> str:
    dump = getattr(value, "model_dump_json", None)
    if callable(dump):
        result = dump()
        if isinstance(result, str):
            return result

    return str(value)
