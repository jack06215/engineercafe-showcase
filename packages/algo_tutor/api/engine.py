"""Store rows → the domain's inputs, and domain results → store rows.

Levels are replayed and plans are built from these on every request
(SPEC §7–§10); nothing here decides anything itself. Store and domain both
have a `ReviewTarget`, a `StudyList` and a `ListEntry`, so both modules are
imported whole and named in full.
"""

from collections import Counter
from datetime import date

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import facts
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.domain import ladder, plan, review
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
    Difficulty,
    DifficultyFeel,
    Help,
    Outcome,
    ReviewAction,
    ReviewStage,
    Source,
)
from packages.algo_tutor.store import models
from packages.algo_tutor.store.timeutil import local_date, new_id, parse_iso

_UNFINISHED = (AttemptStatus.ACTIVE.value, AttemptStatus.PAUSED.value)


def settings_row(session: Session) -> models.Settings:
    """Return the single settings row."""
    return session.get_one(models.Settings, 1)


def today(state: AppState, settings: models.Settings) -> date:
    """The study date now, in the learner's timezone."""
    return local_date(state.clock(), settings.timezone)


def _day(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


def _text(day: date | None) -> str | None:
    return None if day is None else day.isoformat()


# ---------------------------------------------------------------- review targets


def target_from_row(row: models.ReviewTarget) -> review.ReviewTarget:
    """Convert a stored review target to the domain type."""
    return review.ReviewTarget(
        problem_id=row.problem_id,
        recommended_date=_day(row.recommended_date),
        effective_date=_day(row.effective_date),
        action=ReviewAction(row.action),
        stage=ReviewStage(row.stage),
        version=row.version,
        solo_transfer_streak=row.solo_transfer_streak,
    )


def target_row(session: Session, problem_id: str) -> models.ReviewTarget | None:
    """Return the stored review target of *problem_id*, if any."""
    return session.scalars(
        select(models.ReviewTarget).where(models.ReviewTarget.problem_id == problem_id)
    ).first()


def target_of(session: Session, problem_id: str) -> review.ReviewTarget | None:
    """Return the review target of *problem_id* as the domain type, if any."""
    row = target_row(session, problem_id)
    return None if row is None else target_from_row(row)


def write_target(session: Session, target: review.ReviewTarget) -> models.ReviewTarget:
    """Insert or update the problem's review target with the domain's values.

    The domain has already bumped the version.
    """
    row = target_row(session, target.problem_id)
    if row is None:
        row = models.ReviewTarget(id=new_id(), problem_id=target.problem_id)
        session.add(row)
    row.recommended_date = _text(target.recommended_date)
    row.effective_date = _text(target.effective_date)
    row.action = target.action.value
    row.stage = target.stage.value
    row.version = target.version
    row.solo_transfer_streak = target.solo_transfer_streak
    session.flush()
    return row


# ---------------------------------------------------------------- the library as planning sees it


def problem_facts(session: Session, manifests: Manifests) -> list[plan.ProblemFacts]:
    """Every problem in the library, one `ProblemFacts` each."""
    problems = session.scalars(select(models.Problem)).all()
    fitted = facts.estimates(session)
    # A comprehension, not dict(): a Result has .keys() and would be read as a mapping.
    popularity = {
        problem_id: percentile
        for problem_id, percentile in session.execute(
            select(
                models.ProblemPopularity.problem_id, models.ProblemPopularity.percentile
            )
        ).tuples()
    }
    attempted: Counter[str] = Counter()
    completed: Counter[str] = Counter()
    unfinished: set[str] = set()
    for problem_id, status, n in session.execute(
        select(models.Attempt.problem_id, models.Attempt.status, func.count()).group_by(
            models.Attempt.problem_id, models.Attempt.status
        )
    ).tuples():
        attempted[problem_id] += n
        if status == AttemptStatus.COMPLETED.value:
            completed[problem_id] += n
        else:
            unfinished.add(problem_id)
    targets = {
        row.problem_id: target_from_row(row)
        for row in session.scalars(select(models.ReviewTarget))
    }
    return [
        plan.ProblemFacts(
            id=p.id,
            source=Source(p.source),
            title=p.title,
            topic_id=p.topic_id if p.source == Source.LEETCODE else None,
            rating=facts.rating_of(p, manifests, fitted.get(p.id)),
            popularity=popularity.get(p.id),
            paid_only=p.paid_only,
            exposed=p.exposed,
            attempted=attempted[p.id] > 0,
            completed_attempts=completed[p.id],
            in_unfinished_attempt=p.id in unfinished,
            target=targets.get(p.id),
        )
        for p in problems
    ]


# ---------------------------------------------------------------- levels


def ladder_attempts(
    session: Session, manifests: Manifests
) -> list[ladder.LadderAttempt]:
    """Completed attempts in replay order: `finished_at`, then insertion."""
    rows = session.execute(
        select(models.Attempt, models.Problem, models.AttemptSignals)
        .join(models.Problem, models.Problem.id == models.Attempt.problem_id)
        .outerjoin(
            models.AttemptSignals, models.AttemptSignals.attempt_id == models.Attempt.id
        )
        .where(models.Attempt.status == AttemptStatus.COMPLETED.value)
        .order_by(models.Attempt.finished_at, literal_column("attempts.rowid"))
    ).tuples()
    fitted = facts.estimates(session)
    out: list[ladder.LadderAttempt] = []
    for attempt, problem, joined in rows:
        # The outer join gives None for an attempt without a signals row, but the
        # tuple type that select() infers does not include None.
        signals: models.AttemptSignals | None = joined
        if attempt.finished_at is None or attempt.outcome is None:
            continue
        out.append(
            ladder.LadderAttempt(
                attempt_id=attempt.id,
                finished_at=parse_iso(attempt.finished_at),
                problem_title=problem.title,
                topic_id=problem.topic_id
                if problem.source == Source.LEETCODE
                else None,
                rating=facts.rating_of(problem, manifests, fitted.get(problem.id)),
                label=Difficulty(problem.difficulty_label)
                if problem.difficulty_label
                else None,
                outcome=Outcome(attempt.outcome),
                help=Help(attempt.help),
                active_seconds=attempt.active_seconds,
                confidence=attempt.confidence,
                accepted_first_try=signals.accepted_first_try if signals else None,
                feel=DifficultyFeel(signals.difficulty)
                if signals and signals.difficulty
                else None,
            )
        )
    return out


def levels(
    session: Session, manifests: Manifests, target: int
) -> list[ladder.TopicLevel]:
    """Every topic's level, in curriculum order."""
    order = [t.id for t in manifests.topics.by_curriculum()]
    return ladder.training_levels(ladder_attempts(session, manifests), order, target)


# ---------------------------------------------------------------- lists and the current attempt


def study_list(session: Session, list_id: str | None) -> plan.StudyList | None:
    """An active list as planning reads it, entries in list order."""
    if list_id is None:
        return None
    row = session.get(models.StudyList, list_id)
    if row is None:
        return None
    entries = list(
        session.execute(
            select(models.ListEntry, models.Problem.title)
            .join(models.Problem, models.Problem.id == models.ListEntry.problem_id)
            .where(models.ListEntry.list_id == list_id)
            .order_by(models.ListEntry.position)
        ).tuples()
    )
    starts: dict[str, list[str]] = {}
    for problem_id, started_at in session.execute(
        select(models.Attempt.problem_id, models.Attempt.started_at).where(
            models.Attempt.status == AttemptStatus.COMPLETED.value,
            models.Attempt.problem_id.in_([e.problem_id for e, _ in entries]),
        )
    ).tuples():
        starts.setdefault(problem_id, []).append(started_at)
    return plan.StudyList(
        name=row.name,
        entries=tuple(
            plan.ListEntry(
                problem_id=e.problem_id,
                title=title,
                added_at=parse_iso(e.added_at),
                completed_attempt_starts=tuple(
                    parse_iso(s) for s in starts.get(e.problem_id, [])
                ),
            )
            for e, title in entries
        ),
    )


def unfinished_attempt(session: Session) -> models.Attempt | None:
    """Return the active or paused attempt, if there is one."""
    return session.scalars(
        select(models.Attempt).where(models.Attempt.status.in_(_UNFINISHED))
    ).first()


def current_attempt(session: Session) -> plan.CurrentAttempt | None:
    """An unfinished attempt started outside any plan (slot 0, SPEC §10.2)."""
    attempt = unfinished_attempt(session)
    if attempt is None or attempt.plan_item_id is not None:
        return None
    problem = session.get_one(models.Problem, attempt.problem_id)
    return plan.CurrentAttempt(problem.id, problem.title, Source(problem.source))


def plan_context(
    session: Session, state: AppState, settings: models.Settings, day: date
) -> plan.PlanContext:
    """Build the planner context for *day* from the database."""
    manifests = state.runtime.manifests
    return plan.PlanContext(
        today=day,
        target=settings.target_rating,
        catalog=manifests.topics,
        levels=levels(session, manifests, settings.target_rating),
        problems=problem_facts(session, manifests),
        include_paid_only=settings.include_paid_only,
    )


def active_lists(
    session: Session, settings: models.Settings
) -> tuple[plan.StudyList | None, plan.StudyList | None]:
    """The active LeetCode and AtCoder lists."""
    return (
        study_list(session, settings.active_list_leetcode),
        study_list(session, settings.active_list_atcoder),
    )
