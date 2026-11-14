"""Contest-scale rating estimates for problems never in a contest (SPEC.md §5.5).

Ported from BloomCode's `src/integrations/rating-model.ts` (MIT): ridge
regression on the LeetCode label, label × logit(acceptance rate) and LeetCode
tags, trained on problems with exact contest ratings. On upstream's pinned
snapshot it orders problems 200+ points apart correctly ~93 % of the time
(mean error ~150).
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import Difficulty

LABELS = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)
# One-hot label and label × logit(acceptance) stay unpenalised.
_BASE = len(LABELS) * 2


@dataclass(frozen=True)
class ProblemFeatures:
    """The problem traits that the rating model reads."""

    difficulty: Difficulty
    ac_rate: float  # percent, 0–100
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RatedFeatures(ProblemFeatures):
    """Problem traits with a known rating, used for training."""

    rating: float


class TooFewRatedProblemsError(ValueError):
    """There are too few rated problems to fit the model."""


@dataclass(frozen=True)
class RatingModel:
    """A fitted rating predictor with its held-out error."""

    predict: Callable[[ProblemFeatures], float]
    held_out_error: int  # mean absolute error on held-out folds, never on training rows
    method: str  # e.g. "ridge-v1 mae=148"


def _vector(p: ProblemFeatures, tags: Sequence[str]) -> list[float]:
    label = [1.0 if label == p.difficulty else 0.0 for label in LABELS]
    low, high = constants.ACCEPTANCE_CLAMP
    rate = min(max(p.ac_rate, low), high) / 100
    logit = math.log(rate / (1 - rate))
    present = set(p.tags)
    return [
        *label,
        *(v * logit for v in label),
        *(1.0 if t in present else 0.0 for t in tags),
    ]


def _ridge(x: list[list[float]], y: list[float]) -> list[float]:
    """Solve (XᵀX + λI′) w = Xᵀy by Gaussian elimination with partial pivoting."""
    n = len(x[0])
    a = [[0.0] * (n + 1) for _ in range(n)]
    for i in range(_BASE, n):
        a[i][i] = constants.RIDGE_LAMBDA
    # Accumulate over rows once, skipping zero features (most tags are absent).
    for row, target in zip(x, y, strict=True):
        nz = [i for i, v in enumerate(row) if v]
        for i in nz:
            ai = a[i]
            for j in nz:
                ai[j] += row[i] * row[j]
            ai[n] += row[i] * target
    for c in range(n):
        pivot = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[pivot] = a[pivot], a[c]
        # An all-zero column (e.g. a label absent from training) contributes nothing.
        if abs(a[c][c]) < 1e-12:
            continue
        ac = a[c]
        for r in range(n):
            if r == c:
                continue
            ar = a[r]
            f = ar[c] / ac[c]
            if f == 0:
                continue
            for k in range(c, n + 1):
                ar[k] -= f * ac[k]
    return [0.0 if abs(row[i]) < 1e-12 else row[n] / row[i] for i, row in enumerate(a)]


def fit_rating_model(
    rows: Sequence[RatedFeatures], folds: int = constants.RIDGE_FOLDS
) -> RatingModel:
    """Fit on `rows`, reporting the held-out error of deterministic folds by position."""
    if len(rows) < folds * 10:
        raise TooFewRatedProblemsError(
            "Too few rated problems to fit the rating model."
        )
    tags = sorted({t for r in rows for t in r.tags})

    def fit(train: Sequence[RatedFeatures]) -> Callable[[ProblemFeatures], float]:
        w = _ridge([_vector(r, tags) for r in train], [r.rating for r in train])

        def predict(p: ProblemFeatures) -> float:
            return sum(v * wi for v, wi in zip(_vector(p, tags), w, strict=True))

        return predict

    error = 0.0
    for f in range(folds):
        predict = fit([r for i, r in enumerate(rows) if i % folds != f])
        error += sum(
            abs(predict(r) - r.rating) for i, r in enumerate(rows) if i % folds == f
        )
    # JavaScript's Math.round: halves go up.
    held_out = math.floor(error / len(rows) + 0.5)
    return RatingModel(
        predict=fit(rows), held_out_error=held_out, method=f"ridge-v1 mae={held_out}"
    )
