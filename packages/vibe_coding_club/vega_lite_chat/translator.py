"""The repair loop: call the model, check the reply against the profile, and send errors back to fix.

Only the model's own mistakes are repaired: a reply that doesn't parse, or a chart that fails
`check_chart`. `OllamaUnavailable` passes straight through and is not counted as an attempt.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage

from packages.vibe_coding_club.vega_lite_chat.chart_spec import (
    AssistantTurn,
)
from packages.vibe_coding_club.vega_lite_chat.checks import check_chart
from packages.vibe_coding_club.vega_lite_chat.llm import (
    RawReply,
    StructuredModel,
)
from packages.vibe_coding_club.vega_lite_chat.profile import DataProfile
from packages.vibe_coding_club.vega_lite_chat.prompts import (
    repair_message,
)


@dataclass(frozen=True)
class Attempt:
    raw: str
    errors: tuple[str, ...]  # empty when the reply passed


@dataclass(frozen=True)
class Translation:
    turn: AssistantTurn | None  # None when every attempt failed
    attempts: tuple[Attempt, ...]


def translate(
    model: StructuredModel,
    messages: Sequence[BaseMessage],
    profile: DataProfile,
    *,
    max_calls: int,
    on_attempt: Callable[[int, Sequence[str]], None],
) -> Translation:
    """Call `model` up to `max_calls` times until a reply passes.

    `on_attempt(number, errors)` runs before each call, with the 1-based attempt number and the
    previous attempt's errors (empty before the first), so the UI can say what is being fixed.
    """
    conversation = list(messages)
    attempts: list[Attempt] = []
    errors: tuple[str, ...] = ()
    for number in range(1, max_calls + 1):
        on_attempt(number, errors)
        reply = model(conversation)
        errors = _errors(reply, profile)
        attempts.append(Attempt(raw=reply.text, errors=errors))
        if not errors:
            return Translation(turn=reply.turn, attempts=tuple(attempts))
        # The model sees its own reply and what was wrong with it.
        conversation += [AIMessage(content=reply.text), repair_message(errors)]
    return Translation(turn=None, attempts=tuple(attempts))


def _errors(reply: RawReply, profile: DataProfile) -> tuple[str, ...]:
    if reply.turn is None:
        return (f"the reply does not match the JSON schema: {reply.parse_error}",)
    if reply.turn.chart is None:  # a clarifying question or an answer; nothing to check
        return ()
    return tuple(check_chart(reply.turn.chart, profile))
