"""Schema versions (SPEC.md §16).

`PRAGMA user_version` holds the schema version. Each upgrade is an explicit
step below, run in one transaction at startup with the version bump, as in
BloomCode. No Alembic: it isn't in the lock, and one SQLite file doesn't
need it.

Step 1 creates the schema from the models as they stand. When step 2 is
added, freeze step 1 first: replace its `create_all` with the DDL it emits
today, so an old database and a new one end up identical.
"""

from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.engine import Connection

from packages.algo_tutor.store.models import Base


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer algo_tutor."""


def _step_1(connection: Connection) -> None:
    Base.metadata.create_all(connection)


# Index i upgrades version i to i + 1.
STEPS: list[Callable[[Connection], None]] = [_step_1]
SCHEMA_VERSION = len(STEPS)


def user_version(connection: Connection) -> int:
    return int(connection.exec_driver_sql("PRAGMA user_version").scalar_one())


def migrate(engine: Engine) -> int:
    """Bring the database up to `SCHEMA_VERSION`; returns the version it was at."""
    with engine.begin() as connection:
        found = user_version(connection)
        if found > SCHEMA_VERSION:
            raise SchemaTooNewError(
                f"The database is at schema version {found}; this algo_tutor knows up to "
                f"{SCHEMA_VERSION}. Run a newer algo_tutor or restore an older backup."
            )
        for version in range(found, SCHEMA_VERSION):
            STEPS[version](connection)
        if found != SCHEMA_VERSION:
            connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return found
