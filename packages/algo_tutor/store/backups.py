"""Daily SQLite backups (SPEC.md §17).

Taken with SQLite's online backup API, then checked with `PRAGMA
integrity_check` on the copy. Files are mode 0600 in a 0700 folder; the
newest 7 are kept. To restore: stop the server and copy a backup over
`algo_tutor.sqlite`.
"""

import contextlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from packages.algo_tutor.domain import constants
from packages.algo_tutor.store.models import Settings
from packages.algo_tutor.store.timeutil import iso_utc, parse_iso

PREFIX = "algo_tutor-"
SUFFIX = ".sqlite"


class BackupError(RuntimeError):
    """The copy failed its integrity check, or couldn't be written."""


@dataclass(frozen=True)
class Backup:
    """One database backup file and when it was made."""

    path: Path
    created_at: str  # ISO-8601 UTC


def _name(moment: datetime) -> str:
    # The stored timestamp with ':' made filename-safe; names sort by age.
    return PREFIX + iso_utc(moment).replace(":", "-") + SUFFIX


def list_backups(backups_dir: Path) -> list[Path]:
    """Backups in `backups_dir`, oldest first."""
    if not backups_dir.is_dir():
        return []
    return sorted(
        p
        for p in backups_dir.iterdir()
        if p.name.startswith(PREFIX) and p.name.endswith(SUFFIX)
    )


def copy_database(database: Path, backups_dir: Path, now: datetime) -> Backup:
    """Copy `database` into `backups_dir`, check the copy, prune to the newest 7."""
    backups_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backups_dir, 0o700)
    target = backups_dir / _name(now)
    # Create the file private before SQLite writes anything into it.
    os.close(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    try:
        with (
            contextlib.closing(sqlite3.connect(database)) as source,
            contextlib.closing(sqlite3.connect(target)) as copy,
        ):
            source.backup(copy)
            verdict = copy.execute("PRAGMA integrity_check").fetchall()
        if verdict != [("ok",)]:
            raise BackupError(
                f"The backup {target.name} failed its integrity check: {verdict}"
            )
    except sqlite3.Error, BackupError:
        target.unlink(missing_ok=True)
        raise
    os.chmod(target, 0o600)
    for old in list_backups(backups_dir)[: -constants.BACKUPS_KEPT]:
        old.unlink()
    return Backup(path=target, created_at=iso_utc(now))


def backup_now(
    session: Session, database: Path, backups_dir: Path, now: datetime
) -> Backup:
    """Take a backup and record it as the settings' `last_backup_at`.

    The caller commits `session`; the copy itself is outside its transaction.
    """
    backup = copy_database(database, backups_dir, now)
    settings = session.get(Settings, 1)
    if settings is not None:
        settings.last_backup_at = backup.created_at
    return backup


def backup_due(last_backup_at: str | None, now: datetime) -> bool:
    """Whether the startup backup should run: never taken, or over a day old."""
    if last_backup_at is None:
        return True
    return now - parse_iso(last_backup_at) >= timedelta(
        seconds=constants.BACKUP_MAX_AGE_SECONDS
    )
