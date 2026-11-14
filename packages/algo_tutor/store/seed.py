"""Rows that follow files rather than the learner: topics, patterns, settings.

Run at every startup, after migrations:

- topics follow manifests/topics.yaml (names and orders update, notebooks stay);
- patterns follow common_coding_pattern's `NN_name/README.md` folders (SPEC §5.8);
- the settings row exists and carries the computer's current timezone (SPEC §13).
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import literal_column, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import ColumnElement

from packages.algo_tutor.domain.topics import TopicCatalog
from packages.algo_tutor.store.models import Pattern, Settings, Topic

_PATTERN_FOLDER = re.compile(r"^(\d+)_\w+$")
_HEADING = re.compile(r"^#\s+(.+?)\s*#*\s*$")


def sync_topics(session: Session, catalog: TopicCatalog) -> None:
    """Make the topics table match `catalog`, keeping every notebook."""
    existing = {t.id: t for t in session.scalars(select(Topic))}
    # priority and curriculum are UNIQUE: park every row on a distinct negative
    # value before writing the new ones, so a reorder can't collide. A topic
    # dropped from the YAML stays parked.
    parked: ColumnElement[int] = literal_column("-rowid")
    session.execute(update(Topic).values(priority=parked, curriculum=parked))
    session.flush()
    for t in catalog.topics:
        row = existing.get(t.id)
        if row is None:
            session.add(
                Topic(
                    id=t.id, name=t.name, priority=t.priority, curriculum=t.curriculum
                )
            )
        else:
            row.name, row.priority, row.curriculum = t.name, t.priority, t.curriculum
    session.flush()


@dataclass(frozen=True)
class FoundPattern:
    id: str  # folder name
    name: str  # the README's first `# ` heading
    position: int  # the NN prefix
    readme_path: str  # relative to the repo root


def scan_patterns(repo_root: Path, patterns_dir: Path) -> list[FoundPattern]:
    """Each `NN_name/` folder under `patterns_dir` with a README.md, in NN order."""
    found: list[FoundPattern] = []
    if not patterns_dir.is_dir():
        return found
    for folder in sorted(patterns_dir.iterdir()):
        match = _PATTERN_FOLDER.match(folder.name)
        readme = folder / "README.md"
        if not (folder.is_dir() and match and readme.is_file()):
            continue
        name = folder.name
        for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
            if heading := _HEADING.match(line):
                name = heading.group(1)
                break
        found.append(
            FoundPattern(
                id=folder.name,
                name=name,
                position=int(match.group(1)),
                readme_path=readme.relative_to(repo_root).as_posix(),
            )
        )
    return sorted(found, key=lambda p: (p.position, p.id))


def sync_patterns(session: Session, found: list[FoundPattern]) -> None:
    """Upsert the scanned patterns; one whose folder disappeared becomes `missing`."""
    by_id = {p.id: p for p in found}
    for row in session.scalars(select(Pattern)):
        hit = by_id.pop(row.id, None)
        if hit is None:
            row.missing = True
            continue
        row.name, row.position, row.readme_path, row.missing = (
            hit.name,
            hit.position,
            hit.readme_path,
            False,
        )
    for p in by_id.values():
        session.add(
            Pattern(
                id=p.id, name=p.name, position=p.position, readme_path=p.readme_path
            )
        )
    session.flush()


def local_timezone(
    environ: Mapping[str, str] = os.environ, localtime: Path = Path("/etc/localtime")
) -> str:
    """The computer's IANA timezone name, falling back to UTC."""
    candidates = []
    if tz := environ.get("TZ", "").lstrip(":"):
        candidates.append(tz)
    try:
        target = os.path.realpath(localtime)
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    for name in candidates:
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError, ValueError:
            continue
        return name
    return "UTC"


def ensure_settings(session: Session, timezone: str) -> Settings:
    """The settings row, created with the §13 defaults if missing; timezone refreshed."""
    settings = session.get(Settings, 1)
    if settings is None:
        settings = Settings(id=1, timezone=timezone)
        session.add(settings)
    else:
        settings.timezone = timezone
    session.flush()
    return settings
