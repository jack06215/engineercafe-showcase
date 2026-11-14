import contextlib
import sqlite3
import stat
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from packages.algo_tutor.store.backups import (
    backup_due,
    backup_now,
    copy_database,
    list_backups,
)
from packages.algo_tutor.store.db import create_sqlite_engine, session_factory
from packages.algo_tutor.store.migrations import migrate
from packages.algo_tutor.store.models import Settings
from packages.algo_tutor.store.timeutil import iso_utc

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


class BackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.database = self.root / "algo_tutor.sqlite"
        self.engine = create_sqlite_engine(self.database)
        migrate(self.engine)
        self.sessions = session_factory(self.engine)
        with self.sessions() as session, session.begin():
            session.add(Settings(id=1, timezone="UTC"))

    def tearDown(self) -> None:
        self.engine.dispose()
        self.folder.cleanup()

    def test_copy_is_private_checked_and_readable(self) -> None:
        backups = self.root / "backups"
        with self.sessions() as session, session.begin():
            backup = backup_now(session, self.database, backups, NOW)
        self.assertEqual(
            backup.path.name, "algo_tutor-2026-11-08T09-00-00.000000Z.sqlite"
        )
        self.assertEqual(stat.S_IMODE(backups.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(backup.path.stat().st_mode), 0o600)
        with contextlib.closing(sqlite3.connect(backup.path)) as copy:
            self.assertEqual(
                copy.execute("SELECT timezone FROM settings").fetchone(), ("UTC",)
            )
        with self.sessions() as session:
            settings = session.get(Settings, 1)
            assert settings is not None
            self.assertEqual(settings.last_backup_at, iso_utc(NOW))

    def test_keeps_the_newest_seven(self) -> None:
        backups = self.root / "backups"
        for hour in range(9):
            copy_database(self.database, backups, NOW + timedelta(hours=hour))
        kept = list_backups(backups)
        self.assertEqual(len(kept), 7)
        self.assertIn("T11-00-00", kept[0].name)
        self.assertIn("T17-00-00", kept[-1].name)

    def test_due_after_a_day(self) -> None:
        self.assertTrue(backup_due(None, NOW))
        self.assertFalse(backup_due(iso_utc(NOW - timedelta(hours=23)), NOW))
        self.assertTrue(backup_due(iso_utc(NOW - timedelta(hours=24)), NOW))


if __name__ == "__main__":
    unittest.main()
