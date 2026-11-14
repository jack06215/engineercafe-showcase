import json
import unittest
from typing import Any

from sqlalchemy import func, select

from packages.algo_tutor.catalogue.errors import Conflict
from packages.algo_tutor.catalogue.lists import create_own_lists, list_entries
from packages.algo_tutor.catalogue.packs import (
    PackError,
    canonical_json,
    import_pack,
    parse_pack,
)
from packages.algo_tutor.catalogue.problems import find_problem
from packages.algo_tutor.catalogue.testing import NOW, manifests, temp_db
from packages.algo_tutor.domain.enums import Source
from packages.algo_tutor.store.models import (
    ImportBatch,
    Problem,
    ProblemPattern,
    StudyList,
)


def pack(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "version": 2,
        "name": "Tessoku book, chapter 1",
        "source": "atcoder",
        "questions": [
            {
                "url": "https://atcoder.jp/contests/tessoku-book/tasks/tessoku_book_a",
                "title": "The First Problem",
            },
            {
                "url": "https://leetcode.com/problems/two-sum/",
                "title": "Two Sum",
                "difficulty": "Easy",
                "patterns": ["Two Pointers"],
            },
            {
                "url": "https://atcoder.jp/contests/tessoku-book/tasks/tessoku_book_b",
                "title": "Second",
                "patterns": ["01_sliding_window"],
            },
        ],
    }
    value.update(overrides)
    return value


def raw(value: dict[str, Any]) -> bytes:
    return json.dumps(value, indent=2).encode()


class ValidationTest(unittest.TestCase):
    def assert_invalid(self, value: Any, fragment: str) -> None:
        with self.assertRaises(PackError) as caught:
            parse_pack(raw(value) if isinstance(value, dict) else value)
        self.assertIn(fragment, str(caught.exception))

    def test_valid_pack_and_its_fingerprint(self) -> None:
        parsed = parse_pack(raw(pack()))
        self.assertEqual(len(parsed.pack.questions), 3)
        # Formatting and key order don't change the import id.
        compact = parse_pack(canonical_json(pack()).encode())
        self.assertEqual(parsed.import_id, compact.import_id)
        self.assertTrue(parsed.import_id.startswith("pack-v2-"))

    def test_strictness(self) -> None:
        self.assert_invalid(pack(version=1), "version")
        self.assert_invalid(pack(extra=True), "extra: unknown field")
        self.assert_invalid(pack(source="codeforces"), "source")
        self.assert_invalid(pack(questions=[]), "questions")
        q = pack()["questions"]
        self.assert_invalid(
            pack(questions=[q[0] | {"tags": []}]), "questions.0.tags: unknown field"
        )
        self.assert_invalid(
            pack(questions=[{"url": "https://example.com/x", "title": "X"}]),
            "questions.0.url",
        )
        self.assert_invalid(
            pack(questions=[q[0] | {"title": "x" * 301}]), "questions.0.title"
        )
        self.assert_invalid(
            pack(questions=[q[0], q[0] | {"url": q[0]["url"] + "/"}]),
            "duplicate of questions.0",
        )
        self.assert_invalid(pack(questions=[q[0]] * 1001), "questions")
        self.assert_invalid(pack(name="NeetCode 150"), "reserved")
        self.assert_invalid(b"{not json", "not valid JSON")


class ImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def lists(self) -> dict[str, StudyList]:
        with self.db.sessions() as session:
            return {lst.name: lst for lst in session.scalars(select(StudyList))}

    def test_dry_run_reports_and_writes_nothing(self) -> None:
        with self.db.sessions() as session, session.begin():
            report = import_pack(
                session, manifests(), parse_pack(raw(pack())), NOW, dry_run=True
            )
        self.assertEqual(
            (report.problems_created, report.entries_added, report.patterns_added),
            (3, 3, 2),
        )
        self.assertEqual(
            report.lists_created,
            ["Tessoku book, chapter 1", "Tessoku book, chapter 1 (LeetCode)"],
        )
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Problem)), 0
            )
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ImportBatch)), 0
            )

    def test_import_creates_lists_per_source_in_pack_order(self) -> None:
        with self.db.sessions() as session, session.begin():
            report = import_pack(session, manifests(), parse_pack(raw(pack())), NOW)
        self.assertFalse(report.already_applied)
        lists = self.lists()
        main = lists["Tessoku book, chapter 1"]
        self.assertEqual((main.source, main.kind), ("atcoder", "pack"))
        with self.db.sessions() as session:
            self.assertEqual(
                [e.title for e in list_entries(session, main.id)],
                ["The First Problem", "Second"],
            )
            two_sum = find_problem(session, Source.LEETCODE, "two-sum")
            assert two_sum is not None
            self.assertEqual(two_sum.number, 1)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ProblemPattern)), 2
            )

    def test_the_same_pack_twice_is_a_no_op(self) -> None:
        for expected in (False, True):
            with self.db.sessions() as session, session.begin():
                report = import_pack(session, manifests(), parse_pack(raw(pack())), NOW)
            self.assertEqual(report.already_applied, expected)
        with self.db.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(ImportBatch)), 1
            )

    def test_a_changed_pack_appends_new_questions(self) -> None:
        with self.db.sessions() as session, session.begin():
            import_pack(session, manifests(), parse_pack(raw(pack())), NOW)
            p = find_problem(session, Source.ATCODER, "tessoku_book_a")
            assert p is not None
            p.title, p.notes = "My title", "notes"
        changed = pack()
        changed["questions"].insert(
            0,
            {
                "url": "https://atcoder.jp/contests/tessoku-book/tasks/tessoku_book_c",
                "title": "Third",
            },
        )
        changed["questions"][1]["title"] = "Renamed upstream"
        with self.db.sessions() as session, session.begin():
            report = import_pack(session, manifests(), parse_pack(raw(changed)), NOW)
        self.assertEqual((report.entries_added, report.problems_created), (1, 1))
        self.assertEqual(
            report.lists_extended,
            ["Tessoku book, chapter 1", "Tessoku book, chapter 1 (LeetCode)"],
        )
        with self.db.sessions() as session:
            main = self.lists()["Tessoku book, chapter 1"]
            self.assertEqual(
                [e.title for e in list_entries(session, main.id)],
                ["My title", "Second", "Third"],
            )

    def test_a_name_taken_by_your_own_list_conflicts(self) -> None:
        with self.db.sessions() as session, session.begin():
            create_own_lists(
                session, manifests(), "Tessoku book, chapter 1", "two-sum", NOW
            )
        with (
            self.db.sessions() as session,
            session.begin(),
            self.assertRaises(Conflict),
        ):
            import_pack(session, manifests(), parse_pack(raw(pack())), NOW)

    def test_unknown_pattern_is_rejected(self) -> None:
        bad = pack()
        bad["questions"][0]["patterns"] = ["Telepathy"]
        with (
            self.db.sessions() as session,
            session.begin(),
            self.assertRaisesRegex(PackError, "Telepathy"),
        ):
            import_pack(session, manifests(), parse_pack(raw(bad)), NOW)


if __name__ == "__main__":
    unittest.main()
