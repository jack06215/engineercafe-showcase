import unittest
from datetime import timedelta

from sqlalchemy import select

from packages.algo_tutor.catalogue.courses import follow_course
from packages.algo_tutor.catalogue.errors import Conflict, InvalidInput
from packages.algo_tutor.catalogue.lists import (
    activate_list,
    add_entries_from_text,
    create_own_lists,
    deactivate_list,
    delete_list,
    list_entries,
    list_progress,
    preview_entries,
    rename_list,
    set_entries,
)
from packages.algo_tutor.catalogue.problems import add_problem_by_url
from packages.algo_tutor.catalogue.testing import (
    NOW,
    complete_attempt,
    manifests,
    temp_db,
)
from packages.algo_tutor.domain.enums import BundledSet, Source
from packages.algo_tutor.store.models import Problem, Settings

PASTE = """1. https://leetcode.com/problems/two-sum/
2) valid-anagram
Group Anagrams
https://atcoder.jp/contests/abc174/tasks/abc174_e Logs
https://atcoder.jp/contests/abc174/tasks/abc174_d
not a problem at all
no-such-slug-anywhere
two-sum
"""


class PreviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_a_mixed_paste_splits_by_source(self) -> None:
        with self.db.sessions() as session:
            preview = preview_entries(session, manifests(), PASTE, "Week 1")
        leetcode = preview.groups[Source.LEETCODE]
        self.assertEqual(
            [e.external_id for e in leetcode],
            ["two-sum", "valid-anagram", "group-anagrams"],
        )
        atcoder = preview.groups[Source.ATCODER]
        self.assertEqual(
            [(e.external_id, e.title) for e in atcoder],
            [("abc174_e", "Logs"), ("abc174_d", "abc174_d")],
        )
        self.assertEqual(
            [u.line for u in preview.unresolved],
            ["not a problem at all", "no-such-slug-anywhere"],
        )
        self.assertEqual(
            preview.names,
            {Source.LEETCODE: "Week 1 (LeetCode)", Source.ATCODER: "Week 1 (AtCoder)"},
        )

    def test_preview_writes_nothing(self) -> None:
        with self.db.sessions() as session:
            preview_entries(session, manifests(), PASTE)
            self.assertEqual(session.scalars(select(Problem)).all(), [])

    def test_more_than_500_entries_is_refused(self) -> None:
        with self.db.sessions() as session, self.assertRaisesRegex(InvalidInput, "500"):
            preview_entries(session, manifests(), "two-sum\n" * 501)


class OwnListTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_create_one_list_per_source(self) -> None:
        with self.db.sessions() as session, session.begin():
            lists, unresolved = create_own_lists(
                session, manifests(), "Week 1", PASTE, NOW
            )
            self.assertEqual(
                [(lst.name, lst.source, lst.kind) for lst in lists],
                [
                    ("Week 1 (LeetCode)", "leetcode", "own"),
                    ("Week 1 (AtCoder)", "atcoder", "own"),
                ],
            )
            self.assertEqual(len(unresolved), 2)
            entries = list_entries(session, lists[0].id)
            self.assertEqual(
                [e.title for e in entries],
                ["Two Sum", "Valid Anagram", "Group Anagrams"],
            )
            self.assertEqual([e.position for e in entries], [0, 1, 2])

    def test_a_single_source_paste_keeps_the_name_and_names_are_unique(self) -> None:
        with self.db.sessions() as session, session.begin():
            [only], _ = create_own_lists(
                session, manifests(), "Arrays", "two-sum\nvalid-anagram", NOW
            )
            self.assertEqual(only.name, "Arrays")
            with self.assertRaises(Conflict):
                create_own_lists(session, manifests(), "arrays", "two-sum", NOW)

    def test_done_means_a_completed_attempt_started_after_the_entry_was_added(
        self,
    ) -> None:
        with self.db.sessions() as session, session.begin():
            [lst], _ = create_own_lists(
                session, manifests(), "L", "two-sum\nvalid-anagram\ngroup-anagrams", NOW
            )
            problems = {p.external_id: p for p in session.scalars(select(Problem))}
            complete_attempt(
                session, problems["two-sum"], NOW - timedelta(days=1)
            )  # before: not done
            complete_attempt(
                session, problems["valid-anagram"], NOW
            )  # same instant: done
            complete_attempt(
                session, problems["group-anagrams"], NOW + timedelta(hours=1)
            )
            done = [e.done for e in list_entries(session, lst.id)]
            self.assertEqual(done, [False, True, True])
            self.assertEqual(list_progress(session)[lst.id], (2, 3))

    def test_reorder_trim_and_readd_keep_the_add_date(self) -> None:
        with self.db.sessions() as session, session.begin():
            [lst], _ = create_own_lists(
                session, manifests(), "L", "two-sum\nvalid-anagram", NOW
            )
            first = {e.problem_id: e.added_at for e in list_entries(session, lst.id)}
            ids = list(first)
            set_entries(session, lst.id, [ids[1], ids[0]], NOW + timedelta(days=2))
            entries = list_entries(session, lst.id)
            self.assertEqual([e.problem_id for e in entries], [ids[1], ids[0]])
            self.assertEqual({e.problem_id: e.added_at for e in entries}, first)
            set_entries(session, lst.id, [ids[1]], NOW)
            added, unresolved = add_entries_from_text(
                session,
                manifests(),
                lst.id,
                "two-sum\nhttps://atcoder.jp/contests/abc174/tasks/abc174_e X",
                NOW,
            )
            self.assertEqual(added, 1)
            self.assertEqual(
                len(unresolved), 1
            )  # an AtCoder problem can't join a LeetCode list
            rename_list(session, lst.id, "Renamed")
            self.assertEqual(lst.name, "Renamed")

    def test_set_entries_refuses_another_source(self) -> None:
        with self.db.sessions() as session, session.begin():
            [lst], _ = create_own_lists(session, manifests(), "L", "two-sum", NOW)
            atcoder = add_problem_by_url(
                session,
                manifests(),
                "https://atcoder.jp/contests/abc174/tasks/abc174_e",
                NOW,
                title="Logs",
            ).problem
            with self.assertRaisesRegex(InvalidInput, "atcoder"):
                set_entries(session, lst.id, [atcoder.id], NOW)

    def test_bundled_lists_are_read_only(self) -> None:
        with self.db.sessions() as session, session.begin():
            lst = follow_course(
                session, manifests(), BundledSet.BLIND_75, NOW
            ).study_list
            for edit in (
                lambda: rename_list(session, lst.id, "Mine"),
                lambda: set_entries(session, lst.id, [], NOW),
                lambda: add_entries_from_text(
                    session, manifests(), lst.id, "two-sum", NOW
                ),
            ):
                with self.assertRaisesRegex(Conflict, "read-only"):
                    edit()

    def test_one_active_list_per_source(self) -> None:
        with self.db.sessions() as session, session.begin():
            leet, atc = create_own_lists(session, manifests(), "W", PASTE, NOW)[0]
            other, _ = create_own_lists(session, manifests(), "Other", "two-sum", NOW)
            activate_list(session, leet.id)
            activate_list(session, atc.id)
            activate_list(session, other[0].id)
            settings = session.get(Settings, 1)
            assert settings is not None
            self.assertEqual(
                (settings.active_list_leetcode, settings.active_list_atcoder),
                (other[0].id, atc.id),
            )
            deactivate_list(session, atc.id)
            self.assertIsNone(settings.active_list_atcoder)
            delete_list(session, other[0].id)
            settings = session.get(Settings, 1)
            assert settings is not None
            self.assertIsNone(settings.active_list_leetcode)


if __name__ == "__main__":
    unittest.main()
