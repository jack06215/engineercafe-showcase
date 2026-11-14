"""Study lists (SPEC.md §5.10): your own lists, editing, progress and activation.

Rules:

- one source per list; a mixed paste becomes one list per source, after a preview;
- one active list per source, kept in Settings;
- an entry is done once a completed attempt on its problem was *started* on or
  after the entry was added; re-adding an entry keeps its original add date;
- bundled lists are read-only; your own and pack lists can be renamed,
  reordered, added to and trimmed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import and_, case, exists, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Exists

from packages.algo_tutor.catalogue.bank_file import BankQuestion
from packages.algo_tutor.catalogue.errors import Conflict, InvalidInput, NotFound
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.catalogue.problems import (
    ensure_atcoder,
    ensure_leetcode,
    find_problem,
)
from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import AttemptStatus, ListKind, Source
from packages.algo_tutor.domain.urls import is_leetcode_slug, parse_problem_url
from packages.algo_tutor.store.models import (
    Attempt,
    ListEntry,
    Problem,
    Settings,
    StudyList,
)
from packages.algo_tutor.store.timeutil import iso_utc, new_id

_NUMBERING = re.compile(r"^\s*\d+\s*[.)]\s*")
SOURCE_LABELS = {Source.LEETCODE: "LeetCode", Source.ATCODER: "AtCoder"}


@dataclass(frozen=True)
class ResolvedEntry:
    source: Source
    external_id: str
    title: str
    problem_id: str | None  # None: not in the library yet; created on save
    contest: str | None = None


@dataclass(frozen=True)
class Unresolved:
    line: str
    reason: str


@dataclass(frozen=True)
class ListPreview:
    """What a paste would create: one group per source, in paste order."""

    groups: dict[Source, list[ResolvedEntry]]
    unresolved: list[Unresolved]
    names: dict[Source, str] = field(default_factory=dict)  # the list name per source


def _library_title(session: Session, title: str) -> Problem | None:
    return session.scalar(
        select(Problem).where(func.lower(Problem.title) == title.casefold()).limit(1)
    )


def _resolve_line(
    session: Session, manifests: Manifests, line: str, bank: dict[str, BankQuestion]
) -> ResolvedEntry | Unresolved:
    text = _NUMBERING.sub("", line).strip()
    first, _, rest = text.partition(" ")
    ref = parse_problem_url(first)
    if ref is not None and ref.source is Source.ATCODER:
        existing = find_problem(session, Source.ATCODER, ref.external_id)
        # A title may follow the URL on the same line; else the task id stands in.
        title = existing.title if existing else (rest.strip() or ref.external_id)
        return ResolvedEntry(
            Source.ATCODER,
            ref.external_id,
            title[: constants.MAX_TITLE_CHARS],
            existing.id if existing else None,
            contest=ref.contest,
        )
    slug = None
    if ref is not None:
        slug = ref.external_id
    elif is_leetcode_slug(text):
        slug = text
    if slug is not None:
        existing = find_problem(session, Source.LEETCODE, slug)
        if existing is not None:
            return ResolvedEntry(Source.LEETCODE, slug, existing.title, existing.id)
        known = manifests.known.get(slug)
        question = bank.get(slug)
        if known is not None or question is not None:
            title = known.title if known else question.title if question else slug
            return ResolvedEntry(Source.LEETCODE, slug, title, None)
        return Unresolved(
            line,
            "No LeetCode problem with this slug is known; download the problem bank or add it by URL.",
        )
    problem = _library_title(session, text)
    if problem is not None:
        return ResolvedEntry(
            Source(problem.source),
            problem.external_id,
            problem.title,
            problem.id,
            problem.contest,
        )
    known = manifests.find_title(text)
    if known is not None:
        return ResolvedEntry(Source.LEETCODE, known.slug, known.title, None)
    for question in bank.values():
        if question.title.casefold() == text.casefold():
            return ResolvedEntry(Source.LEETCODE, question.slug, question.title, None)
    return Unresolved(
        line, "Not a LeetCode link, slug or exact title, or an AtCoder task URL."
    )


def split_lines(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > constants.MAX_LIST_ENTRIES:
        raise InvalidInput(
            f"A list takes up to {constants.MAX_LIST_ENTRIES} entries; got {len(lines)}."
        )
    return lines


def list_names(name: str, sources: list[Source]) -> dict[Source, str]:
    """One name per source: the name itself, or "<name> (LeetCode)" for a mixed paste."""
    if len(sources) <= 1:
        return {s: name for s in sources}
    return {s: f"{name} ({SOURCE_LABELS[s]})" for s in sources}


def preview_entries(
    session: Session,
    manifests: Manifests,
    text: str,
    name: str = "",
    bank: dict[str, BankQuestion] | None = None,
) -> ListPreview:
    """Resolve pasted entries without writing anything (`POST /lists/preview`)."""
    groups: dict[Source, list[ResolvedEntry]] = {}
    seen: set[tuple[Source, str]] = set()
    unresolved = []
    for line in split_lines(text):
        result = _resolve_line(session, manifests, line, bank or {})
        if isinstance(result, Unresolved):
            unresolved.append(result)
            continue
        key = (result.source, result.external_id)
        if key in seen:
            continue
        seen.add(key)
        groups.setdefault(result.source, []).append(result)
    return ListPreview(
        groups,
        unresolved,
        list_names(name.strip(), list(groups)) if name.strip() else {},
    )


def _check_name(session: Session, name: str, exclude_id: str | None = None) -> str:
    name = name.strip()
    if not 1 <= len(name) <= constants.MAX_TITLE_CHARS:
        raise InvalidInput(f"A list name is 1–{constants.MAX_TITLE_CHARS} characters.")
    clash = session.scalar(
        select(StudyList.id).where(
            func.lower(StudyList.name) == name.casefold(),
            StudyList.id != (exclude_id or ""),
        )
    )
    if clash is not None:
        raise Conflict(f"A list named {name!r} already exists.")
    return name


def materialise(
    session: Session,
    manifests: Manifests,
    entry: ResolvedEntry,
    now: datetime,
    bank: dict[str, BankQuestion] | None = None,
) -> Problem:
    """The entry's problem, created in the library if it isn't there yet."""
    if entry.problem_id is not None:
        problem = session.get(Problem, entry.problem_id)
        if problem is not None:
            return problem
    if entry.source is Source.ATCODER:
        return ensure_atcoder(
            session, entry.external_id, entry.contest or "", entry.title, now
        ).problem
    question = (bank or {}).get(entry.external_id)
    return ensure_leetcode(
        session, manifests, entry.external_id, now, title=entry.title, bank=question
    ).problem


def create_list(
    session: Session,
    name: str,
    source: Source,
    kind: ListKind,
    now: datetime,
    *,
    origin: str | None = None,
    source_url: str | None = None,
) -> StudyList:
    row = StudyList(
        id=new_id(),
        name=_check_name(session, name),
        source=source.value,
        kind=kind.value,
        origin=origin,
        source_url=source_url,
        created_at=iso_utc(now),
    )
    session.add(row)
    session.flush()
    return row


def append_entries(
    session: Session,
    study_list: StudyList,
    problems: list[Problem],
    now: datetime,
    section: str | None = None,
) -> int:
    """Add `problems` to the end of the list, skipping ones already on it. Returns how many."""
    on_list = set(
        session.scalars(
            select(ListEntry.problem_id).where(ListEntry.list_id == study_list.id)
        )
    )
    position = session.scalar(
        select(func.coalesce(func.max(ListEntry.position), -1)).where(
            ListEntry.list_id == study_list.id
        )
    )
    next_position = int(position if position is not None else -1) + 1
    added = 0
    for problem in problems:
        if problem.id in on_list:
            continue
        if problem.source != study_list.source:
            raise InvalidInput(
                f"{problem.title} is a {problem.source} problem; this list is {study_list.source}."
            )
        session.add(
            ListEntry(
                list_id=study_list.id,
                problem_id=problem.id,
                position=next_position,
                section=section,
                added_at=iso_utc(now),
            )
        )
        on_list.add(problem.id)
        next_position += 1
        added += 1
    session.flush()
    return added


def create_own_lists(
    session: Session,
    manifests: Manifests,
    name: str,
    text: str,
    now: datetime,
    bank: dict[str, BankQuestion] | None = None,
) -> tuple[list[StudyList], list[Unresolved]]:
    """Create your list(s) from pasted entries (`POST /lists`): one per source."""
    preview = preview_entries(session, manifests, text, name, bank)
    if not preview.groups:
        raise InvalidInput("None of the entries resolved to a problem.")
    created = []
    for source, entries in preview.groups.items():
        study_list = create_list(
            session, preview.names[source], source, ListKind.OWN, now
        )
        problems = [materialise(session, manifests, e, now, bank) for e in entries]
        append_entries(session, study_list, problems, now)
        created.append(study_list)
    return created, preview.unresolved


def get_list(session: Session, list_id: str) -> StudyList:
    study_list = session.get(StudyList, list_id)
    if study_list is None:
        raise NotFound("No such list.")
    return study_list


def _editable(session: Session, list_id: str) -> StudyList:
    study_list = get_list(session, list_id)
    if study_list.kind == ListKind.BUNDLED.value:
        raise Conflict("Bundled lists are read-only.")
    return study_list


def rename_list(session: Session, list_id: str, name: str) -> StudyList:
    study_list = _editable(session, list_id)
    study_list.name = _check_name(session, name, exclude_id=list_id)
    session.flush()
    return study_list


def set_entries(
    session: Session, list_id: str, problem_ids: list[str], now: datetime
) -> StudyList:
    """Reorder and trim the list to exactly `problem_ids`, adding any new ones.

    Entries that stay keep their add date, so finished stays finished.
    """
    study_list = _editable(session, list_id)
    if len(set(problem_ids)) != len(problem_ids):
        raise InvalidInput("A problem can be on a list only once.")
    if len(problem_ids) > constants.MAX_LIST_ENTRIES:
        raise InvalidInput(f"A list takes up to {constants.MAX_LIST_ENTRIES} entries.")
    current = {
        e.problem_id: e
        for e in session.scalars(select(ListEntry).where(ListEntry.list_id == list_id))
    }
    for problem_id in problem_ids:
        if problem_id in current:
            continue
        problem = session.get(Problem, problem_id)
        if problem is None:
            raise NotFound(f"No problem {problem_id}.")
        if problem.source != study_list.source:
            raise InvalidInput(
                f"{problem.title} is a {problem.source} problem; this list is {study_list.source}."
            )
    keep = set(problem_ids)
    for problem_id, dropped in current.items():
        if problem_id not in keep:
            session.delete(dropped)
    session.flush()
    for position, problem_id in enumerate(problem_ids):
        kept = current.get(problem_id)
        if kept is None:
            session.add(
                ListEntry(
                    list_id=list_id,
                    problem_id=problem_id,
                    position=position,
                    added_at=iso_utc(now),
                )
            )
        else:
            kept.position = position
    session.flush()
    return study_list


def add_entries_from_text(
    session: Session,
    manifests: Manifests,
    list_id: str,
    text: str,
    now: datetime,
    bank: dict[str, BankQuestion] | None = None,
) -> tuple[int, list[Unresolved]]:
    """Append pasted entries of the list's source; others are reported as unresolved."""
    study_list = _editable(session, list_id)
    preview = preview_entries(session, manifests, text, bank=bank)
    unresolved = list(preview.unresolved)
    problems: list[Problem] = []
    for source, entries in preview.groups.items():
        if source.value != study_list.source:
            unresolved.extend(
                Unresolved(
                    e.title,
                    f"A {SOURCE_LABELS[source]} problem can't go on a {study_list.source} list.",
                )
                for e in entries
            )
            continue
        problems.extend(materialise(session, manifests, e, now, bank) for e in entries)
    return append_entries(session, study_list, problems, now), unresolved


def delete_list(session: Session, list_id: str) -> None:
    """Delete a list; settings' active list falls back to none via ON DELETE SET NULL."""
    study_list = get_list(session, list_id)
    session.delete(study_list)
    session.flush()
    session.expire_all()


def _settings(session: Session) -> Settings:
    settings = session.get(Settings, 1)
    if settings is None:
        raise NotFound("Settings are missing; run setup first.")
    return settings


def activate_list(session: Session, list_id: str) -> StudyList:
    """Make the list the active one for its source (SPEC §13)."""
    study_list = get_list(session, list_id)
    settings = _settings(session)
    if study_list.source == Source.LEETCODE.value:
        settings.active_list_leetcode = study_list.id
    else:
        settings.active_list_atcoder = study_list.id
    session.flush()
    return study_list


def deactivate_list(session: Session, list_id: str) -> StudyList:
    study_list = get_list(session, list_id)
    settings = _settings(session)
    if settings.active_list_leetcode == list_id:
        settings.active_list_leetcode = None
    if settings.active_list_atcoder == list_id:
        settings.active_list_atcoder = None
    session.flush()
    return study_list


def done_clause() -> Exists:
    """Whether a list entry is done: a completed attempt started on or after it was added."""
    return exists().where(
        and_(
            Attempt.problem_id == ListEntry.problem_id,
            Attempt.status == AttemptStatus.COMPLETED.value,
            Attempt.started_at >= ListEntry.added_at,
        )
    )


@dataclass(frozen=True)
class EntryView:
    problem_id: str
    title: str
    position: int
    section: str | None
    added_at: str
    done: bool


def list_entries(session: Session, list_id: str) -> list[EntryView]:
    """The list's entries in order, each with whether it's done."""
    get_list(session, list_id)
    rows = session.execute(
        select(ListEntry, Problem.title, done_clause().label("done"))
        .join(Problem, Problem.id == ListEntry.problem_id)
        .where(ListEntry.list_id == list_id)
        .order_by(ListEntry.position)
    ).all()
    return [
        EntryView(e.problem_id, title, e.position, e.section, e.added_at, bool(done))
        for e, title, done in rows
    ]


def list_progress(session: Session) -> dict[str, tuple[int, int]]:
    """(done, total) for every list, by list id."""
    rows = session.execute(
        select(
            ListEntry.list_id, func.count(), func.sum(case((done_clause(), 1), else_=0))
        ).group_by(ListEntry.list_id)
    ).all()
    return {list_id: (int(done or 0), int(total)) for list_id, total, done in rows}
