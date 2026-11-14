"""A problem's difficulty on LeetCode's contest-rating scale (SPEC §5.5).

Ported from BloomCode's `topics/ratings.ts`. Pure: the caller looks up the
zerotrac rating and the fitted estimate for the problem and passes them in.
"""

import math
from dataclasses import dataclass

from packages.algo_tutor.domain.constants import LABEL_MEDIAN_RATING
from packages.algo_tutor.domain.enums import Difficulty, Source


@dataclass(frozen=True)
class Rating:
    """A problem rating, exact or estimated."""

    value: int
    estimated: bool  # shown with "≈" in the UI


def js_round(x: float) -> int:
    """Round half up, as JavaScript's Math.round does (Python's round is banker's).

    Used wherever upstream rounds, so ported expected numbers match exactly.
    """
    return math.floor(x + 0.5)


def problem_rating(
    source: Source,
    label: Difficulty | None,
    exact: float | None = None,
    estimate: float | None = None,
) -> Rating | None:
    """The first of: exact (zerotrac), fitted estimate, label median, none.

    AtCoder problems never have a rating (R2-Q4), so they are never planned
    or levelled.
    """
    if source is Source.ATCODER:
        return None
    if exact is not None:
        return Rating(js_round(exact), estimated=False)
    if estimate is not None:
        return Rating(js_round(estimate), estimated=True)
    if label is not None:
        return Rating(LABEL_MEDIAN_RATING[label], estimated=True)
    return None
