"""The library and problem pages (SPEC §5, §6.4, §14 Library and Problem).

The library is small (a few thousand problems at most), so GET /problems
filters what SQL filters cheaply, then builds every row and filters, sorts
and pages the rest in Python, where the rating rule (§5.5) lives.
"""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import deps, facts, schemas
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import ApiError, hidden_assessment, not_found
from packages.algo_tutor.catalogue.problems import add_problem_by_url, assign_topic
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
    Context,
    Difficulty,
    Help,
    Language,
    Outcome,
    ReviewAction,
    ReviewStage,
    Source,
)
from packages.algo_tutor.domain.paths import (
    ATCODER_SRC,
    EXTENSIONS,
    LEETCODE_SRC,
    suggest_path,
)
from packages.algo_tutor.store.models import (
    Attempt,
    ListEntry,
    Pattern,
    Problem,
    ProblemPattern,
    ProblemPopularity,
    ReviewTarget,
    StudyList,
    Topic,
)
from packages.algo_tutor.store.timeutil import parse_iso

router = APIRouter(tags=["problems"])

_DIFFICULTY_RANK = {
    Difficulty.EASY.value: 0,
    Difficulty.MEDIUM.value: 1,
    Difficulty.HARD.value: 2,
}


def _date(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def get_problem(session: Session, problem_id: str) -> Problem:
    """Return the problem with *problem_id*; raise 404 if there is none."""
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise not_found("Problem")
    return problem


# ---------------------------------------------------------------- detail


def review_out(target: ReviewTarget | None) -> schemas.ReviewTargetOut | None:
    """Convert a review target to its API shape."""
    if target is None:
        return None
    return schemas.ReviewTargetOut(
        problem_id=target.problem_id,
        recommended_date=_date(target.recommended_date),
        effective_date=_date(target.effective_date),
        action=ReviewAction(target.action),
        stage=ReviewStage(target.stage),
        version=target.version,
    )


def attempt_summary(attempt: Attempt) -> schemas.AttemptSummary:
    """Return the short API view of *attempt*."""
    return schemas.AttemptSummary(
        id=attempt.id,
        problem_id=attempt.problem_id,
        status=AttemptStatus(attempt.status),
        context=Context(attempt.context),
        language=Language(attempt.language),
        outcome=Outcome(attempt.outcome) if attempt.outcome else None,
        help=Help(attempt.help),
        confidence=attempt.confidence,
        active_seconds=attempt.active_seconds,
        started_at=parse_iso(attempt.started_at),
        finished_at=parse_iso(attempt.finished_at) if attempt.finished_at else None,
        study_date=date.fromisoformat(attempt.study_date),
    )


def pattern_ids(session: Session, problem_id: str) -> list[str]:
    """Return the pattern IDs of *problem_id*, in pattern order."""
    return list(
        session.scalars(
            select(ProblemPattern.pattern_id)
            .join(Pattern, Pattern.id == ProblemPattern.pattern_id)
            .where(ProblemPattern.problem_id == problem_id)
            .order_by(Pattern.position)
        )
    )


def detail(
    session: Session, state: AppState, problem: Problem
) -> schemas.ProblemDetail:
    """Return the full API view of *problem*."""
    lists = session.execute(
        select(StudyList.id, StudyList.name)
        .join(ListEntry, ListEntry.list_id == StudyList.id)
        .where(ListEntry.problem_id == problem.id)
        .order_by(StudyList.name)
    ).tuples()
    attempts = session.scalars(
        select(Attempt)
        .where(Attempt.problem_id == problem.id)
        .order_by(Attempt.started_at.desc())
    )
    target = session.scalar(
        select(ReviewTarget).where(ReviewTarget.problem_id == problem.id)
    )
    return schemas.ProblemDetail(
        problem=facts.brief_one(session, state.runtime.manifests, problem),
        external_id=problem.external_id,
        paid_only=problem.paid_only,
        source_tags=list(problem.source_tags),
        neetcode_category=problem.neetcode_category,
        topic_id=problem.topic_id,
        topic_overridden=problem.topic_overridden,
        patterns=pattern_ids(session, problem.id),
        notes=problem.notes,
        exposed=problem.exposed,
        lists=[schemas.ListRef(id=list_id, name=name) for list_id, name in lists],
        review=review_out(target),
        attempts=[attempt_summary(a) for a in attempts],
    )


# ---------------------------------------------------------------- the library


@dataclass(frozen=True)
class _Latest:
    outcome: Outcome
    active_seconds: int
    confidence: int | None
    finished_at: str


def _latest_completed(session: Session) -> dict[str, _Latest]:
    """Each problem's most recent completed attempt."""
    latest: dict[str, _Latest] = {}
    rows = session.execute(
        select(
            Attempt.problem_id,
            Attempt.outcome,
            Attempt.active_seconds,
            Attempt.confidence,
            Attempt.finished_at,
        )
        .where(Attempt.status == AttemptStatus.COMPLETED.value)
        .order_by(Attempt.finished_at, Attempt.id)
    ).tuples()
    for problem_id, outcome, seconds, confidence, finished_at in rows:
        latest[problem_id] = _Latest(
            Outcome(outcome or Outcome.STOPPED), seconds, confidence, finished_at or ""
        )
    return latest


def _time_bucket(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    minutes = seconds / 60
    for limit, bucket in ((10, "0-10"), (20, "10-20"), (30, "20-30"), (45, "30-45")):
        if minutes < limit:
            return bucket
    return "45+"


def _confidence_bucket(confidence: int | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence < 3:
        return "low"
    return "medium" if confidence < 4 else "high"


def _sort_key(
    sort: schemas.ProblemSort, row: schemas.ProblemRow, latest: _Latest | None
) -> Any:
    """The value to sort by; None sorts last in either direction (see `_order`)."""
    match sort:
        case "title":
            return row.problem.title.casefold()
        case "difficulty":
            label = row.problem.difficulty
            return None if label is None else _DIFFICULTY_RANK[label.value]
        case "rating":
            return None if row.problem.rating is None else row.problem.rating.value
        case "latest":  # most recently practised
            return None if latest is None else latest.finished_at
        case "time":
            return row.latest_active_seconds
        case "confidence":
            return row.latest_confidence
        case "next_review":
            return row.next_review_date


def _order(
    rows: list[tuple[schemas.ProblemRow, _Latest | None]],
    sort: schemas.ProblemSort,
    descending: bool,
) -> list[schemas.ProblemRow]:
    by_title = sorted(
        rows, key=lambda pair: (pair[0].problem.title.casefold(), pair[0].problem.id)
    )
    present = [pair for pair in by_title if _sort_key(sort, *pair) is not None]
    absent = [pair for pair in by_title if _sort_key(sort, *pair) is None]
    present.sort(
        key=lambda pair: _sort_key(sort, *pair), reverse=descending
    )  # stable: title breaks ties
    return [row for row, _ in present + absent]


@router.get("/problems")
def list_problems(
    query: Annotated[schemas.ProblemQuery, Query()],
    state: deps.State,
    session: deps.Db,
) -> schemas.ProblemPage:
    """Return one page of the problem library, filtered and sorted."""
    deps.forbid_during_assessment(session)
    statement = select(Problem)
    if query.q:
        needle = f"%{query.q.strip().lower()}%"
        statement = statement.where(
            or_(Problem.title.ilike(needle), Problem.url.ilike(needle))
        )
    if query.source is not None:
        statement = statement.where(Problem.source == query.source.value)
    if query.difficulty is not None:
        statement = statement.where(Problem.difficulty_label == query.difficulty.value)
    if query.topic == "none":
        statement = statement.where(Problem.topic_id.is_(None))
    elif query.topic is not None:
        statement = statement.where(Problem.topic_id == query.topic)
    if query.pattern is not None:
        statement = statement.where(
            Problem.id.in_(
                select(ProblemPattern.problem_id).where(
                    ProblemPattern.pattern_id == query.pattern
                )
            )
        )
    if query.list_id is not None:
        statement = statement.where(
            Problem.id.in_(
                select(ListEntry.problem_id).where(ListEntry.list_id == query.list_id)
            )
        )
    problems = [
        p
        for p in session.scalars(statement)
        if query.tag is None or query.tag in p.source_tags
    ]

    latest = _latest_completed(session)
    # Comprehensions, not dict(): a Result has .keys(), so dict() takes it for a mapping.
    reviews = {
        pid: day
        for pid, day in session.execute(
            select(ReviewTarget.problem_id, ReviewTarget.effective_date)
        ).tuples()
    }
    popularity = {
        pid: pct
        for pid, pct in session.execute(
            select(ProblemPopularity.problem_id, ProblemPopularity.percentile)
        ).tuples()
    }
    patterns: dict[str, list[str]] = {}
    for problem_id, pattern_id in session.execute(
        select(ProblemPattern.problem_id, ProblemPattern.pattern_id)
        .join(Pattern, Pattern.id == ProblemPattern.pattern_id)
        .order_by(Pattern.position)
    ).tuples():
        patterns.setdefault(problem_id, []).append(pattern_id)
    fitted = facts.estimates(session)
    manifests = state.runtime.manifests

    rows: list[tuple[schemas.ProblemRow, _Latest | None]] = []
    for p in problems:
        last = latest.get(p.id)
        row = schemas.ProblemRow(
            problem=facts.brief(p, facts.rating_of(p, manifests, fitted.get(p.id))),
            topic_id=p.topic_id,
            source_tags=list(p.source_tags),
            patterns=patterns.get(p.id, []),
            paid_only=p.paid_only,
            popularity=popularity.get(p.id),
            latest_outcome=last.outcome if last else None,
            latest_active_seconds=last.active_seconds if last else None,
            latest_confidence=last.confidence if last else None,
            next_review_date=_date(reviews.get(p.id)),
        )
        if query.latest is not None:
            shown = (
                "not_submitted"
                if row.latest_outcome is None
                else row.latest_outcome.value
            )
            if shown != query.latest:
                continue
        if (
            query.time is not None
            and _time_bucket(row.latest_active_seconds) != query.time
        ):
            continue
        if (
            query.confidence is not None
            and _confidence_bucket(row.latest_confidence) != query.confidence
        ):
            continue
        rows.append((row, last))

    ordered = _order(rows, query.sort, query.order == "desc")
    start = (query.page - 1) * query.page_size
    return schemas.ProblemPage(
        items=ordered[start : start + query.page_size],
        total=len(ordered),
        page=query.page,
        page_size=query.page_size,
    )


@router.post("/problems")
def add_problem(
    body: schemas.ProblemCreate, state: deps.State, session: deps.Db
) -> JSONResponse:
    """Add a problem by URL.

    A problem already in the library comes back as is (200 instead of 201).
    AtCoder needs a typed title (never fetched).
    """
    deps.forbid_during_assessment(session)
    added = add_problem_by_url(
        session,
        state.runtime.manifests,
        body.url,
        state.clock(),
        title=body.title,
        bank=state.runtime.saved_bank(),
    )
    if (
        added.created
        and body.difficulty is not None
        and added.problem.difficulty_label is None
    ):
        added.problem.difficulty_label = body.difficulty.value
        session.flush()
    out = detail(session, state, added.problem)
    return JSONResponse(
        status_code=201 if added.created else 200, content=out.model_dump(mode="json")
    )


@router.get("/problems/{problem_id}")
def get_problem_detail(
    problem_id: str, state: deps.State, session: deps.Db
) -> schemas.ProblemDetail:
    """Showing a problem's facts exposes it: it can no longer be a transfer check."""
    deps.forbid_during_assessment(session)
    problem = get_problem(session, problem_id)
    problem.exposed = True
    session.flush()
    return detail(session, state, problem)


@router.patch("/problems/{problem_id}")
def patch_problem(
    problem_id: str, body: schemas.ProblemPatch, state: deps.State, session: deps.Db
) -> schemas.ProblemDetail:
    """Edit a problem's notes, primary topic and pattern labels.

    Send `topic_id` to override the primary topic (null for "None"),
    `reset_topic` to go back to the automatic topic, and the pattern labels by
    pattern id.
    """
    deps.forbid_during_assessment(session)
    problem = get_problem(session, problem_id)
    sent = body.model_fields_set
    if body.notes is not None:
        problem.notes = body.notes
    if body.reset_topic and "topic_id" in sent:
        raise ApiError(
            422, "VALIDATION", "Send either topic_id or reset_topic, not both"
        )
    if "topic_id" in sent or body.reset_topic:
        if problem.source != Source.LEETCODE.value:
            raise ApiError(422, "VALIDATION", "AtCoder problems have no primary topic")
        if body.reset_topic:
            problem.topic_overridden = False
            assign_topic(problem, state.runtime.manifests.topics)
        else:
            if body.topic_id is not None and session.get(Topic, body.topic_id) is None:
                raise ApiError(
                    422, "VALIDATION", f"topic_id: no topic {body.topic_id!r}"
                )
            problem.topic_id = body.topic_id
            problem.topic_overridden = True
    if body.patterns is not None:
        wanted = list(dict.fromkeys(body.patterns))
        known = set(session.scalars(select(Pattern.id).where(Pattern.id.in_(wanted))))
        if unknown := [p for p in wanted if p not in known]:
            raise ApiError(422, "VALIDATION", f"patterns: no pattern {unknown[0]!r}")
        for row in session.scalars(
            select(ProblemPattern).where(ProblemPattern.problem_id == problem.id)
        ):
            session.delete(row)
        session.flush()
        session.add_all(
            ProblemPattern(problem_id=problem.id, pattern_id=p) for p in wanted
        )
    problem.exposed = True
    session.flush()
    return detail(session, state, problem)


# ---------------------------------------------------------------- suggested paths


def solution_files(
    repo_root: Path, roots: Iterable[str] = (LEETCODE_SRC, ATCODER_SRC)
) -> list[str]:
    """Repo-relative solution files under the LeetCode and AtCoder source folders.

    Only .py, .go and .ts files count; dot folders are skipped.
    """
    extensions = tuple(EXTENSIONS.values())
    found: list[str] = []
    for root in roots:
        for folder, subfolders, files in os.walk(repo_root / root):
            subfolders[:] = sorted(d for d in subfolders if not d.startswith("."))
            here = Path(folder).relative_to(repo_root).as_posix()
            found.extend(
                f"{here}/{name}" for name in sorted(files) if name.endswith(extensions)
            )
    return found


@router.get("/problems/{problem_id}/suggested-path")
def suggested_path(
    problem_id: str,
    state: deps.State,
    session: deps.Db,
    language: Language = Language.PYTHON,
) -> schemas.SuggestedPath:
    """Appendix D.

    During a hidden assessment, only the assessment's own problem gets a
    suggestion: a folder name gives a topic away.
    """
    assessment = deps.assessment_attempt(session)
    if assessment is not None and assessment.problem_id != problem_id:
        raise hidden_assessment()
    problem = get_problem(session, problem_id)
    catalog = state.runtime.manifests.topics
    folder = catalog.get(problem.topic_id).folder if problem.topic_id else None
    if problem.source == Source.ATCODER.value and problem.contest is None:
        raise ApiError(422, "VALIDATION", "This AtCoder problem has no contest")
    suggestion = suggest_path(
        source=Source(problem.source),
        external_id=problem.external_id,
        title=problem.title,
        language=language,
        existing=solution_files(state.runtime.paths.repo_root),
        number=problem.number,
        label=Difficulty(problem.difficulty_label)
        if problem.difficulty_label
        else None,
        topic_folder=folder,
        contest=problem.contest,
    )
    return schemas.SuggestedPath(path=suggestion.path, exists=suggestion.exists)
