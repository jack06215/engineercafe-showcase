"""Ported from BloomCode's tests/server/rating-model.test.ts, same numbers."""

import math
import unittest

from packages.algo_tutor.catalogue.manifests import PINNED_SHA256, ZEROTRAC_FILE
from packages.algo_tutor.catalogue.rating_model import (
    ProblemFeatures,
    RatedFeatures,
    TooFewRatedProblemsError,
    fit_rating_model,
)
from packages.algo_tutor.catalogue.testing import manifests
from packages.algo_tutor.domain.enums import Difficulty

LABELS = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)


def truth(p: ProblemFeatures) -> float:
    """Known generating rule: a label base, lower acceptance is harder, Graph adds 120."""
    rate = p.ac_rate / 100
    return (
        [1200, 1600, 2100][LABELS.index(p.difficulty)]
        - 80 * math.log(rate / (1 - rate))
        + (120 if "Graph" in p.tags else 0)
    )


def rows() -> list[RatedFeatures]:
    out = []
    for i in range(300):
        p = ProblemFeatures(
            LABELS[i % 3], 20 + (i * 37) % 60, ("Graph",) if i % 4 == 0 else ("Array",)
        )
        out.append(RatedFeatures(p.difficulty, p.ac_rate, p.tags, rating=truth(p)))
    return out


class RatingModelTest(unittest.TestCase):
    def test_recovers_a_known_rule_and_reports_error_on_held_out_rows_only(
        self,
    ) -> None:
        model = fit_rating_model(rows())
        probe = ProblemFeatures(Difficulty.MEDIUM, 45, ("Graph",))
        self.assertLess(abs(model.predict(probe) - truth(probe)), 15)
        self.assertLess(model.held_out_error, 15)
        self.assertEqual(model.method, f"ridge-v1 mae={model.held_out_error}")

        # Noise the fit cannot learn shows up as held-out error, not as a perfect score.
        noisy = [
            RatedFeatures(
                r.difficulty,
                r.ac_rate,
                r.tags,
                r.rating + (200 if (i * 7919) % 13 < 6 else -200),
            )
            for i, r in enumerate(rows())
        ]
        self.assertGreater(fit_rating_model(noisy).held_out_error, 120)

    def test_needs_fifty_rows(self) -> None:
        with self.assertRaises(TooFewRatedProblemsError):
            fit_rating_model(rows()[:49])

    def test_the_bundled_contest_ratings_match_their_pinned_checksum(self) -> None:
        self.assertEqual(len(PINNED_SHA256[ZEROTRAC_FILE]), 64)
        ratings = manifests().exact_ratings
        self.assertGreater(len(ratings), 2500)
        self.assertEqual(ratings["koko-eating-bananas"].rating, 1766)


if __name__ == "__main__":
    unittest.main()
