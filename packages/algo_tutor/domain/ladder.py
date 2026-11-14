"""Training levels: one Elo-like rating per topic, replayed from history (SPEC §7).

Ported unchanged from BloomCode's `topics/training-levels.ts`. Levels are never
stored: every read replays all completed attempts, so an edit (a signal, a
primary-topic override) can never leave them stale.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from packages.algo_tutor.domain.constants import (
    FLOOR_LEVEL,
    K_FACTOR,
    START_LEVEL,
    TIME_BUDGET_SECONDS,
)
from packages.algo_tutor.domain.enums import (
    Difficulty,
    DifficultyFeel,
    Help,
    Outcome,
    Result,
)
from packages.algo_tutor.domain.ratings import Rating, js_round

_STEPS = (Result.STRUGGLED, Result.OK, Result.STRONG)
_SCORE = {Result.STRUGGLED: 0.0, Result.OK: 0.5, Result.STRONG: 1.0}


def on_time(active_seconds: int | None, label: Difficulty | None) -> bool:
    """No recorded time (none or 0) counts as on time; else within the label's budget."""
    return not active_seconds or active_seconds <= TIME_BUDGET_SECONDS[label]


def classify(
    outcome: Outcome,
    help: Help,
    active_seconds: int | None,
    confidence: float | None,
    label: Difficulty | None,
    accepted_first_try: bool | None = None,
    feel: DifficultyFeel | None = None,
) -> Result:
    """Strong, OK or Struggled (SPEC §7.2).

    Struggled: not solved, major help or the solution, or confidence 1–2.
    Strong: solved alone, on time, not "no" to first-try acceptance,
    confidence unset or 4–5. OK otherwise. "Too easy" / "too hard" then
    moves the result one step, clamped.
    """
    struggled = (
        outcome is not Outcome.SOLVED
        or help in (Help.MAJOR, Help.SOLUTION)
        or (confidence is not None and confidence <= 2)
    )
    strong = (
        not struggled
        and help is Help.NONE
        and on_time(active_seconds, label)
        and accepted_first_try is not False
        and (confidence is None or confidence >= 4)
    )
    step = 0 if struggled else 2 if strong else 1
    if feel is DifficultyFeel.TOO_EASY:
        step += 1
    elif feel is DifficultyFeel.TOO_HARD:
        step -= 1
    return _STEPS[min(2, max(0, step))]


def result_score(result: Result) -> float:
    """Return the score that *result* counts as in a level update."""
    return _SCORE[result]


def expected_score(level: float, rating: float) -> float:
    """Return the Elo expected score at *level* on a problem rated *rating*."""
    return 1 / (1 + 10 ** ((rating - level) / 400))


@dataclass(frozen=True)
class LadderAttempt:
    """One completed attempt, with what the ladder needs from its problem.

    Pass them in replay order: `finished_at`, then insertion order. Attempts
    whose problem has no primary topic or no rating (every AtCoder attempt)
    are skipped.
    """

    attempt_id: str
    finished_at: datetime
    problem_title: str
    topic_id: str | None
    rating: Rating | None
    label: Difficulty | None
    outcome: Outcome
    help: Help
    active_seconds: int | None
    confidence: float | None
    accepted_first_try: bool | None = None
    feel: DifficultyFeel | None = None

    @property
    def result(self) -> Result:
        """How this attempt counts on the ladder."""
        return classify(
            self.outcome,
            self.help,
            self.active_seconds,
            self.confidence,
            self.label,
            self.accepted_first_try,
            self.feel,
        )


@dataclass(frozen=True)
class LevelChange:
    """The last move of a topic's level, e.g. `+12 after Two Sum (≈1732)`."""

    delta: int  # rounded
    attempt_id: str
    problem_title: str
    rating: int
    estimated: bool
    result: Result
    date: datetime


@dataclass(frozen=True)
class TopicLevel:
    """The learner's ladder level in one topic."""

    topic_id: str
    level: int  # rounded
    at_target: bool  # rounded level >= target: only review checks, no new practice
    attempts: int
    last_change: LevelChange | None


def replay(attempts: Iterable[LadderAttempt]) -> list[LadderAttempt]:
    """The attempts that count, in replay order (stable on insertion order)."""
    counted = [a for a in attempts if a.topic_id is not None and a.rating is not None]
    return sorted(counted, key=lambda a: a.finished_at)


def training_levels(
    attempts: Iterable[LadderAttempt],
    topic_ids: Sequence[str],
    target: int,
) -> list[TopicLevel]:
    """Each topic's level, in the order of `topic_ids` (SPEC §7.1, §7.3).

    START 1300, K 32, floor 1000; retries count every time; no decay.
    """
    history = replay(attempts)
    levels: list[TopicLevel] = []
    for topic_id in topic_ids:
        level = float(START_LEVEL)
        last: LevelChange | None = None
        mine = [a for a in history if a.topic_id == topic_id]
        for a in mine:
            assert a.rating is not None  # replay() keeps rated attempts only
            result = a.result
            delta = K_FACTOR * (
                result_score(result) - expected_score(level, a.rating.value)
            )
            level = max(FLOOR_LEVEL, level + delta)
            last = LevelChange(
                delta=js_round(delta),
                attempt_id=a.attempt_id,
                problem_title=a.problem_title,
                rating=a.rating.value,
                estimated=a.rating.estimated,
                result=result,
                date=a.finished_at,
            )
        rounded = js_round(level)
        levels.append(
            TopicLevel(
                topic_id=topic_id,
                level=rounded,
                at_target=rounded >= target,
                attempts=len(mine),
                last_change=last,
            )
        )
    return levels
