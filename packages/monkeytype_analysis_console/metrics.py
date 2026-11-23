"""The console's definitions for one result (SPEC.md §5), and number formatting.

Speeds are in the result's unit unless a name says wpm.
"""

import itertools
import math
import re
from collections.abc import Iterable, Sequence

from packages.monkeytype_analysis_console.results import (
    Result,
    Word,
)

# yr's prompt starts at this threshold when no word has a speed.
_FALLBACK_THRESHOLD = 80.0
_MARGIN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


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


def format_number(value: float | None, digits: int = 2) -> str:
    """A number for display: at most `digits` decimals, "∞" or "–"."""
    if value is None:
        return "–"
    if math.isinf(value):
        return "∞"
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
