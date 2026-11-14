"""The state of one chat: the table it is about, its turns, and which turn holds the current chart.

A turn is either a `Turn` (vega_lite_tool drew, asked back or failed) or an `Answer` (the chat
model replied in prose).

No Streamlit here; ui.py keeps a single `ChatSession` in `st.session_state` and draws it.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas

from packages.vibe_coding_club.vega_lite_chat.chart_spec import (
    AssistantTurn,
    ChartSpec,
)
from packages.vibe_coding_club.vega_lite_chat.profile import DataProfile
from packages.vibe_coding_club.vega_lite_chat.translator import Attempt


@dataclass(frozen=True)
class Turn:
    """One chart request and how the translator handled it."""

    request: str  # what the user typed; the first chart's is first_chart_request
    auto: bool  # the automatic first chart: shown as such, never a "recent request"
    reply: AssistantTurn | None  # None when every attempt in the repair loop failed
    vega_lite: dict[str, Any] | None  # reply.chart compiled
    attempts: tuple[Attempt, ...]
    error: str | None = None  # shown to the user, e.g. a compiler bug
    # What the chat model passed to vega_lite_tool. It may reword the request (「売上がいちばん多い地域は？」
    # → a bar chart of sales by region); None when drawn without the chat model.
    tool_request: str | None = None

    @property
    def translator_request(self) -> str:
        """The request the translator answered."""
        return self.request if self.tool_request is None else self.tool_request

    @property
    def chart(self) -> ChartSpec | None:
        """The chart of the reply, if there is one."""
        return self.reply.chart if self.reply is not None else None

    @property
    def has_chart(self) -> bool:
        """Whether this turn drew something: a chart that compiled without error."""
        return (
            self.chart is not None and self.vega_lite is not None and self.error is None
        )


@dataclass(frozen=True)
class Answer:
    """A reply in prose: the request wasn't for a chart, so vega_lite_tool wasn't called."""

    request: str
    text: str


@dataclass
class ChatSession:
    """The loaded data and the conversation about it."""

    source_name: str
    df: pandas.DataFrame
    profile: DataProfile
    credit: str | None = None  # a sample's data credit, e.g. 出典: 気象庁
    turns: list[Turn | Answer] = field(default_factory=list)
    current: int | None = None  # index of the turn holding the current chart

    def current_chart(self) -> ChartSpec | None:
        """The chart the user sees now, if any."""
        if self.current is None:
            return None
        turn = self.turns[self.current]
        return turn.chart if isinstance(turn, Turn) else None

    def recent_requests(self, n: int) -> list[str]:
        """The translator's last `n` requests, oldest first. Answers and the automatic first request never count."""
        if n <= 0:
            return []
        asked = [
            turn.translator_request
            for turn in self.turns
            if isinstance(turn, Turn) and not turn.auto
        ]
        return asked[-n:]

    def add_turn(self, turn: Turn | Answer) -> None:
        """Append `turn`; if it drew a chart, that chart becomes the current one."""
        self.turns.append(turn)
        if isinstance(turn, Turn) and turn.has_chart:
            self.current = len(self.turns) - 1

    def continue_from(self, index: int) -> None:
        """Make an earlier turn's chart current (「ここから続ける」)."""
        if not 0 <= index < len(self.turns):
            raise IndexError(f"no turn {index}; there are {len(self.turns)}")
        turn = self.turns[index]
        if not isinstance(turn, Turn) or not turn.has_chart:
            raise ValueError(f"turn {index} has no chart to continue from")
        self.current = index
