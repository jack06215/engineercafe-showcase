"""The SQLite engine and sessions (SPEC.md §3.3, §16).

Every connection runs with WAL, foreign keys on and a 5 s busy timeout.
pysqlite's own transaction handling is switched off and every transaction
starts with `BEGIN IMMEDIATE`, so DDL and `PRAGMA user_version` take part in
transactions (migrations) and a read-then-write transaction never fails
halfway with SQLITE_BUSY. One learner, so serialising writers costs nothing.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 5000


def _on_connect(dbapi_connection: Any, _record: Any) -> None:
    connection: sqlite3.Connection = dbapi_connection
    connection.isolation_level = None  # SQLAlchemy's "begin" hook issues BEGIN
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()


def _on_begin(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def create_sqlite_engine(path: Path) -> Engine:
    """An engine on the database file at `path`, creating its folder (mode 0700)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _on_connect)
    event.listen(engine, "begin", _on_begin)
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: rows read in a request stay usable after commit.
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose work commits on success and rolls back on any error."""
    with factory() as session, session.begin():
        yield session
