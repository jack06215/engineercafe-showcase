"""Question packs, version 2 (SPEC.md §5.9).

A pack is metadata only: problems and the order of a study list, never
attempts or code. Validated strictly; the import id is the SHA-256 of the
canonical JSON, so importing the same pack twice is a no-op and a changed
pack with the same name appends its new questions to the end of its list.

One source per list (§5.10): the questions of the pack's `source` go on a
list named after the pack; any of the other source go on "<name> (LeetCode)"
or "<name> (AtCoder)".
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.algo_tutor.catalogue.bank_file import BankQuestion
from packages.algo_tutor.catalogue.errors import Conflict, InvalidInput
from packages.algo_tutor.catalogue.lists import (
    SOURCE_LABELS,
    append_entries,
    create_list,
)
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.catalogue.problems import ensure_atcoder, ensure_leetcode
from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import Difficulty, ListKind, Source
from packages.algo_tutor.domain.urls import ProblemRef, parse_problem_url
from packages.algo_tutor.store.models import (
    ImportBatch,
    Pattern,
    ProblemPattern,
    StudyList,
)
from packages.algo_tutor.store.timeutil import iso_utc

_Title = Field(min_length=1, max_length=constants.MAX_TITLE_CHARS)


class PackQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str
    title: str = _Title
    difficulty: Difficulty | None = None
    patterns: list[str] = []

    @field_validator("url")
    @classmethod
    def _problem_url(cls, url: str) -> str:
        if parse_problem_url(url) is None:
            raise ValueError("not a LeetCode problem URL or an AtCoder task URL")
        return url


class Pack(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: Literal[2]
    name: str = _Title
    source: Source
    questions: list[PackQuestion] = Field(
        min_length=1, max_length=constants.MAX_PACK_QUESTIONS
    )

    def refs(self) -> list[ProblemRef]:
        refs = []
        for q in self.questions:
            ref = parse_problem_url(q.url)
            if ref is None:  # validated above
                raise InvalidInput(f"Not a problem URL: {q.url}")
            refs.append(ref)
        return refs


class PackError(InvalidInput):
    """The pack failed validation. `problems` lists each failure with its path."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("The question pack is invalid: " + "; ".join(problems))
        self.problems = problems


def canonical_json(value: Any) -> str:
    """Keys sorted, no spaces: the same JSON always hashes the same."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ParsedPack:
    pack: Pack
    fingerprint: str  # SHA-256 of the canonical JSON

    @property
    def import_id(self) -> str:
        return f"pack-v2-{self.fingerprint}"


def parse_pack(raw: str | bytes) -> ParsedPack:
    """Validate a pack file's contents. Raises `PackError` naming every failure."""
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise PackError([f"not valid JSON: {exc}"]) from exc
    try:
        pack = Pack.model_validate(value)
    except ValidationError as exc:
        raise PackError(
            [
                ".".join(str(p) for p in e["loc"])
                + ": "
                + ("unknown field" if e["type"] == "extra_forbidden" else e["msg"])
                for e in exc.errors()
            ]
        ) from exc
    problems = []
    seen: dict[tuple[Source, str], int] = {}
    for index, ref in enumerate(pack.refs()):
        key = (ref.source, ref.external_id)
        if key in seen:
            problems.append(
                f"questions.{index}.url: duplicate of questions.{seen[key]}"
            )
        else:
            seen[key] = index
    reserved = {"neetcode 150", "blind 75", "hello interview"}
    if pack.name.casefold() in reserved:
        problems.append("name: the bundled course names are reserved")
    if problems:
        raise PackError(problems)
    return ParsedPack(
        pack, hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    )


@dataclass
class PackReport:
    import_id: str
    dry_run: bool
    already_applied: bool = False
    problems_created: int = 0
    problems_existing: int = 0
    entries_added: int = 0
    patterns_added: int = 0
    lists_created: list[str] = field(default_factory=list)
    lists_extended: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "import_id": self.import_id,
            "dry_run": self.dry_run,
            "already_applied": self.already_applied,
            "problems_created": self.problems_created,
            "problems_existing": self.problems_existing,
            "entries_added": self.entries_added,
            "patterns_added": self.patterns_added,
            "lists_created": self.lists_created,
            "lists_extended": self.lists_extended,
        }


def _pattern_ids(session: Session, pack: Pack) -> dict[str, str]:
    """Pattern name or folder (any case) → pattern id, for every name the pack uses."""
    wanted = {name for q in pack.questions for name in q.patterns}
    if not wanted:
        return {}
    lookup: dict[str, str] = {}
    for pattern in session.scalars(select(Pattern)):
        lookup[pattern.name.casefold()] = pattern.id
        lookup[pattern.id.casefold()] = pattern.id
    unknown = sorted(name for name in wanted if name.casefold() not in lookup)
    if unknown:
        raise PackError([f"patterns: unknown pattern {name!r}" for name in unknown])
    return {name: lookup[name.casefold()] for name in wanted}


def _list_for(
    session: Session,
    name: str,
    source: Source,
    origin: str,
    now: datetime,
    report: PackReport,
) -> StudyList:
    existing = session.scalar(
        select(StudyList).where(func.lower(StudyList.name) == name.casefold())
    )
    if existing is None:
        report.lists_created.append(name)
        return create_list(session, name, source, ListKind.PACK, now, origin=origin)
    if existing.kind != ListKind.PACK.value or existing.source != source.value:
        raise Conflict(f"A list named {name!r} already exists and isn't this pack's.")
    report.lists_extended.append(name)
    existing.origin = origin
    return existing


def _apply(
    session: Session,
    manifests: Manifests,
    parsed: ParsedPack,
    now: datetime,
    report: PackReport,
    bank: dict[str, BankQuestion],
) -> None:
    pack = parsed.pack
    patterns = _pattern_ids(session, pack)
    by_source: dict[Source, list[tuple[PackQuestion, ProblemRef]]] = {}
    for question, ref in zip(pack.questions, pack.refs(), strict=True):
        by_source.setdefault(ref.source, []).append((question, ref))
    for source, items in sorted(by_source.items(), key=lambda kv: kv[0] != pack.source):
        name = (
            pack.name
            if source is pack.source
            else f"{pack.name} ({SOURCE_LABELS[source]})"
        )
        study_list = _list_for(session, name, source, parsed.import_id, now, report)
        problems = []
        for question, ref in items:
            if ref.source is Source.LEETCODE:
                result = ensure_leetcode(
                    session,
                    manifests,
                    ref.external_id,
                    now,
                    title=question.title,
                    difficulty=question.difficulty,
                    bank=bank.get(ref.external_id),
                )
            else:
                result = ensure_atcoder(
                    session, ref.external_id, ref.contest or "", question.title, now
                )
                if (
                    result.problem.difficulty_label is None
                    and question.difficulty is not None
                ):
                    result.problem.difficulty_label = question.difficulty.value
            if result.created:
                report.problems_created += 1
            else:
                report.problems_existing += 1
            problems.append(result.problem)
            for name_ in question.patterns:
                key = (result.problem.id, patterns[name_])
                if session.get(ProblemPattern, key) is None:
                    session.add(ProblemPattern(problem_id=key[0], pattern_id=key[1]))
                    report.patterns_added += 1
        report.entries_added += append_entries(session, study_list, problems, now)
    session.add(
        ImportBatch(
            id=parsed.import_id,
            kind="pack",
            fingerprint=parsed.fingerprint,
            applied_at=iso_utc(now),
            report=report.as_json(),
        )
    )
    session.flush()


def import_pack(
    session: Session,
    manifests: Manifests,
    parsed: ParsedPack,
    now: datetime,
    *,
    dry_run: bool = False,
    bank: dict[str, BankQuestion] | None = None,
) -> PackReport:
    """Apply a validated pack in the caller's transaction, or report what it would do.

    A dry run does all the work inside a savepoint and rolls it back.
    """
    report = PackReport(import_id=parsed.import_id, dry_run=dry_run)
    if session.get(ImportBatch, parsed.import_id) is not None:
        report.already_applied = True
        return report
    if dry_run:
        savepoint = session.begin_nested()
        try:
            _apply(session, manifests, parsed, now, report, bank or {})
        finally:
            savepoint.rollback()
    else:
        _apply(session, manifests, parsed, now, report, bank or {})
    return report
