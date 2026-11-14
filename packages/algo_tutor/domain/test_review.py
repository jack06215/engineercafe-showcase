import unittest
from datetime import date

from packages.algo_tutor.domain.attempts import start_facts
from packages.algo_tutor.domain.enums import (
    Context,
    Evidence,
    Help,
    Outcome,
    PlanItemKind,
    ReviewAction,
    ReviewChoice,
    ReviewStage,
    Source,
)
from packages.algo_tutor.domain.review import (
    NO_REVIEW,
    RECOMMENDED,
    Choice,
    DueCandidate,
    ReviewDateRequired,
    ReviewTarget,
    due_checks,
    edit_target,
    is_waiting,
    recommendation,
    review_at_finish,
    snooze_target,
    update_target,
)

D = date(2026, 9, 16)
A = ReviewAction
S = ReviewStage


class RecommendationTest(unittest.TestCase):
    def test_intervals(self) -> None:
        cases = [
            (
                Outcome.NOT_SOLVED,
                Help.NONE,
                Evidence.UNSEEN,
                date(2026, 9, 17),
                S.REPAIR,
            ),
            (Outcome.STOPPED, Help.NONE, Evidence.UNSEEN, date(2026, 9, 17), S.REPAIR),
            (Outcome.SOLVED, Help.MAJOR, Evidence.UNSEEN, date(2026, 9, 17), S.REPAIR),
            (
                Outcome.SOLVED,
                Help.SOLUTION,
                Evidence.UNSEEN,
                date(2026, 9, 17),
                S.REPAIR,
            ),
            # "Leaving Help as Unknown schedules a repair tomorrow."
            (
                Outcome.SOLVED,
                Help.UNKNOWN,
                Evidence.UNSEEN,
                date(2026, 9, 17),
                S.REPAIR,
            ),
            (
                Outcome.SOLVED,
                Help.SMALL,
                Evidence.RETENTION,
                date(2026, 9, 19),
                S.RECONSTRUCTION,
            ),
            (
                Outcome.SOLVED,
                Help.NONE,
                Evidence.RETENTION,
                date(2026, 9, 23),
                S.TRANSFER,
            ),
            (
                Outcome.SOLVED,
                Help.NONE,
                Evidence.NEAR_TRANSFER,
                date(2026, 9, 30),
                S.MIXED,
            ),
            (Outcome.SOLVED, Help.NONE, Evidence.UNSEEN, date(2026, 9, 30), S.MIXED),
        ]
        for outcome, help, evidence, when, stage in cases:
            with self.subTest(outcome=outcome, help=help, evidence=evidence):
                r = recommendation(outcome, help, evidence, D)
                self.assertEqual((r.date, r.stage), (when, stage))

    def test_calendar_days_cross_months(self) -> None:
        self.assertEqual(
            recommendation(
                Outcome.SOLVED, Help.NONE, Evidence.UNSEEN, date(2026, 12, 25)
            ).date,
            date(2027, 1, 8),
        )


class UpdateTargetTest(unittest.TestCase):
    def test_new_target(self) -> None:
        t = update_target(None, "p", D, S.REPAIR)
        self.assertEqual(t, ReviewTarget("p", D, D, A.RECOMMENDED, S.REPAIR, 1))

    def test_recommended_choice_keeps_a_hand_set_date(self) -> None:
        manual = ReviewTarget("p", D, date(2026, 12, 1), A.MANUAL, S.MIXED, 3)
        t = update_target(manual, "p", date(2026, 9, 20), S.TRANSFER, RECOMMENDED)
        self.assertEqual(
            t,
            ReviewTarget(
                "p", date(2026, 9, 20), date(2026, 12, 1), A.MANUAL, S.TRANSFER, 4
            ),
        )

    def test_manual_and_none_choices(self) -> None:
        t = update_target(None, "p", D, S.MIXED, Choice(A.MANUAL, date(2026, 12, 1)))
        self.assertEqual(
            (t.action, t.effective_date, t.recommended_date),
            (A.MANUAL, date(2026, 12, 1), D),
        )
        t = update_target(t, "p", D, S.MIXED, NO_REVIEW)
        self.assertEqual((t.action, t.effective_date, t.version), (A.NONE, None, 2))

    def test_a_date_is_required(self) -> None:
        with self.assertRaises(ReviewDateRequired):
            update_target(None, "p", D, S.MIXED, Choice(A.MANUAL))
        with self.assertRaises(ReviewDateRequired):
            edit_target(update_target(None, "p", D, S.MIXED), A.SNOOZE)

    def test_from_finish_choice(self) -> None:
        self.assertEqual(Choice.from_finish(ReviewChoice.NONE), NO_REVIEW)
        self.assertEqual(
            Choice.from_finish(ReviewChoice.MANUAL, D), Choice(A.MANUAL, D)
        )

    def test_edit(self) -> None:
        t = update_target(None, "p", D, S.TRANSFER)
        snoozed = edit_target(t, A.SNOOZE, date(2026, 10, 1))
        self.assertEqual(
            (snoozed.action, snoozed.effective_date, snoozed.version),
            (A.SNOOZE, date(2026, 10, 1), 2),
        )
        back = edit_target(snoozed, A.RECOMMENDED)
        self.assertEqual(
            (back.action, back.effective_date, back.stage),
            (A.RECOMMENDED, D, S.TRANSFER),
        )
        self.assertIsNone(edit_target(back, A.NONE).effective_date)

    def test_snoozing_a_plan_item(self) -> None:
        t = snooze_target(None, "p", date(2026, 9, 20))
        self.assertEqual(
            t, ReviewTarget("p", None, date(2026, 9, 20), A.SNOOZE, S.SNOOZED, 1)
        )

    def test_waiting(self) -> None:
        self.assertFalse(is_waiting(None, D))
        self.assertTrue(is_waiting(snooze_target(None, "p", date(2026, 9, 20)), D))
        self.assertFalse(is_waiting(snooze_target(None, "p", D), D))
        self.assertTrue(
            is_waiting(update_target(None, "p", None, S.COVERED, NO_REVIEW), D)
        )


def finish(
    outcome: Outcome = Outcome.SOLVED,
    help: Help = Help.NONE,
    evidence: Evidence = Evidence.UNSEEN,
    *,
    choice: Choice = RECOMMENDED,
    own: ReviewTarget | None = None,
    review_of: str | None = None,
    idea: ReviewTarget | None = None,
    source: Source = Source.LEETCODE,
    day: date = D,
) -> tuple[ReviewTarget, ...]:
    return review_at_finish(
        problem_id="check" if review_of else "p",
        source=source,
        outcome=outcome,
        help=help,
        evidence=evidence,
        study_date=day,
        choice=choice,
        own_target=own,
        review_of=review_of,
        idea_target=idea,
    ).targets


class FinishingACheckTest(unittest.TestCase):
    def test_a_plain_finish_moves_its_own_target(self) -> None:
        r = review_at_finish(
            problem_id="p",
            source=Source.LEETCODE,
            outcome=Outcome.SOLVED,
            help=Help.SMALL,
            evidence=Evidence.NEAR_TRANSFER,
            study_date=D,
            choice=RECOMMENDED,
            own_target=None,
        )
        self.assertEqual(r.next_review, date(2026, 9, 19))
        self.assertEqual([t.problem_id for t in r.targets], ["p"])

    def test_the_idea_moves_on_and_the_check_is_covered(self) -> None:
        idea = update_target(None, "idea", date(2026, 9, 16), S.REPAIR)
        moved, covered = finish(
            evidence=Evidence.NEAR_TRANSFER, review_of="idea", idea=idea
        )
        self.assertEqual(
            (moved.problem_id, moved.stage, moved.effective_date),
            ("idea", S.MIXED, date(2026, 9, 30)),
        )
        self.assertEqual(moved.version, 2)
        self.assertEqual(
            (covered.problem_id, covered.stage, covered.action, covered.effective_date),
            ("check", S.COVERED, A.NONE, None),
        )

    def test_a_hand_set_date_that_came_due_goes_back_to_recommended(self) -> None:
        idea = ReviewTarget("idea", date(2026, 9, 1), D, A.MANUAL, S.RECONSTRUCTION, 2)
        moved, _ = finish(
            evidence=Evidence.UNSEEN, help=Help.SMALL, review_of="idea", idea=idea
        )
        self.assertEqual(
            (moved.action, moved.effective_date), (A.RECOMMENDED, date(2026, 9, 19))
        )

    def test_two_solo_solves_at_the_14_day_stage_retire_the_idea(self) -> None:
        idea = ReviewTarget("idea", D, D, A.RECOMMENDED, S.MIXED, 3)
        moved, _ = finish(review_of="idea", idea=idea)
        self.assertEqual(
            (moved.stage, moved.action, moved.effective_date, moved.recommended_date),
            (S.RETIRED, A.NONE, None, None),
        )

    def test_no_retirement_without_the_recommended_date(self) -> None:
        idea = ReviewTarget("idea", D, D, A.RECOMMENDED, S.MIXED, 3)
        moved, _ = finish(
            review_of="idea", idea=idea, choice=Choice(A.MANUAL, date(2026, 11, 1))
        )
        self.assertEqual(
            (moved.stage, moved.action, moved.effective_date),
            (S.MIXED, A.MANUAL, date(2026, 11, 1)),
        )

    def test_a_struggle_on_a_check_sends_the_idea_to_repair(self) -> None:
        idea = ReviewTarget("idea", D, D, A.RECOMMENDED, S.MIXED, 3)
        moved, _ = finish(Outcome.NOT_SOLVED, review_of="idea", idea=idea)
        self.assertEqual(
            (moved.stage, moved.effective_date), (S.REPAIR, date(2026, 9, 17))
        )


class AtCoderRetirementTest(unittest.TestCase):
    """SPEC §8.5: the same problem comes back; two consecutive solo solves at
    stage `transfer` retire it."""

    def solve(
        self,
        own: ReviewTarget | None,
        evidence: Evidence,
        help: Help = Help.NONE,
        choice: Choice = RECOMMENDED,
    ) -> ReviewTarget:
        (t,) = finish(
            help=help, evidence=evidence, own=own, source=Source.ATCODER, choice=choice
        )
        return t

    def test_first_solve_then_two_transfer_solves(self) -> None:
        first = self.solve(None, Evidence.NEAR_TRANSFER)
        self.assertEqual(
            (first.stage, first.solo_transfer_streak, first.effective_date),
            (S.MIXED, 0, date(2026, 9, 30)),
        )
        second = self.solve(first, Evidence.RETENTION)
        self.assertEqual(
            (second.stage, second.solo_transfer_streak, second.effective_date),
            (S.TRANSFER, 1, date(2026, 9, 23)),
        )
        third = self.solve(second, Evidence.RETENTION)
        self.assertEqual(
            (third.stage, third.action, third.effective_date), (S.RETIRED, A.NONE, None)
        )

    def test_anything_but_a_solo_solve_resets_the_streak(self) -> None:
        t = self.solve(None, Evidence.NEAR_TRANSFER)
        t = self.solve(t, Evidence.RETENTION)
        t = self.solve(t, Evidence.RETENTION, help=Help.SMALL)
        self.assertEqual((t.stage, t.solo_transfer_streak), (S.RECONSTRUCTION, 0))
        t = self.solve(t, Evidence.RETENTION)
        self.assertEqual((t.stage, t.solo_transfer_streak), (S.TRANSFER, 1))

    def test_a_hand_set_date_keeps_it_scheduled(self) -> None:
        t = self.solve(None, Evidence.NEAR_TRANSFER)
        t = self.solve(t, Evidence.RETENTION)
        t = self.solve(
            t, Evidence.RETENTION, choice=Choice(A.MANUAL, date(2026, 12, 1))
        )
        self.assertEqual(
            (t.stage, t.action, t.effective_date),
            (S.TRANSFER, A.MANUAL, date(2026, 12, 1)),
        )

    def test_a_due_hand_set_date_is_served_by_the_re_solve(self) -> None:
        due = ReviewTarget("p", date(2026, 9, 1), D, A.MANUAL, S.MIXED, 2)
        t = self.solve(due, Evidence.RETENTION)
        self.assertEqual(
            (t.action, t.effective_date), (A.RECOMMENDED, date(2026, 9, 23))
        )
        future = ReviewTarget(
            "p", date(2026, 9, 1), date(2026, 12, 1), A.MANUAL, S.MIXED, 2
        )
        t = self.solve(future, Evidence.RETENTION)
        self.assertEqual((t.action, t.effective_date), (A.MANUAL, date(2026, 12, 1)))

    def test_leetcode_targets_keep_no_streak(self) -> None:
        (t,) = finish(evidence=Evidence.RETENTION)
        self.assertEqual((t.stage, t.solo_transfer_streak), (S.TRANSFER, 0))
        (t,) = finish(evidence=Evidence.RETENTION, own=t)
        self.assertEqual((t.stage, t.solo_transfer_streak), (S.TRANSFER, 0))


def due(
    pid: str,
    title: str,
    when: date | None,
    stage: ReviewStage = S.MIXED,
    completed: int = 1,
    live: bool = False,
) -> DueCandidate:
    return DueCandidate(
        problem_id=pid,
        title=title,
        source=Source.LEETCODE,
        topic_id="tree",
        rating=1500,
        target=ReviewTarget(pid, when, when, A.RECOMMENDED if when else A.NONE, stage),
        completed_attempts=completed,
        in_unfinished_attempt=live,
    )


class DueChecksTest(unittest.TestCase):
    def test_due_conditions_and_order(self) -> None:
        checks = due_checks(
            [
                due("b", "Beta", date(2026, 9, 15)),
                due("a", "alpha", date(2026, 9, 15), S.REPAIR),
                due("c", "Gamma", date(2026, 9, 10)),
                due("future", "Future", date(2026, 9, 17)),
                due("none", "No review", None),
                due("live", "In progress", date(2026, 9, 1), live=True),
                due("new", "Snoozed new problem", date(2026, 9, 1), completed=0),
            ],
            D,
        )
        self.assertEqual([c.problem_id for c in checks], ["c", "a", "b"])
        self.assertEqual([c.is_repair for c in checks], [False, True, False])


class StartFactsTest(unittest.TestCase):
    def test_context_and_evidence(self) -> None:
        check = start_facts(
            from_plan=True,
            plan_item_kind=None,
            exposed=False,
            has_completed_attempt=False,
        )
        self.assertEqual(
            (check.context, check.evidence), (Context.MIXED, Evidence.UNSEEN)
        )
        # 'records topic picks as known-topic (targeted) evidence'
        topic = start_facts(
            from_plan=True,
            plan_item_kind=PlanItemKind.TOPIC,
            exposed=False,
            has_completed_attempt=False,
        )
        self.assertEqual(
            (topic.context, topic.evidence), (Context.TARGETED, Evidence.NEAR_TRANSFER)
        )
        listed = start_facts(
            from_plan=True,
            plan_item_kind=PlanItemKind.LIST,
            exposed=True,
            has_completed_attempt=False,
        )
        self.assertEqual(
            (listed.context, listed.evidence), (Context.TARGETED, Evidence.RETENTION)
        )
        library = start_facts(
            from_plan=False,
            plan_item_kind=None,
            exposed=False,
            has_completed_attempt=True,
        )
        self.assertEqual(
            (library.context, library.evidence), (Context.TARGETED, Evidence.RETENTION)
        )


if __name__ == "__main__":
    unittest.main()
