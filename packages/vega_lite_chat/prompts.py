"""The prompts from prompts.yaml, for the chat model and the translator.

They are the chat model's instructions, and the translator's instructions, few-shot examples and the
messages for one call.

The JSON schema goes into the translator's system prompt as text as well: `with_structured_output` hands it to
Ollama only as `format`, which constrains the output but never shows the field descriptions to the
model. Every example's chart is checked against its sample's profile at load, because a broken
example teaches the model the wrong thing.
"""

import functools
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from packages.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
)
from packages.vega_lite_chat.checks import check_chart
from packages.vega_lite_chat.config import DataConfig
from packages.vega_lite_chat.csv_loader import (
    InputError,
    load_csv,
)
from packages.vega_lite_chat.profile import (
    DataProfile,
    profile_frame,
    profile_yaml,
)
from packages.vega_lite_chat.samples import sample_named

DEFAULT_PROMPTS = Path(__file__).with_name("prompts.yaml")


class PromptError(Exception):
    """prompts.yaml is malformed, or one of its examples fails the chart checks."""


class Example(BaseModel):
    """A worked example for the translator prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample: str  # a sample CSV's file name, e.g. "sales_by_region.csv"
    current: ChartSpec | None = None
    recent: list[str] = Field(default_factory=list)
    request: str
    reply: AssistantTurn


class _PromptFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chat_system: str
    system: str
    first_chart_request: str
    examples: list[Example]


@dataclass(frozen=True)
class PromptBook:
    """The prompt texts and examples loaded from the prompt files."""

    chat_system: (
        str  # the chat model's instructions; chat_system_prompt appends the table
    )
    system: str  # the translator's instructions; build_messages appends the schema
    first_chart_request: str
    examples: tuple[Example, ...]
    example_profiles: dict[str, DataProfile]  # by sample file name


def load_prompts(path: Path = DEFAULT_PROMPTS, *, data: DataConfig) -> PromptBook:
    """Read `path` and check every example against its sample's profile; any failure raises `PromptError`."""
    try:
        parsed = _PromptFile.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
    except (yaml.YAMLError, ValidationError) as error:
        raise PromptError(f"{path.name}: {error}") from error

    profiles: dict[str, DataProfile] = {}
    for number, example in enumerate(parsed.examples, start=1):
        label = f"{path.name} example {number} ({example.request})"
        if example.sample not in profiles:
            profiles[example.sample] = _sample_profile(example.sample, data, label)
        for role, chart in (
            ("current", example.current),
            ("reply", example.reply.chart),
        ):
            if chart is None:
                continue
            errors = check_chart(chart, profiles[example.sample])
            if errors:
                raise PromptError(
                    f"{label}: the {role} chart fails the checks: {'; '.join(errors)}"
                )

    return PromptBook(
        chat_system=parsed.chat_system,
        system=parsed.system,
        first_chart_request=parsed.first_chart_request,
        examples=tuple(parsed.examples),
        example_profiles=profiles,
    )


def chat_system_prompt(
    book: PromptBook, profile: DataProfile, current: ChartSpec | None
) -> str:
    """The chat model's instructions, then the table it is about and the chart on screen."""
    return (
        f"{book.chat_system.rstrip()}\n\n"
        f"## Data profile\n{profile_yaml(profile).rstrip()}\n\n"
        f"## Current chart\n{_chart_text(current)}"
    )


def build_messages(
    book: PromptBook,
    profile: DataProfile,
    current: ChartSpec | None,
    recent: Sequence[str],
    request: str,
) -> list[BaseMessage]:
    """System prompt, the example pairs, then this request, all in the same user-message format."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt(book))]
    for example in book.examples:
        messages.append(
            HumanMessage(
                content=user_message(
                    book.example_profiles[example.sample],
                    example.current,
                    example.recent,
                    example.request,
                )
            )
        )
        messages.append(AIMessage(content=reply_json(example.reply)))
    messages.append(
        HumanMessage(content=user_message(profile, current, recent, request))
    )
    return messages


def repair_message(errors: Sequence[str]) -> HumanMessage:
    """The follow-up after an invalid reply: what was wrong, and a request to try again."""
    bullets = "\n".join(f"- {error}" for error in errors)
    return HumanMessage(
        content=f"Your reply was invalid:\n{bullets}\n\nReply again with the corrected JSON."
    )


def system_prompt(book: PromptBook) -> str:
    """Return the translator's instructions followed by the reply schema."""
    return (
        f"{book.system.rstrip()}\n\n"
        "The reply must match this JSON schema (shown as YAML):\n\n"
        f"{_schema_yaml()}"
    )


def user_message(
    profile: DataProfile,
    current: ChartSpec | None,
    recent: Sequence[str],
    request: str,
) -> str:
    """Build the translator's user message for one request."""
    recent_text = "\n".join(f"- {line}" for line in recent) if recent else "none"
    return (
        f"## Data profile\n{profile_yaml(profile).rstrip()}\n\n"
        f"## Current chart\n{_chart_text(current)}\n\n"
        f"## Recent requests (oldest first)\n{recent_text}\n\n"
        f"## Request\n{request}"
    )


def reply_json(turn: AssistantTurn) -> str:
    """An example reply as the model should write it.

    The keys the schema requires stay even when empty: `chart: null`, and `filters: []` right after
    `mark`.
    """
    chart = None
    if turn.chart is not None:
        rest = _compact(turn.chart)
        chart = {
            "mark": rest.pop("mark"),
            "filters": rest.pop("filters", []),
            **rest,
        }
    return json.dumps({"chart": chart, "message": turn.message}, ensure_ascii=False)


def chart_yaml(spec: ChartSpec) -> str:
    """A chart as readable YAML with Vega-Lite's key names, leaving out unset fields."""
    return yaml.safe_dump(_compact(spec), allow_unicode=True, sort_keys=False)


def _chart_text(spec: ChartSpec | None) -> str:
    return chart_yaml(spec).rstrip() if spec is not None else "none"


def _compact(spec: ChartSpec) -> dict[str, Any]:
    return spec.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_defaults=True
    )


def _sample_profile(name: str, data: DataConfig, label: str) -> DataProfile:
    try:
        frame = load_csv(sample_named(name).read_bytes())
    except (LookupError, InputError, OSError) as error:
        raise PromptError(f"{label}: can't read sample {name!r}: {error}") from error
    return profile_frame(
        frame,
        sample_rows=data.sample_rows,
        seed=data.sample_seed,
        max_listed_values=data.max_listed_values,
    )


@functools.cache
def _schema_yaml() -> str:
    schema = _without_model_docstrings(
        _without_titles(AssistantTurn.model_json_schema(by_alias=True))
    )
    return yaml.safe_dump(schema, allow_unicode=True, sort_keys=False)


def _without_model_docstrings(schema: dict[str, Any]) -> dict[str, Any]:
    # pydantic copies each model's docstring into the schema as "description". The docstrings are
    # written for programmers; the Field descriptions are the instructions written for the model.
    for model in [schema, *schema.get("$defs", {}).values()]:
        model.pop("description", None)
    return schema


def _without_titles(node: Any) -> Any:
    # pydantic adds a "title" string to every property ("Timeunit"); they only cost tokens. A
    # property *named* title maps to a dict, so it survives.
    if isinstance(node, dict):
        return {
            key: _without_titles(value)
            for key, value in node.items()
            if not (key == "title" and isinstance(value, str))
        }
    if isinstance(node, list):
        return [_without_titles(value) for value in node]
    return node
