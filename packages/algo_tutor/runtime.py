"""Opening algo_tutor: paths, config, manifests, database (SPEC.md §3).

`open_runtime` is what `serve` and every CLI command start from. It fails
fast with a message naming the file or flag at fault: a bad config key, a
manifest checksum, a missing repo root, a database from a newer version.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from packages.algo_tutor.catalogue.bank import reset_interrupted
from packages.algo_tutor.catalogue.bank_file import BankQuestion, load_saved
from packages.algo_tutor.catalogue.manifests import Manifests, load_manifests
from packages.algo_tutor.config import AppConfig, load_config
from packages.algo_tutor.paths import AppPaths, resolve_paths
from packages.algo_tutor.store.backups import Backup, backup_due, backup_now
from packages.algo_tutor.store.db import create_sqlite_engine, session_factory
from packages.algo_tutor.store.migrations import migrate
from packages.algo_tutor.store.models import Settings
from packages.algo_tutor.store.seed import (
    ensure_settings,
    local_timezone,
    scan_patterns,
    sync_patterns,
    sync_topics,
)
from packages.algo_tutor.store.timeutil import now_utc


@dataclass(frozen=True)
class Runtime:
    """What a running server needs: paths, config, manifests and the database."""

    paths: AppPaths
    config: AppConfig
    manifests: Manifests
    engine: Engine
    sessions: sessionmaker[Session]

    def saved_bank(self) -> dict[str, BankQuestion]:
        """The last bank download by slug, for titles and tags without fetching."""
        return load_saved(self.paths.bank_file)

    def close(self) -> None:
        """Release the database engine's connections."""
        self.engine.dispose()


def open_runtime(
    repo_root: Path | None = None,
    data_dir: Path | None = None,
    config: Path | None = None,
    environ: Mapping[str, str] = os.environ,
) -> Runtime:
    """Resolve paths, load config and manifests, migrate and seed the database."""
    paths = resolve_paths(repo_root, data_dir, config, environ)
    app_config = load_config(paths.config_files)
    manifests = load_manifests()
    engine = create_sqlite_engine(paths.database)
    migrate(engine)
    sessions = session_factory(engine)
    with sessions() as session, session.begin():
        sync_topics(session, manifests.topics)
        sync_patterns(session, scan_patterns(paths.repo_root, paths.patterns_dir))
        ensure_settings(session, local_timezone(environ))
        reset_interrupted(session)
    return Runtime(paths, app_config, manifests, engine, sessions)


def take_backup(runtime: Runtime, now: datetime | None = None) -> Backup:
    """`cli algo_tutor backup` and `POST /backup`."""
    with runtime.sessions() as session, session.begin():
        return backup_now(
            session, runtime.paths.database, runtime.paths.backups_dir, now or now_utc()
        )


def startup_backup(runtime: Runtime, now: datetime | None = None) -> Backup | None:
    """At `serve`: back up when the last backup is over a day old (SPEC §17)."""
    moment = now or now_utc()
    with runtime.sessions() as session:
        settings = session.get(Settings, 1)
        last = settings.last_backup_at if settings else None
    if not backup_due(last, moment):
        return None
    return take_backup(runtime, moment)
