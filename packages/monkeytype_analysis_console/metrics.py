"""The console's definitions for one result (SPEC.md §5), and number formatting.

Speeds are in the result's unit unless a name says wpm.
"""

import dataclasses
import itertools
import math
import re
from collections.abc import Iterable, Sequence

from packages.monkeytype_analysis_console.results import (
    Result,
    Word,
)
from packages.monkeytype_analysis_console.typos import (
    shift_presses,
    symbols,
)

# Fewer keypresses than 5 standard words: nothing to analyse.
ABORTED_MIN_KEYPRESSES = 25
AFK_FLAG_PERCENT = 2.0
DEFAULT_GOAL = 96.0

# yr's prompt starts at this threshold when no word has a speed.
_FALLBACK_THRESHOLD = 80.0
_MARGIN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


@dataclasses.dataclass(frozen=True)
class WordGroup:
    """A group of words for one table row, and its means.

    A mean is None when no word in the group has the value; speeds count only
    words with a finite speed.
    """

    label: str
    words: int
    mean_speed: float | None
    mean_length: float | None
    mean_shift_presses: float | None
    mean_symbols: float | None
    mistyped: int


def finite_speed(word: Word) -> float | None:
    """The word's speed, or None when it is missing or too fast to measure."""
    if word.wpm is None or not math.isfinite(word.wpm):
        return None
    return word.wpm


def is_slow(word: Word, threshold: float) -> bool:
    """Whether the word's speed is below the threshold. `inf` is never slow."""
    speed = finite_speed(word)
    return speed is not None and speed < threshold


def slow_words(words: Iterable[Word], threshold: float) -> list[Word]:
    """The slow words, in typed order."""
    return [word for word in words if is_slow(word, threshold)]


def default_threshold(result: Result) -> float:
    """The threshold the slider starts at.

    It is the result's `wpm_threshold`. Without one, it is what `yr`'s prompt
    offers: the mean positive word speed, rounded half up.
    """
    if result.wpm_threshold is not None:
        return result.wpm_threshold
    speeds = [
        speed
        for speed in (finite_speed(word) for word in result.words)
        if speed is not None and speed > 0
    ]
    if not speeds:
        return _FALLBACK_THRESHOLD
    return float(math.floor(sum(speeds) / len(speeds) + 0.5))


def fastest_speed(words: Iterable[Word]) -> float | None:
    """The highest finite word speed, or None."""
    speeds = [speed for speed in map(finite_speed, words) if speed is not None]
    return max(speeds, default=None)


def band_labels(steps: Sequence[float]) -> tuple[str, ...]:
    """The label of each heatmap band, as Monkeytype shows it.

    Steps [0, 37, 70, 92, 127] give "<37", "37-69", "70-91", "92-126" and
    "127+". A band whose edges are equal is empty, and its label is the edge.
    With speeds that are not whole numbers, a middle band reads "low-high",
    with `high` itself in the next band.
    """
    if len(steps) < 2:
        return tuple("all" for _ in steps)
    whole = all(float(step).is_integer() for step in steps)
    labels = [f"<{format_number(steps[1])}"]
    for low, next_low in itertools.pairwise(steps[1:]):
        high = next_low - 1 if whole else next_low
        if high <= low:
            labels.append(format_number(low))
        else:
            labels.append(f"{format_number(low)}-{format_number(high)}")
    labels.append(f"{format_number(steps[-1])}+")
    return tuple(labels)


def previous_pb(result: Result) -> float | None:
    """The PB this result beat, in wpm, or None when it can't be known.

    `crown.text` holds the margin over the previous PB, such as "+2.04". The
    YAML doesn't say which unit the margin uses, so only wpm results have one.
    """
    if not result.pb or result.unit != "wpm" or result.crown is None:
        return None
    margin = result.crown.text.strip()
    if not _MARGIN.match(margin):
        return None
    return result.wpm - float(margin)


def too_fast_count(words: Iterable[Word]) -> int:
    """Words that were too fast to measure (`inf` speed)."""
    return sum(1 for word in words if word.wpm is not None and math.isinf(word.wpm))


def is_mistyped(word: Word) -> bool:
    """Whether the word had a wrong keypress: `yr`'s rule for `missed_word_list`."""
    return (
        word.typed is not None
        or word.marks is not None
        or word.error
        or word.extra_fixed
    )


def keypresses(result: Result) -> int | None:
    """Keys pressed, from `keys`, else from `chars`; None without either."""
    if result.keys is not None:
        return result.keys.correct + result.keys.incorrect
    if result.chars is not None:
        chars = result.chars
        return chars.correct + chars.incorrect + chars.extra
    return None


def is_aborted(result: Result) -> bool:
    """Whether the test ended before there was anything to analyse."""
    count = keypresses(result)
    too_short = any("too short" in flag for flag in result.flags)
    return (count is not None and count < ABORTED_MIN_KEYPRESSES) or too_short


def has_afk_flag(result: Result) -> bool:
    """Whether more than `AFK_FLAG_PERCENT` of the test was AFK."""
    return result.afk_pct is not None and result.afk_pct > AFK_FLAG_PERCENT


def goal_met(result: Result, goal: float) -> bool | None:
    """Whether `acc` reached the goal; None without an accuracy."""
    return None if result.acc is None else result.acc >= goal


def time_lost(result: Result) -> float | None:
    """Seconds lost to mistakes: each wrong key and its backspace at raw speed.

    A lower bound, because pauses after a mistake don't count. It is at most
    the test time, and None without `keys` or with a raw speed of 0.
    """
    if result.keys is None or not result.raw:
        return None
    lost = result.keys.incorrect * 2 * 60 / (result.raw * 5)
    return min(lost, result.time) if result.time else lost


def chars_left_wrong(result: Result) -> int | None:
    """Characters still wrong in the final text, or None without `chars`."""
    if result.chars is None:
        return None
    return result.chars.incorrect + result.chars.extra + result.chars.missed


def flags(result: Result) -> list[str]:
    """Monkeytype's flags, then the AFK and aborted flags of SPEC.md §5."""
    found = list(result.flags)
    if has_afk_flag(result):
        found.append(f"AFK {format_number(result.afk_pct)}%")
    if is_aborted(result):
        found.append("aborted")
    return found


def describe(label: str, words: Sequence[Word]) -> WordGroup:
    """The table row of a group of words."""
    speeds = [speed for speed in map(finite_speed, words) if speed is not None]
    return WordGroup(
        label=label,
        words=len(words),
        mean_speed=_mean(speeds),
        mean_length=_mean([len(word.word) for word in words]),
        mean_shift_presses=_mean([shift_presses(word.word) for word in words]),
        mean_symbols=_mean([symbols(word.word) for word in words]),
        mistyped=sum(1 for word in words if is_mistyped(word)),
    )


def band_groups(result: Result) -> list[WordGroup]:
    """One row per heatmap band, by its label, then one for all words."""
    rows = [
        describe(label, [word for word in result.words if word.bucket == band])
        for band, label in enumerate(band_labels(result.steps))
    ]
    return [*rows, describe("all", result.words)]


def thirds(words: Sequence[Word]) -> list[tuple[str, Sequence[Word]]]:
    """The first, middle and last third of the words; one group under 3 words.

    The first and last thirds hold `len(words) // 3` words each.
    """
    third = len(words) // 3
    if not third:
        return [("all", words)]
    return [
        ("first", words[:third]),
        ("middle", words[third : len(words) - third]),
        ("last", words[len(words) - third :]),
    ]


def position_groups(words: Sequence[Word]) -> list[WordGroup]:
    """The table rows of `thirds`."""
    return [describe(label, group) for label, group in thirds(words)]


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def format_number(value: float | None, digits: int = 2) -> str:
    """A number for display: at most `digits` decimals, "∞" or "–"."""
    if value is None:
        return "–"
    if math.isinf(value):
        return "∞"
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
