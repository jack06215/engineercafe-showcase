"""Training levels and topic notebooks (SPEC §7.3, §11.1, §15).

Every route here is locked during a hidden assessment: a level, a topic
page or its problems would give the check's topic away (SPEC §9).
"""

from collections import Counter

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import deps, engine, facts
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import not_found
from packages.algo_tutor.api.schemas import (
    LevelChange,
    Notebook,
    NotebookPatch,
    NotebookProblem,
    TopicDetail,
    TopicLevel,
    TopicLevels,
)
from packages.algo_tutor.domain import ladder
from packages.algo_tutor.domain.enums import AttemptStatus, Outcome
from packages.algo_tutor.store import models
from packages.algo_tutor.store.timeutil import iso_utc, local_date, parse_iso

router = APIRouter(tags=["topics"])


def level_out(
    topic: models.Topic, level: ladder.TopicLevel, timezone: str
) -> TopicLevel:
    """Return the API view of a topic level."""
    change = level.last_change
    return TopicLevel(
        id=topic.id,
        name=topic.name,
        curriculum=topic.curriculum,
        level=level.level,
        at_target=level.at_target,
        attempts=level.attempts,
        last_change=None
        if change is None
        else LevelChange(
            delta=change.delta,
            attempt_id=change.attempt_id,
            problem_title=change.problem_title,
            rating=change.rating,
            estimated=change.estimated,
            result=change.result,
            study_date=local_date(change.date, timezone),
        ),
    )


def _levels(
    session: Session, state: AppState
) -> tuple[models.Settings, dict[str, ladder.TopicLevel]]:
    settings = engine.settings_row(session)
    levels = engine.levels(session, state.runtime.manifests, settings.target_rating)
    return settings, {lv.topic_id: lv for lv in levels}


def notebook_out(topic: models.Topic) -> Notebook:
    """Return the API view of a topic's notebook."""
    return Notebook(
        cues=topic.cues,
        pitfalls=topic.pitfalls,
        notes=topic.notes,
        version=topic.notebook_version,
        updated_at=parse_iso(topic.notebook_updated_at)
        if topic.notebook_updated_at
        else None,
    )


@router.get("/topics")
def list_topics(session: deps.Db, state: deps.State) -> TopicLevels:
    """The 34 levels, in curriculum order, with the target."""
    deps.forbid_during_assessment(session)
    settings, by_id = _levels(session, state)
    topics = session.scalars(select(models.Topic).order_by(models.Topic.curriculum))
    return TopicLevels(
        target_rating=settings.target_rating,
        topics=[level_out(t, by_id[t.id], settings.timezone) for t in topics],
    )


def _topic(session: Session, topic_id: str) -> models.Topic:
    topic = session.get(models.Topic, topic_id)
    if topic is None:
        raise not_found("Topic")
    return topic


def notebook_problems(
    session: Session, state: AppState, problems: list[models.Problem]
) -> list[NotebookProblem]:
    """Attempted problems only, newest attempt's outcome first in the row."""
    ids = [p.id for p in problems]
    counts: Counter[str] = Counter()
    latest: dict[str, str | None] = {}
    for attempt in session.scalars(
        select(models.Attempt)
        .where(models.Attempt.problem_id.in_(ids))
        .order_by(models.Attempt.started_at)
    ):
        counts[attempt.problem_id] += 1
        if attempt.status == AttemptStatus.COMPLETED.value:
            latest[attempt.problem_id] = attempt.outcome
    tried = [p for p in problems if counts[p.id]]
    ratings = facts.ratings(session, state.runtime.manifests, tried)
    rows = [
        NotebookProblem(
            problem=facts.brief(p, ratings[p.id]),
            attempts=counts[p.id],
            latest_outcome=Outcome(outcome) if (outcome := latest.get(p.id)) else None,
        )
        for p in tried
    ]
    return sorted(rows, key=lambda r: r.problem.title.casefold())


@router.get("/topics/{topic_id}")
def read_topic(topic_id: str, session: deps.Db, state: deps.State) -> TopicDetail:
    """A topic page.

    Unseen problems are only counted, never listed, so browsing can't expose
    them and drain the transfer-check pool.
    """
    deps.forbid_during_assessment(session)
    topic = _topic(session, topic_id)
    settings, by_id = _levels(session, state)
    problems = list(
        session.scalars(
            select(models.Problem).where(models.Problem.topic_id == topic.id)
        )
    )
    listed = notebook_problems(session, state, problems)
    tried = {row.problem.id for row in listed}
    return TopicDetail(
        level=level_out(topic, by_id[topic.id], settings.timezone),
        target_rating=settings.target_rating,
        notebook=notebook_out(topic),
        problems=listed,
        unseen_count=sum(1 for p in problems if p.id not in tried),
    )


@router.patch("/topics/{topic_id}/notebook")
def edit_topic_notebook(
    topic_id: str, body: NotebookPatch, session: deps.Db, state: deps.State
) -> Notebook:
    """Update the sent fields of a topic's notebook."""
    deps.forbid_during_assessment(session)
    topic = _topic(session, topic_id)
    deps.check_version(topic.notebook_version, body.version, "This notebook")
    sent = body.model_fields_set
    for field in ("cues", "pitfalls", "notes"):
        value = getattr(body, field)
        if field in sent and value is not None:
            setattr(topic, field, value)
    topic.notebook_version += 1
    topic.notebook_updated_at = iso_utc(state.clock())
    session.flush()
    return notebook_out(topic)
