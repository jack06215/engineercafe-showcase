"""Pattern pages and the mistake notebook (SPEC §11.2, §11.3).

Pattern pages show common_coding_pattern's README read from the repo on
every view, beside your own cues, pitfalls and notes. Both are locked
during a hidden assessment (SPEC §9).
"""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import deps, facts, schemas
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import not_found
from packages.algo_tutor.domain.enums import AttemptStatus, MistakeLabel, Outcome
from packages.algo_tutor.store.models import Attempt, Pattern, Problem, ProblemPattern
from packages.algo_tutor.store.timeutil import iso_utc, parse_iso

router = APIRouter(tags=["notebooks"])

# How a label reads, so a search for "edge case" finds missed_edge_case.
LABEL_TEXT = {
    MistakeLabel.MISSED_EDGE_CASE: "missed edge case",
    MistakeLabel.WRONG_APPROACH: "wrong approach",
    MistakeLabel.IMPLEMENTATION_BUG: "implementation bug",
}


def notebook(row: Pattern) -> schemas.Notebook:
    return schemas.Notebook(
        cues=row.cues,
        pitfalls=row.pitfalls,
        notes=row.notes,
        version=row.notebook_version,
        updated_at=parse_iso(row.notebook_updated_at)
        if row.notebook_updated_at
        else None,
    )


def attempted_counts(session: Session) -> dict[str, int]:
    """Attempted problems per pattern: the only ones a pattern page lists,
    so browsing it can't expose unseen problems."""
    rows = session.execute(
        select(
            ProblemPattern.pattern_id,
            func.count(func.distinct(ProblemPattern.problem_id)),
        )
        .join(Attempt, Attempt.problem_id == ProblemPattern.problem_id)
        .group_by(ProblemPattern.pattern_id)
    ).tuples()
    return {pattern_id: int(count) for pattern_id, count in rows}


def pattern_summary(row: Pattern, counts: dict[str, int]) -> schemas.PatternSummary:
    return schemas.PatternSummary(
        id=row.id,
        name=row.name,
        position=row.position,
        missing=row.missing,
        problems=counts.get(row.id, 0),
    )


def notebook_problems(
    session: Session, state: AppState, pattern_id: str
) -> list[schemas.NotebookProblem]:
    problems = list(
        session.scalars(
            select(Problem)
            .join(ProblemPattern, ProblemPattern.problem_id == Problem.id)
            .where(ProblemPattern.pattern_id == pattern_id)
            .where(Problem.id.in_(select(Attempt.problem_id)))
            .order_by(Problem.title)
        )
    )
    rated = facts.ratings(session, state.runtime.manifests, problems)
    out = []
    for p in problems:
        attempts = list(
            session.scalars(
                select(Attempt)
                .where(Attempt.problem_id == p.id)
                .order_by(Attempt.started_at)
            )
        )
        outcomes = [
            a.outcome for a in attempts if a.status == AttemptStatus.COMPLETED.value
        ]
        latest = next((o for o in reversed(outcomes) if o is not None), None)
        out.append(
            schemas.NotebookProblem(
                problem=facts.brief(p, rated[p.id]),
                attempts=len(attempts),
                latest_outcome=Outcome(latest) if latest is not None else None,
            )
        )
    return out


def get_pattern(session: Session, pattern_id: str) -> Pattern:
    row = session.get(Pattern, pattern_id)
    if row is None:
        raise not_found("Pattern")
    return row


def read_readme(state: AppState, row: Pattern) -> str | None:
    """The README as it is in the repo now; None when it's gone."""
    path = state.runtime.paths.repo_root / row.readme_path
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


@router.get("/patterns")
def list_patterns(session: deps.Db) -> list[schemas.PatternSummary]:
    deps.forbid_during_assessment(session)
    counts = attempted_counts(session)
    return [
        pattern_summary(p, counts)
        for p in session.scalars(select(Pattern).order_by(Pattern.position))
    ]


@router.get("/patterns/{pattern_id}")
def pattern_page(
    pattern_id: str, state: deps.State, session: deps.Db
) -> schemas.PatternDetail:
    deps.forbid_during_assessment(session)
    row = get_pattern(session, pattern_id)
    return schemas.PatternDetail(
        pattern=pattern_summary(row, attempted_counts(session)),
        readme_path=row.readme_path,
        readme_markdown=read_readme(state, row),
        notebook=notebook(row),
        problems=notebook_problems(session, state, row.id),
    )


@router.patch("/patterns/{pattern_id}/notebook")
def patch_pattern_notebook(
    pattern_id: str, body: schemas.NotebookPatch, state: deps.State, session: deps.Db
) -> schemas.Notebook:
    """Your cues, pitfalls and notes; 409 STALE when `version` is old."""
    deps.forbid_during_assessment(session)
    row = get_pattern(session, pattern_id)
    deps.check_version(row.notebook_version, body.version, "This notebook")
    for name in ("cues", "pitfalls", "notes"):
        value = getattr(body, name)
        if value is not None:
            setattr(row, name, value)
    row.notebook_version += 1
    row.notebook_updated_at = iso_utc(state.clock())
    session.flush()
    return notebook(row)


@router.get("/mistakes")
def mistakes(
    state: deps.State,
    session: deps.Db,
    q: Annotated[str | None, Query(max_length=200)] = None,
    label: MistakeLabel | None = None,
) -> schemas.MistakeList:
    """Completed attempts with a mistake label or a takeaway, newest first;
    `q` searches the title, the takeaway and the labels."""
    deps.forbid_during_assessment(session)
    rows = session.execute(
        select(Attempt, Problem)
        .join(Problem, Problem.id == Attempt.problem_id)
        .where(Attempt.status == AttemptStatus.COMPLETED.value)
        .order_by(Attempt.finished_at.desc(), Attempt.id)
    ).tuples()
    needle = (q or "").strip().casefold()
    picked: list[tuple[Attempt, Problem, list[MistakeLabel]]] = []
    for attempt, problem in rows:
        labels = [MistakeLabel(value) for value in attempt.mistake_labels]
        if not labels and not attempt.takeaway.strip():
            continue
        if label is not None and label not in labels:
            continue
        if needle:
            haystack = " ".join(
                [
                    problem.title,
                    attempt.takeaway,
                    *labels,
                    *(LABEL_TEXT[x] for x in labels),
                ]
            ).casefold()
            if needle not in haystack:
                continue
        picked.append((attempt, problem, labels))
    rated = facts.ratings(session, state.runtime.manifests, [p for _, p, _ in picked])
    return schemas.MistakeList(
        items=[
            schemas.MistakeEntry(
                attempt_id=attempt.id,
                problem=facts.brief(problem, rated[problem.id]),
                finished_at=parse_iso(attempt.finished_at or attempt.started_at),
                mistake_labels=labels,
                takeaway=attempt.takeaway,
            )
            for attempt, problem, labels in picked
        ]
    )
