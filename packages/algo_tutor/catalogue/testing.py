"""Test helpers: a migrated, seeded database in a temporary folder."""

import functools
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from packages.algo_tutor.catalogue.manifests import Manifests, load_manifests
from packages.algo_tutor.domain.enums import AttemptStatus, Context, Evidence, Outcome
from packages.algo_tutor.store.db import create_sqlite_engine, session_factory
from packages.algo_tutor.store.migrations import migrate
from packages.algo_tutor.store.models import Attempt, Problem
from packages.algo_tutor.store.seed import (
    FoundPattern,
    ensure_settings,
    sync_patterns,
    sync_topics,
)
from packages.algo_tutor.store.timeutil import iso_utc, new_id

TESTDATA = Path(__file__).parent / "testdata"
NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
PATTERNS = [
    FoundPattern(
        "01_sliding_window", "Sliding Window", 1, "p/01_sliding_window/README.md"
    ),
    FoundPattern("02_two_pointers", "Two Pointers", 2, "p/02_two_pointers/README.md"),
]


@functools.cache
def manifests() -> Manifests:
    return load_manifests()


def bank_pages() -> list[Any]:
    return list(json.loads((TESTDATA / "leetcode-bank.json").read_text())["pages"])


@dataclass
class TempDb:
    folder: tempfile.TemporaryDirectory[str]
    engine: Engine
    sessions: sessionmaker[Session]

    @property
    def path(self) -> Path:
        return Path(self.folder.name)

    def close(self) -> None:
        self.engine.dispose()
        self.folder.cleanup()


def temp_db() -> TempDb:
    folder = tempfile.TemporaryDirectory()
    engine = create_sqlite_engine(Path(folder.name) / "algo_tutor.sqlite")
    migrate(engine)
    sessions = session_factory(engine)
    with sessions() as session, session.begin():
        sync_topics(session, manifests().topics)
        sync_patterns(session, PATTERNS)
        ensure_settings(session, "Asia/Tokyo")
    return TempDb(folder, engine, sessions)


def complete_attempt(
    session: Session, problem: Problem, started_at: datetime
) -> Attempt:
    """A finished, solved attempt started at `started_at`."""
    attempt = Attempt(
        id=new_id(),
        problem_id=problem.id,
        context=Context.TARGETED.value,
        status=AttemptStatus.COMPLETED.value,
        evidence=Evidence.NEAR_TRANSFER.value,
        outcome=Outcome.SOLVED.value,
        started_at=iso_utc(started_at),
        finished_at=iso_utc(started_at + timedelta(minutes=20)),
        study_date=started_at.date().isoformat(),
    )
    session.add(attempt)
    session.flush()
    return attempt
