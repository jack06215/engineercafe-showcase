import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from packages.algo_tutor.store.db import create_sqlite_engine, session_factory
from packages.algo_tutor.store.migrations import (
    SCHEMA_VERSION,
    SchemaTooNewError,
    migrate,
    user_version,
)
from packages.algo_tutor.store.models import Attempt, Problem, Settings, StudyList
from packages.algo_tutor.store.timeutil import iso_utc, new_id, now_utc, parse_iso


def problem(**overrides: object) -> Problem:
    values: dict[str, object] = {
        "id": new_id(),
        "source": "leetcode",
        "external_id": "two-sum",
        "title": "Two Sum",
        "url": "https://leetcode.com/problems/two-sum/",
        "created_at": iso_utc(now_utc()),
    }
    values.update(overrides)
    return Problem(**values)


def attempt(problem_id: str, status: str = "active") -> Attempt:
    return Attempt(
        id=new_id(),
        problem_id=problem_id,
        context="targeted",
        status=status,
        evidence="near_transfer",
        started_at=iso_utc(now_utc()),
        study_date="2026-11-08",
        outcome="solved" if status == "completed" else None,
    )


class SchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "data" / "algo_tutor.sqlite"
        self.engine = create_sqlite_engine(self.path)
        migrate(self.engine)
        self.sessions = session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.folder.cleanup()

    def test_migrate_sets_user_version_and_is_idempotent(self) -> None:
        with self.engine.connect() as connection:
            self.assertEqual(user_version(connection), SCHEMA_VERSION)
        self.assertEqual(migrate(self.engine), SCHEMA_VERSION)

    def test_a_newer_schema_is_refused(self) -> None:
        with contextlib.closing(sqlite3.connect(self.path)) as raw:
            raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        with self.assertRaisesRegex(SchemaTooNewError, "newer"):
            migrate(self.engine)

    def test_pragmas(self) -> None:
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1
            )
            self.assertEqual(
                connection.exec_driver_sql("PRAGMA busy_timeout").scalar(), 5000
            )
            self.assertEqual(
                connection.exec_driver_sql("PRAGMA journal_mode").scalar(), "wal"
            )

    def test_source_and_external_id_are_unique(self) -> None:
        with (
            self.assertRaises(IntegrityError),
            self.sessions() as session,
            session.begin(),
        ):
            session.add(problem())
            session.add(problem())

    def test_checks_reject_bad_values(self) -> None:
        for bad in (
            {"source": "codeforces"},
            {"difficulty_label": "Trivial"},
            {"source_tags": "not json"},
            {"title": ""},
            {"contest": "abc174"},  # only AtCoder problems have a contest
        ):
            with self.subTest(bad=bad), self.assertRaises(IntegrityError):
                with self.sessions() as session, session.begin():
                    session.add(problem(**bad))
                    session.flush()
                    if bad == {"source_tags": "not json"}:
                        session.execute(
                            text("UPDATE problems SET source_tags = 'not json'")
                        )

    def test_report_error_message_is_capped(self) -> None:
        with self.sessions() as session, session.begin():
            p = problem()
            session.add(p)
            session.flush()
            a = attempt(p.id, "completed")
            a.report_status, a.report_error, a.report_error_message = (
                "failed",
                "error",
                "boom",
            )
            session.add(a)
        with (
            self.assertRaises(IntegrityError),
            self.sessions() as session,
            session.begin(),
        ):
            session.execute(
                text("UPDATE attempts SET report_error_message = printf('%2001s', 'x')")
            )

    def test_only_one_unfinished_attempt(self) -> None:
        with self.sessions() as session, session.begin():
            p = problem()
            session.add(p)
            session.flush()
            session.add(attempt(p.id, "completed"))
            session.add(attempt(p.id, "completed"))
            session.add(attempt(p.id, "active"))
        with (
            self.assertRaises(IntegrityError),
            self.sessions() as session,
            session.begin(),
        ):
            session.add(attempt(p.id, "paused"))

    def test_settings_is_a_singleton_with_spec_defaults(self) -> None:
        with self.sessions() as session, session.begin():
            session.add(Settings(id=1, timezone="Asia/Tokyo"))
        with self.sessions() as session:
            s = session.get(Settings, 1)
            assert s is not None
            self.assertEqual(
                (s.questions_per_day, s.atcoder_per_day, s.target_rating), (2, 0, 1850)
            )
            self.assertFalse(s.include_paid_only)
            self.assertFalse(s.onboarding_complete)
        with (
            self.assertRaises(IntegrityError),
            self.sessions() as session,
            session.begin(),
        ):
            session.add(Settings(id=2, timezone="UTC"))
        for column, value in (
            ("target_rating", 1875),
            ("questions_per_day", 21),
            ("atcoder_per_day", 11),
        ):
            with self.subTest(column=column), self.assertRaises(IntegrityError):
                with self.sessions() as session, session.begin():
                    session.execute(text(f"UPDATE settings SET {column} = {value}"))

    def test_list_names_are_unique_ignoring_case(self) -> None:
        def study_list(name: str) -> StudyList:
            return StudyList(
                id=new_id(),
                name=name,
                source="leetcode",
                kind="own",
                created_at=iso_utc(now_utc()),
            )

        with self.sessions() as session, session.begin():
            session.add(study_list("Graphs"))
        with (
            self.assertRaises(IntegrityError),
            self.sessions() as session,
            session.begin(),
        ):
            session.add(study_list("graphs"))

    def test_deleting_the_active_list_clears_the_setting(self) -> None:
        with self.sessions() as session, session.begin():
            row = StudyList(
                id=new_id(),
                name="L",
                source="leetcode",
                kind="own",
                created_at=iso_utc(now_utc()),
            )
            session.add(row)
            session.flush()
            session.add(Settings(id=1, timezone="UTC", active_list_leetcode=row.id))
        with self.sessions() as session, session.begin():
            session.execute(text("DELETE FROM lists"))
        with self.sessions() as session:
            s = session.get(Settings, 1)
            assert s is not None
            self.assertIsNone(s.active_list_leetcode)


class TimeTest(unittest.TestCase):
    def test_timestamps_round_trip_and_sort_as_text(self) -> None:
        now = now_utc()
        stamp = iso_utc(now)
        self.assertTrue(stamp.endswith("Z"))
        self.assertEqual(parse_iso(stamp), now)
        self.assertLess(iso_utc(now), iso_utc(now.replace(year=now.year + 1)))


if __name__ == "__main__":
    unittest.main()
