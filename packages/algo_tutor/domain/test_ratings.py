import unittest

from packages.algo_tutor.domain.enums import Difficulty, Source
from packages.algo_tutor.domain.ratings import Rating, js_round, problem_rating


class ProblemRatingTest(unittest.TestCase):
    def test_exact_rating_wins_and_is_rounded(self) -> None:
        self.assertEqual(
            problem_rating(
                Source.LEETCODE, Difficulty.MEDIUM, exact=1765.5, estimate=1500.0
            ),
            Rating(1766, estimated=False),
        )

    def test_estimate_before_label_median(self) -> None:
        self.assertEqual(
            problem_rating(Source.LEETCODE, Difficulty.MEDIUM, estimate=1700.4),
            Rating(1700, estimated=True),
        )

    def test_label_medians(self) -> None:
        self.assertEqual(
            problem_rating(Source.LEETCODE, Difficulty.EASY), Rating(1252, True)
        )
        self.assertEqual(
            problem_rating(Source.LEETCODE, Difficulty.MEDIUM), Rating(1648, True)
        )
        self.assertEqual(
            problem_rating(Source.LEETCODE, Difficulty.HARD), Rating(2262, True)
        )

    def test_unrated(self) -> None:
        self.assertIsNone(problem_rating(Source.LEETCODE, None))

    def test_atcoder_is_never_rated(self) -> None:
        self.assertIsNone(problem_rating(Source.ATCODER, Difficulty.EASY, exact=1500.0))

    def test_js_round_is_half_up(self) -> None:
        self.assertEqual(
            [js_round(x) for x in (0.5, 1.5, 2.5, -0.5, -2.5, -2.6)],
            [1, 2, 3, 0, -2, -3],
        )


if __name__ == "__main__":
    unittest.main()
