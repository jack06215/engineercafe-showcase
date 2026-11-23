"""The console's definitions over many results (SPEC.md §5, §6.4).

Speeds are never compared across word lists or test types: a trend group holds
the results of one word list and one test type. Aborted results are left out
of everything here.

    groups = trend_groups(results)
    recurring = recurring_problems(results)
"""

import collections
import dataclasses
import statistics
from collections.abc import Iterable, Sequence

from packages.monkeytype_analysis_console.metrics import (
    default_threshold,
    is_aborted,
    is_mistyped,
    is_slow,
)
from packages.monkeytype_analysis_console.results import (
    Result,
)
from packages.monkeytype_analysis_console.typos import (
    classify_words,
    key_confusions,
)

# The latest result is compared with the mean of up to this many before it.
TREND_WINDOW = 10
# Recurring problems look at this many of the latest results.
RECURRING_WINDOW = 20
RECURRING_LIMIT = 20
# A word or confusion recurs when it shows up in at least this many results.
RECURRING_MIN = 2
TREND_FIELDS = ("wpm", "acc", "consistency")


@dataclasses.dataclass(frozen=True)
class Trend:
    """The results of one word list and one test type, oldest first.

    Attributes:
        latest: The newest result.
        earlier: Up to `TREND_WINDOW` results before it, oldest first.
    """

    word_list: str
    test: str
    results: tuple[Result, ...]

    @property
    def latest(self) -> Result:
        """The newest result of the group."""
        return self.results[-1]

    @property
    def earlier(self) -> tuple[Result, ...]:
        """Up to `TREND_WINDOW` results before the latest, oldest first."""
        return self.results[-1 - TREND_WINDOW : -1]

    def change(self, field: str) -> float | None:
        """The latest value of `field` minus the mean of the earlier ones.

        None without earlier results, or when no result has the value.
        """
        latest = getattr(self.latest, field)
        earlier = [
            value
            for value in (getattr(result, field) for result in self.earlier)
            if value is not None
        ]
        if latest is None or not earlier:
            return None
        return float(latest - statistics.fmean(earlier))


@dataclasses.dataclass(frozen=True)
class Recurring:
    """A word that was slow or mistyped in more than one result.

    Attributes:
        results: Results it was slow or mistyped in.
        slow: Results it was slow in, by each result's own `wpm_threshold`.
        mistyped: Results it was mistyped in.
    """

    word: str
    results: int
    slow: int
    mistyped: int


def counted(results: Iterable[Result]) -> list[Result]:
    """The results that are not aborted, oldest first."""
    return sorted(
        (result for result in results if not is_aborted(result)),
        key=lambda result: result.copied_at,
    )


def common_tests(results: Iterable[Result]) -> list[str]:
    """The test types of the counted results, the most common first."""
    counts = collections.Counter(result.test for result in counted(results))
    return sorted(counts, key=lambda test: (-counts[test], test))


def trend_groups(results: Iterable[Result]) -> list[Trend]:
    """One group per word list and test type, sorted by word list, then test."""
    groups: dict[tuple[str, str], list[Result]] = {}
    for result in counted(results):
        groups.setdefault((result.word_list_name, result.test), []).append(result)
    return [
        Trend(word_list, test, tuple(group))
        for (word_list, test), group in sorted(groups.items())
    ]


def latest_results(
    results: Iterable[Result], window: int = RECURRING_WINDOW
) -> list[Result]:
    """The newest `window` counted results, oldest first."""
    return counted(results)[-window:]


def recurring_problems(
    results: Iterable[Result],
    window: int = RECURRING_WINDOW,
    limit: int = RECURRING_LIMIT,
) -> list[Recurring]:
    """Words slow or mistyped in at least 2 of the newest `window` results.

    Sorted by the number of results, then by word, and at most `limit` long.
    """
    slow: collections.Counter[str] = collections.Counter()
    mistyped: collections.Counter[str] = collections.Counter()
    either: collections.Counter[str] = collections.Counter()
    for result in latest_results(results, window):
        threshold = default_threshold(result)
        slow_here = {w.word for w in result.words if is_slow(w, threshold)}
        mistyped_here = {w.word for w in result.words if is_mistyped(w)}
        slow.update(slow_here)
        mistyped.update(mistyped_here)
        either.update(slow_here | mistyped_here)
    recurring = sorted(
        (word for word, count in either.items() if count >= RECURRING_MIN),
        key=lambda word: (-either[word], word),
    )
    return [
        Recurring(word, either[word], slow[word], mistyped[word])
        for word in recurring[:limit]
    ]


def repeated_confusions(
    results: Iterable[Result], window: int = RECURRING_WINDOW
) -> list[tuple[str, int]]:
    """Key confusions seen at least twice in the newest `window` results."""
    counts: collections.Counter[str] = collections.Counter()
    for result in latest_results(results, window):
        counts.update(key_confusions(classify_words(result.words)))
    return [(pair, n) for pair, n in counts.most_common() if n >= RECURRING_MIN]


def by_word_list(results: Sequence[Result]) -> dict[str, list[Result]]:
    """The results of each word list, oldest first, word lists in name order."""
    groups: dict[str, list[Result]] = {}
    for result in counted(results):
        groups.setdefault(result.word_list_name, []).append(result)
    return dict(sorted(groups.items()))
