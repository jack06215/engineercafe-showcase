"""The daily plan, ported from BloomCode's tests/server/recommendations.test.ts,
the rule-level cases of plan-changes.test.ts and the shortlist case of
training-levels.test.ts, with upstream's expected numbers.

Upstream's NeetCode categories map to our topics: Arrays & Hashing → Hash
Table, Two Pointers → Two Pointers, Binary Search → Binary Search, Graphs →
Graph, Advanced Graphs → Shortest Path (both keep fundamentals-first order).
Cases about Bloom, chat proposals and the API (idempotency, versions,
persistence across restarts) are left to the API tests.
"""

import unittest
from datetime import UTC, date, datetime

from packages.algo_tutor.domain.enums import (
    Difficulty,
    Evidence,
    Help,
    Lane,
    Outcome,
    PlanItemKind,
    PlanItemStatus,
    ReviewAction,
    ReviewStage,
    Source,
)
from packages.algo_tutor.domain.plan import (
    ATCODER_REVIEW_REASON,
    CURRENT_REASON,
    LIST_REASON,
    TRANSFER_REASON,
    CurrentAttempt,
    PlannedItem,
    rebuild_plan,
    replacement,
    shortlist,
)
from packages.algo_tutor.domain.plan_harness import Library, existing
from packages.algo_tutor.domain.review import Choice

EASY, MEDIUM, HARD = Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD
ACTIVE, QUEUED, COMPLETED, SKIPPED = (
    PlanItemStatus.ACTIVE,
    PlanItemStatus.QUEUED,
    PlanItemStatus.COMPLETED,
    PlanItemStatus.SKIPPED,
)


def titles(items: list[PlannedItem]) -> list[str]:
    return [i.title for i in items]


def recommendations_fixture() -> Library:
    """recommendations.test.ts: imported like the problem bank, tagged, rated and unseen."""
    lib = Library(now=datetime(2026, 9, 16, 1, tzinfo=UTC))
    for t in ("ah-a", "ah-b", "ah-c"):
        lib.add(t, EASY, "hash-table")
    for t in ("tp-a", "tp-b", "tp-c"):
        lib.add(t, EASY, "two-pointers")
    # Above the 1,850 target (Hard ≈ 2,262), completed elsewhere, or without a topic.
    lib.add("graph-hard", HARD, "graph")
    lib.add("done-before", EASY, "hash-table", attempted_before=True)
    lib.add("untagged", EASY)
    return lib


class RecommendationsTest(unittest.TestCase):
    def test_weakest_topics_first_one_each_never_above_target_or_done(self) -> None:
        lib = recommendations_fixture()
        plan = lib.plan(questions_per_day=3)
        # Equal levels go fundamentals first; one per topic, then round again.
        self.assertEqual(titles(plan), ["ah-a", "tp-a", "ah-b"])
        first = plan[0]
        self.assertEqual(
            (first.reason, first.kind, first.review_of),
            ("Hash Table · your level 1300", PlanItemKind.TOPIC, None),
        )
        self.assertEqual([i.status for i in plan], [ACTIVE, QUEUED, QUEUED])
        self.assertEqual([i.position for i in plan], [0, 1, 2])
        rating = lib.rating("ah-a")
        assert rating is not None
        self.assertEqual((rating.value, rating.estimated), (1252, True))
        everything = titles(lib.plan(questions_per_day=20, day=date(2026, 9, 17)))
        for never in ("graph-hard", "done-before", "untagged"):
            self.assertNotIn(never, everything)

    def test_brings_an_idea_back_as_a_different_problem_then_retires_it(self) -> None:
        lib = recommendations_fixture()
        # Day 1: a struggle in Hash Table, a hinted solve in Two Pointers.
        lib.practise("ah-a", Outcome.NOT_SOLVED, Help.MAJOR, 900)
        lib.practise("tp-a", Outcome.SOLVED, Help.SMALL, 600)
        t = lib.targets["ah-a"]
        self.assertEqual(
            (t.stage, t.effective_date), (ReviewStage.REPAIR, date(2026, 9, 17))
        )

        # Day 2: the struggle comes back as easier practice from the same topic, not the problem.
        lib.at("2026-09-17T01:00:00Z")
        day2 = lib.plan(questions_per_day=3)
        self.assertEqual(
            (day2[0].title, day2[0].review_of, day2[0].reason),
            ("ah-b", "ah-a", "Hash Table · easier practice after ah-a"),
        )
        self.assertNotIn("ah-a", titles(day2))
        self.assertNotIn("tp-a", titles(day2))
        lib.practise(
            day2[0].problem_id, Outcome.SOLVED, Help.NONE, 300, 5.0, item=day2[0]
        )
        # The repair moved the original idea on; the easier problem has no schedule of its own.
        self.assertEqual(lib.targets["ah-a"].stage, ReviewStage.MIXED)
        self.assertEqual(lib.targets["ah-b"].action, ReviewAction.NONE)

        # Day 4: the hinted solve's idea comes back as a different problem from its topic.
        # Upstream (rules, no Bloom) served it as visible "Two Pointers · practice after
        # tp-a"; SPEC §8.3 makes the fair sibling a hidden transfer check.
        lib.at("2026-09-19T01:00:00Z")
        day4 = lib.plan(questions_per_day=3)
        check = next(i for i in day4 if i.review_of == "tp-a")
        self.assertEqual((check.reason, check.kind), (TRANSFER_REASON, None))
        self.assertIn(check.title, ["tp-b", "tp-c"])
        practised = lib.practise(
            check.problem_id, Outcome.SOLVED, Help.NONE, 300, 5.0, item=check
        )
        self.assertEqual(
            practised.evidence, Evidence.UNSEEN
        )  # upstream: near_transfer (visible)
        t = lib.targets["tp-a"]
        self.assertEqual(
            (t.stage, t.effective_date), (ReviewStage.MIXED, date(2026, 10, 3))
        )

        # Two weeks later another solo solve of the same idea retires it.
        lib.at("2026-10-03T01:00:00Z")
        later = lib.plan(questions_per_day=3)
        second = next(i for i in later if i.review_of == "tp-a")
        self.assertNotEqual(second.problem_id, check.problem_id)
        lib.practise(
            second.problem_id, Outcome.SOLVED, Help.NONE, 300, 5.0, item=second
        )
        t = lib.targets["tp-a"]
        self.assertEqual((t.stage, t.action), (ReviewStage.RETIRED, ReviewAction.NONE))

    def test_rebuilds_only_unstarted_items(self) -> None:
        lib = recommendations_fixture()
        plan = lib.plan(questions_per_day=4)
        done_item, active_item = plan[0], plan[1]
        lib.practise(
            done_item.problem_id,
            Outcome.SOLVED,
            Help.NONE,
            30,
            item=done_item,
            choice=Choice(ReviewAction.MANUAL, date(2026, 12, 1)),
        )
        lib.start(active_item.problem_id, active_item)
        items = existing(
            plan, statuses={0: COMPLETED, 1: ACTIVE, 2: QUEUED}, started={0, 1}
        )
        rebuilt = rebuild_plan(
            lib.context(), items, questions_per_day=4, atcoder_per_day=0
        )
        self.assertEqual(rebuilt.removed, ("item2", "item3"))
        self.assertEqual(len(rebuilt.added), 2)
        self.assertTrue(all(i.status is QUEUED for i in rebuilt.added))
        self.assertEqual([i.position for i in rebuilt.added], [2, 3])
        all_titles = [done_item.title, active_item.title, *titles(list(rebuilt.added))]
        self.assertEqual(len(set(all_titles)), len(all_titles))

    def test_unstarted_stays_eligible_and_finished_work_never_repeats(self) -> None:
        lib = recommendations_fixture()
        lib.target = 1800
        first = lib.plan(questions_per_day=1)
        lib.at("2026-09-17T01:00:00Z")
        second = lib.plan(questions_per_day=1)
        self.assertEqual(
            second[0].problem_id, first[0].problem_id
        )  # unstarted remains eligible
        lib.at("2026-09-18T01:00:00Z")
        lib.practise(
            second[0].problem_id, Outcome.SOLVED, Help.NONE, 10, item=second[0]
        )
        third = lib.plan(questions_per_day=1, day=date(2026, 9, 19))
        self.assertNotEqual(third[0].problem_id, second[0].problem_id)  # never repeated

    def test_snoozed_new_problem_waits_swap_and_empty_library(self) -> None:
        lib = recommendations_fixture()
        today = lib.plan(questions_per_day=2)
        snoozed = today[1]
        lib.snooze(snoozed.problem_id, date(2026, 9, 20))
        self.assertNotIn(
            snoozed.title, titles(lib.plan(questions_per_day=2, day=date(2026, 9, 18)))
        )
        # Once its date comes, a never-attempted problem is simply new again (not a check).
        back = lib.plan(questions_per_day=20, day=date(2026, 9, 21))
        self.assertIn(snoozed.title, titles(back))
        self.assertTrue(all(i.review_of is None for i in back))

        items = existing(today, statuses={1: SKIPPED})
        swap = replacement(lib.context(), items[0], items)
        assert swap is not None
        # Both of the day's items are now set aside (one snoozed, one swapped): one replacement.
        self.assertNotIn(swap.title, ("graph-hard", snoozed.title, today[0].title))

        empty = Library(now=lib.now)
        self.assertEqual(empty.plan(), [])


class ShortlistTest(unittest.TestCase):
    """training-levels.test.ts: 'candidates are the most popular unseen problems
    near your level, else the closest, never above target'"""

    def test_popular_near_else_closest(self) -> None:
        lib = recommendations_fixture()
        lib.problems.clear()
        lib.add("obscure-near", EASY, "graph", popularity=20)
        lib.add("famous-near", EASY, "graph", popularity=97)
        lib.add("graph-hard", HARD, "graph")
        # Nothing near a new learner: the closest ones are offered.
        lib.add("advanced-a", MEDIUM, "shortest-path")
        lib.add("advanced-b", MEDIUM, "shortest-path")
        topics = {t.topic_id: t for t in shortlist(lib.context())}
        graph = topics["graph"].problems
        self.assertEqual((graph[0].title, graph[0].popularity), ("famous-near", 97))
        # Hard (≈2,262) is above the 1,850 target: never offered.
        self.assertNotIn("graph-hard", [c.title for c in graph])
        self.assertEqual(
            [c.title for c in topics["shortest-path"].problems],
            ["advanced-a", "advanced-b"],
        )
        # Weakest first; equal levels go in fundamentals-first order.
        order = list(topics)
        self.assertLess(order.index("graph"), order.index("shortest-path"))

        lib.target = 1300
        for t in shortlist(lib.context()):
            for c in t.problems:
                self.assertLessEqual(c.rating, 1300)

    def test_window_top_up_and_cap(self) -> None:
        lib = recommendations_fixture()
        lib.problems.clear()
        for n, exact in enumerate([1300, 1350, 1250, 1450, 1100, 1500, 1520, 1290]):
            lib.add(f"p{n}", MEDIUM, "greedy", exact=exact, popularity=n)
        (greedy,) = shortlist(lib.context())
        # Within ±100 of 1300, most popular first (p7, p2, p1, p0); topped up with the
        # closest outside (p3 at 150 before p4 and p5 at 200).
        self.assertEqual(
            [c.title for c in greedy.problems], ["p7", "p2", "p1", "p0", "p3"]
        )

    def test_at_target_topics_and_paid_only(self) -> None:
        lib = recommendations_fixture()
        lib.problems.clear()
        lib.add("paid", EASY, "greedy", paid_only=True)
        lib.add("free", EASY, "trie")
        self.assertEqual([t.topic_id for t in shortlist(lib.context())], ["trie"])
        lib.include_paid_only = True
        self.assertEqual(
            {t.topic_id for t in shortlist(lib.context())}, {"greedy", "trie"}
        )
        lib.target = 1300  # every topic is at 1300: at target, so no new practice
        self.assertEqual(shortlist(lib.context()), [])


def search_fixture() -> Library:
    """plan-changes.test.ts: a fresh learner's Binary Search window is 1,150–1,350:
    Easy (≈1,252) fits, Hard doesn't."""
    lib = recommendations_fixture()
    lib.problems.clear()
    lib.at("2026-10-01T09:00:00Z")
    for title in ("Search One", "Search Two", "Search Three", "Search Four"):
        lib.add(title, EASY, "binary-search")
    lib.add("Search Hard", HARD, "binary-search")
    return lib


class StudyListTest(unittest.TestCase):
    def test_list_fills_the_day_first_repeats_included_and_rules_fill_the_rest(
        self,
    ) -> None:
        lib = search_fixture()
        lib.practise("Search One")  # solved before it was listed: still on the list
        lib.at("2026-10-01T10:00:00Z")
        lib.set_list(
            Source.LEETCODE, "Mine", ["Search Hard", "Search One", "Search Two"]
        )
        day1 = lib.plan()
        self.assertEqual(titles(day1), ["Search Hard", "Search One"])
        self.assertEqual(
            (day1[0].status, day1[0].reason, day1[0].kind),
            (ACTIVE, LIST_REASON, PlanItemKind.LIST),
        )
        lib.practise(day1[0].problem_id, item=day1[0])
        study = lib.study_list(Source.LEETCODE)
        assert study is not None
        self.assertEqual([e.title for e in study.entries if e.done], ["Search Hard"])

        # The next day: unfinished problems carry over; a shorter list leaves room for the rules.
        lib.at("2026-10-02T09:00:00Z")
        lib.set_list(Source.LEETCODE, "Mine", ["Search Two", "Search Hard"])
        day2 = lib.plan()
        self.assertEqual(len(day2), 2)
        self.assertEqual((day2[0].title, day2[0].reason), ("Search Two", LIST_REASON))
        self.assertNotEqual(day2[1].reason, LIST_REASON)
        self.assertNotIn("Search Hard", titles(day2))

        # Rebuilding the day keeps the list's problem first.
        rebuilt = rebuild_plan(
            lib.context(),
            existing(day2),
            questions_per_day=2,
            atcoder_per_day=0,
            leetcode_list=lib.study_list(Source.LEETCODE),
        )
        self.assertEqual(rebuilt.added[0].title, "Search Two")
        # With no active list, a rebuild drops the list's unstarted problem; the list waits.
        no_list = rebuild_plan(
            lib.context(), existing(day2), questions_per_day=2, atcoder_per_day=0
        )
        self.assertNotIn(LIST_REASON, [i.reason for i in no_list.added])
        self.assertEqual(no_list.added[0].status, ACTIVE)

    def test_a_full_list_leaves_one_slot_for_a_due_check(self) -> None:
        lib = search_fixture()
        lib.practise(
            "Search One", Outcome.NOT_SOLVED, Help.MAJOR
        )  # repair due tomorrow
        lib.set_list(
            Source.LEETCODE, "Mine", ["Search Hard", "Search Two", "Search Three"]
        )
        lib.at("2026-10-02T09:00:00Z")
        day = lib.plan(questions_per_day=2)
        self.assertEqual(titles(day)[0], "Search Hard")
        self.assertEqual(
            (day[1].review_of, day[1].reason),
            ("Search One", "Binary Search · easier practice after Search One"),
        )
        # A single slot is the list's.
        self.assertEqual(titles(lib.plan(questions_per_day=1)), ["Search Hard"])

    def test_an_unplanned_attempt_in_progress_keeps_slot_zero(self) -> None:
        lib = search_fixture()
        lib.set_list(Source.LEETCODE, "Mine", ["Search Two"])
        lib.start("Search Four")
        day = lib.plan(
            questions_per_day=3,
            current=CurrentAttempt("Search Four", "Search Four", Source.LEETCODE),
        )
        self.assertEqual(titles(day), ["Search Four", "Search Two", "Search One"])
        self.assertEqual(
            (day[0].reason, day[0].status, day[0].kind), (CURRENT_REASON, ACTIVE, None)
        )
        self.assertEqual([i.status for i in day[1:]], [QUEUED, QUEUED])


class TransferCheckTest(unittest.TestCase):
    def due_idea(self, lib: Library) -> None:
        """plan-changes.test.ts `dueIdea`: a hinted solve with its review set to today."""
        lib.practise(
            "Search One",
            Outcome.SOLVED,
            Help.SMALL,
            600,
            choice=Choice(ReviewAction.MANUAL, date(2026, 10, 1)),
        )

    def test_without_a_fair_sibling_the_check_is_visible_topic_practice(self) -> None:
        lib = search_fixture()
        self.due_idea(lib)
        for title in ("Search Two", "Search Three", "Search Four"):
            lib.problems[title].exposed = True  # seen: unfair as an unseen check
        (check,) = [i for i in lib.plan(questions_per_day=2) if i.review_of]
        self.assertEqual(
            (check.reason, check.kind),
            ("Binary Search · practice after Search One", PlanItemKind.TOPIC),
        )

    def test_a_fair_sibling_is_a_hidden_transfer_check(self) -> None:
        lib = search_fixture()
        self.due_idea(lib)
        lib.add("Search Five", MEDIUM, "binary-search", exact=1403)  # above 1,252 + 150
        lib.add("Search Six", EASY, "binary-search", paid_only=True)
        lib.problems["Search Two"].exposed = True
        lib.problems["Search Three"].exposed = True
        plan = lib.plan(questions_per_day=2)
        check = plan[0]
        self.assertEqual(
            (check.title, check.reason, check.kind, check.review_of),
            ("Search Four", TRANSFER_REASON, None, "Search One"),
        )
        # The hand-set date came due and is served: back to the recommended schedule.
        lib.practise(check.problem_id, item=check)
        t = lib.targets["Search One"]
        self.assertEqual(
            (t.action, t.stage, t.effective_date),
            (ReviewAction.RECOMMENDED, ReviewStage.MIXED, date(2026, 10, 15)),
        )
        self.assertEqual(lib.targets["Search Four"].stage, ReviewStage.COVERED)

    def test_an_idea_is_checked_at_most_once_a_day(self) -> None:
        lib = search_fixture()
        self.due_idea(lib)
        plan = lib.plan(questions_per_day=2)
        self.assertEqual(sum(1 for i in plan if i.review_of), 1)
        # Replacing the other item never serves the same idea again.
        items = existing(plan)
        other = next(i for i in items if i.review_of is None)
        swap = replacement(lib.context(), other, items)
        assert swap is not None
        self.assertIsNone(swap.review_of)
        # Replacing the check itself may serve the idea as a different problem.
        check = next(i for i in items if i.review_of)
        again = replacement(lib.context(), check, items)
        assert again is not None
        self.assertEqual(again.review_of, "Search One")
        self.assertNotIn(again.problem_id, [i.problem_id for i in items])

    def test_nothing_fits(self) -> None:
        lib = search_fixture()
        lib.problems.clear()
        lib.add("Only", EASY, "binary-search")
        items = existing(lib.plan(questions_per_day=1))
        self.assertIsNone(replacement(lib.context(), items[0], items))


class AtCoderLaneTest(unittest.TestCase):
    def fixture(self) -> Library:
        lib = search_fixture()
        for task in ("abc1_a", "abc1_b", "abc1_c", "abc1_d"):
            lib.add(task, None, source=Source.ATCODER)
        lib.set_list(
            Source.ATCODER, "ABC drill", ["abc1_a", "abc1_b", "abc1_c", "abc1_d"]
        )
        return lib

    def lane(self, items: list[PlannedItem], lane: Lane) -> list[PlannedItem]:
        return [i for i in items if i.lane is lane]

    def test_quota_zero_shows_no_new_entries(self) -> None:
        lib = self.fixture()
        plan = lib.plan(questions_per_day=2)
        self.assertEqual(self.lane(plan, Lane.ATCODER), [])
        self.assertEqual(len(self.lane(plan, Lane.LEETCODE)), 2)

    def test_quota_takes_list_entries_in_order(self) -> None:
        lib = self.fixture()
        at = self.lane(lib.plan(atcoder_per_day=2), Lane.ATCODER)
        self.assertEqual(
            [(i.title, i.reason, i.position, i.status) for i in at],
            [
                ("abc1_a", "From ABC drill", 0, QUEUED),
                ("abc1_b", "From ABC drill", 1, QUEUED),
            ],
        )
        self.assertTrue(all(i.kind is PlanItemKind.LIST for i in at))

    def test_due_reviews_bring_the_same_problem_back_whatever_the_quota(self) -> None:
        lib = self.fixture()
        lib.practise("abc1_c", Outcome.NOT_SOLVED, Help.MAJOR)  # repair tomorrow
        lib.practise("abc1_a")  # solved alone: +14
        lib.at("2026-10-02T09:00:00Z")
        at = self.lane(lib.plan(atcoder_per_day=0), Lane.ATCODER)
        self.assertEqual(
            [(i.title, i.reason, i.review_of) for i in at],
            [("abc1_c", ATCODER_REVIEW_REASON, None)],
        )
        at = self.lane(lib.plan(atcoder_per_day=1), Lane.ATCODER)
        # abc1_a and abc1_c are done (attempted after listing); abc1_b is next.
        self.assertEqual(titles(at), ["abc1_c", "abc1_b"])

    def test_retirement_through_the_lane(self) -> None:
        lib = self.fixture()
        lib.practise("abc1_a")
        self.assertEqual(lib.targets["abc1_a"].effective_date, date(2026, 10, 15))
        lib.at("2026-10-15T09:00:00Z")
        (review,) = self.lane(lib.plan(), Lane.ATCODER)
        self.assertEqual(
            lib.practise(review.problem_id, item=review).evidence, Evidence.RETENTION
        )
        self.assertEqual(lib.targets["abc1_a"].stage, ReviewStage.TRANSFER)
        lib.at("2026-10-22T09:00:00Z")
        (review,) = self.lane(lib.plan(), Lane.ATCODER)
        lib.practise(review.problem_id, item=review)
        self.assertEqual(lib.targets["abc1_a"].stage, ReviewStage.RETIRED)
        lib.at("2026-12-01T09:00:00Z")
        self.assertEqual(self.lane(lib.plan(), Lane.ATCODER), [])

    def test_atcoder_never_reaches_the_ladder(self) -> None:
        lib = self.fixture()
        lib.practise("abc1_a")
        self.assertTrue(all(lv.attempts == 0 for lv in lib.levels()))
        self.assertNotIn("abc1_b", titles(lib.plan(questions_per_day=20)))

    def test_the_first_item_is_active_across_lanes(self) -> None:
        lib = self.fixture()
        lib.problems = {
            k: v for k, v in lib.problems.items() if v.source is Source.ATCODER
        }
        plan = lib.plan(atcoder_per_day=2)
        self.assertEqual([i.status for i in plan], [ACTIVE, QUEUED])
        lib.start("abc1_d")
        plan = lib.plan(
            atcoder_per_day=1,
            current=CurrentAttempt("abc1_d", "abc1_d", Source.ATCODER),
        )
        self.assertEqual(
            [(i.title, i.status) for i in plan],
            [("abc1_d", ACTIVE), ("abc1_a", QUEUED)],
        )

    def test_rebuild_keeps_the_quota(self) -> None:
        lib = self.fixture()
        plan = lib.plan(questions_per_day=1, atcoder_per_day=2)
        lib.practise(plan[1].problem_id, item=plan[1])
        items = existing(plan, statuses={0: ACTIVE, 1: COMPLETED})
        rebuilt = rebuild_plan(
            lib.context(),
            items,
            questions_per_day=1,
            atcoder_per_day=2,
            atcoder_list=lib.study_list(Source.ATCODER),
        )
        self.assertEqual(
            [
                (i.title, i.lane, i.position)
                for i in rebuilt.added
                if i.lane is Lane.ATCODER
            ],
            [("abc1_b", Lane.ATCODER, 1)],
        )


if __name__ == "__main__":
    unittest.main()
