"""Ported from BloomCode's tests/server/training-levels.test.ts (expected numbers unchanged).

Upstream drives the server; these call the rules directly. Its shortlist
case lives in test_plan.py.
"""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from packages.algo_tutor.domain.enums import (
    Difficulty,
    DifficultyFeel,
    Help,
    Outcome,
    Result,
)
from packages.algo_tutor.domain.ladder import (
    LadderAttempt,
    classify,
    expected_score,
    training_levels,
)
from packages.algo_tutor.domain.ratings import Rating, js_round

M = Difficulty.MEDIUM


def result(
    label: Difficulty | None = M,
    *,
    outcome: Outcome = Outcome.SOLVED,
    help: Help = Help.NONE,
    active_seconds: int | None = 600,
    confidence: float | None = 4.0,
    accepted_first_try: bool | None = None,
    feel: DifficultyFeel | None = None,
) -> Result:
    """Upstream's `solved` fixture, with changes."""
    return classify(
        outcome, help, active_seconds, confidence, label, accepted_first_try, feel
    )


class ClassifyTest(unittest.TestCase):
    """'each attempt is Strong, OK or Struggled; feedback moves it one step'"""

    def test_strong(self) -> None:
        self.assertIs(result(), Result.STRONG)
        # Unanswered questions don't count against you.
        self.assertIs(result(active_seconds=None, confidence=None), Result.STRONG)

    def test_any_shortfall_is_ok(self) -> None:
        self.assertIs(result(help=Help.SMALL), Result.OK)
        self.assertIs(result(active_seconds=30 * 60), Result.OK)
        self.assertIs(result(Difficulty.HARD, active_seconds=30 * 60), Result.STRONG)
        self.assertIs(result(accepted_first_try=False), Result.OK)
        self.assertIs(result(confidence=3.0), Result.OK)

    def test_struggled(self) -> None:
        self.assertIs(result(outcome=Outcome.NOT_SOLVED), Result.STRUGGLED)
        self.assertIs(result(help=Help.MAJOR), Result.STRUGGLED)
        self.assertIs(result(confidence=2.0), Result.STRUGGLED)

    def test_feedback_is_one_step(self) -> None:
        self.assertIs(result(feel=DifficultyFeel.TOO_HARD), Result.OK)
        self.assertIs(
            result(help=Help.SMALL, feel=DifficultyFeel.TOO_EASY), Result.STRONG
        )
        self.assertIs(
            result(outcome=Outcome.NOT_SOLVED, feel=DifficultyFeel.TOO_EASY), Result.OK
        )

    def test_budgets_by_label(self) -> None:
        # Easy 15, Medium 25, Hard 40, no label 25 minutes.
        self.assertIs(result(Difficulty.EASY, active_seconds=15 * 60), Result.STRONG)
        self.assertIs(result(Difficulty.EASY, active_seconds=15 * 60 + 1), Result.OK)
        self.assertIs(result(None, active_seconds=25 * 60), Result.STRONG)
        self.assertIs(result(None, active_seconds=25 * 60 + 1), Result.OK)
        self.assertIs(result(active_seconds=0), Result.STRONG)


class EloTest(unittest.TestCase):
    """'Elo moves little on misses far above the level and more on misses at or below it'"""

    def test_deltas(self) -> None:
        def delta(level: int, rating: int, score: float) -> int:
            return js_round(32 * (score - expected_score(level, rating)))

        self.assertEqual(delta(1600, 2097, 0), -2)
        self.assertEqual(delta(1600, 1600, 0), -16)
        self.assertEqual(delta(1600, 1450, 0), -23)
        self.assertEqual(delta(1600, 1600, 1), 16)
        self.assertEqual(delta(1600, 1600, 0.5), 0)


T0 = datetime(2026, 10, 1, 9, tzinfo=UTC)


def attempt(
    n: int,
    title: str,
    rating: Rating | None,
    label: Difficulty,
    topic: str | None = "binary-search",
) -> LadderAttempt:
    """A solo solve in 5 minutes, finished n minutes after T0."""
    return LadderAttempt(
        attempt_id=f"a{n}",
        finished_at=T0 + timedelta(minutes=n),
        problem_title=title,
        topic_id=topic,
        rating=rating,
        label=label,
        outcome=Outcome.SOLVED,
        help=Help.NONE,
        active_seconds=300,
        confidence=None,
    )


TOPICS = ["binary-search", "graph"]


class TrainingLevelsTest(unittest.TestCase):
    """'a struggle lowers only that topic and feedback adjusts the result'

    Upstream's topics are NeetCode's "Binary Search" and "Graphs"; here
    `binary-search` and `graph`.
    """

    def test_struggle_then_strong_then_signals(self) -> None:
        self.assertEqual(training_levels([], TOPICS, 1850)[0].level, 1300)
        # koko-eating-bananas: exact contest rating 1,766.
        koko = replace(
            attempt(1, "koko-eating-bananas", Rating(1766, False), M),
            outcome=Outcome.NOT_SOLVED,
            help=Help.MAJOR,
            active_seconds=1800,
        )
        after = training_levels([koko], TOPICS, 1850)
        # Expected only ~6% at 1,300 against 1,766, so a miss barely moves the level.
        self.assertEqual(after[0].level, 1298)
        last = after[0].last_change
        assert last is not None
        self.assertEqual(
            (last.problem_title, last.rating, last.result),
            ("koko-eating-bananas", 1766, Result.STRUGGLED),
        )
        self.assertFalse(last.estimated)
        self.assertEqual(after[1].level, 1300)

        easy = replace(
            attempt(2, "binary-search", Rating(1252, True), Difficulty.EASY),
            confidence=5.0,
        )
        strong = training_levels([koko, easy], TOPICS, 1850)[0]
        assert strong.last_change is not None
        self.assertIs(strong.last_change.result, Result.STRONG)
        # Not first try (OK) and "too hard" (one step down): now Struggled.
        signalled = replace(
            easy, accepted_first_try=False, feel=DifficultyFeel.TOO_HARD
        )
        lowered = training_levels([koko, signalled], TOPICS, 1850)[0]
        assert lowered.last_change is not None
        self.assertIs(lowered.last_change.result, Result.STRUGGLED)
        self.assertLess(lowered.level, strong.level)

    def test_replay_order_and_floor(self) -> None:
        # Out-of-order input replays by finished_at; the level never drops below 1000.
        misses = [
            replace(
                attempt(n, f"p{n}", Rating(1000, True), Difficulty.EASY),
                outcome=Outcome.NOT_SOLVED,
            )
            for n in range(40, 0, -1)
        ]
        lv = training_levels(misses, TOPICS, 1850)[0]
        self.assertEqual(lv.level, 1000)
        self.assertEqual(lv.attempts, 40)
        assert lv.last_change is not None
        self.assertEqual(lv.last_change.attempt_id, "a40")

    def test_unrated_or_untopiced_attempts_are_ignored(self) -> None:
        ignored = [
            attempt(1, "x", Rating(1500, True), M, topic=None),
            attempt(2, "y", None, M),
        ]
        lv = training_levels(ignored, TOPICS, 1850)[0]
        self.assertEqual((lv.level, lv.attempts, lv.last_change), (1300, 0, None))

    def test_at_target_uses_the_rounded_level(self) -> None:
        self.assertTrue(training_levels([], TOPICS, 1300)[0].at_target)
        self.assertFalse(training_levels([], TOPICS, 1350)[0].at_target)


if __name__ == "__main__":
    unittest.main()
