"""The desk and the daily plan (SPEC §10, §14 Desk, §15).

Plans are made lazily by `ensure`, one per (date, timezone), and never
rebuilt automatically once changed or filled. Every change bumps the plan's
version; writes carry the version they saw (409 STALE otherwise).
"""

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import deps, engine, facts
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import ApiError, not_found
from packages.algo_tutor.api.routes_attempts import promote_next, signals_out
from packages.algo_tutor.api.schemas import (
    ActiveAttemptBrief,
    Desk,
    DispositionIn,
    PlanItemOut,
    PlanOut,
    PlanVersionIn,
    ReorderIn,
)
from packages.algo_tutor.domain import plan, review
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
    Context,
    Disposition,
    Lane,
    PlanItemKind,
    PlanItemStatus,
    ReviewAction,
)
from packages.algo_tutor.store import models
from packages.algo_tutor.store.timeutil import new_id

router = APIRouter(tags=["plans"])

_LANE_ORDER = {Lane.LEETCODE.value: 0, Lane.ATCODER.value: 1}
_DONE = (PlanItemStatus.COMPLETED.value, PlanItemStatus.SKIPPED.value)


# ---------------------------------------------------------------- reading


def plan_items(session: Session, plan_id: str) -> list[models.PlanItem]:
    rows = session.scalars(
        select(models.PlanItem).where(models.PlanItem.plan_id == plan_id)
    ).all()
    return sorted(rows, key=lambda i: (_LANE_ORDER[i.lane], i.position))


def is_check(item: models.PlanItem) -> bool:
    """A transfer check, a repair or practice after a struggle, or a due AtCoder review."""
    return item.review_of is not None or item.reason == plan.ATCODER_REVIEW_REASON


def plan_out(session: Session, state: AppState, row: models.DailyPlan) -> PlanOut:
    """`review_of` never leaves the server: it would name a transfer check's idea."""
    items = plan_items(session, row.id)
    problems = {
        p.id: p
        for p in session.scalars(
            select(models.Problem).where(
                models.Problem.id.in_([i.problem_id for i in items])
            )
        )
    }
    ratings = facts.ratings(session, state.runtime.manifests, problems.values())
    out = []
    for i in items:
        finished = (
            i.status == PlanItemStatus.COMPLETED.value and i.attempt_id is not None
        )
        out.append(
            PlanItemOut(
                id=i.id,
                lane=Lane(i.lane),
                position=i.position,
                problem=facts.brief(problems[i.problem_id], ratings[i.problem_id]),
                attempt_id=i.attempt_id,
                status=PlanItemStatus(i.status),
                reason=i.reason,
                kind=PlanItemKind(i.kind) if i.kind else None,
                disposition=Disposition(i.disposition) if i.disposition else None,
                is_check=is_check(i),
                signals=signals_out(session, i.attempt_id)
                if finished and i.attempt_id
                else None,
            )
        )
    return PlanOut(
        id=row.id,
        plan_date=date.fromisoformat(row.date),
        timezone=row.timezone,
        version=row.version,
        items=out,
    )


def find_plan(session: Session, day: date, timezone: str) -> models.DailyPlan | None:
    return session.scalars(
        select(models.DailyPlan).where(
            models.DailyPlan.date == day.isoformat(),
            models.DailyPlan.timezone == timezone,
        )
    ).first()


def get_plan(session: Session, plan_id: str) -> models.DailyPlan:
    row = session.get(models.DailyPlan, plan_id)
    if row is None:
        raise not_found("Plan")
    return row


def current_plan(session: Session, state: AppState) -> models.DailyPlan | None:
    """The plan holding the attempt in progress, else today's."""
    attempt = engine.unfinished_attempt(session)
    if attempt is not None and attempt.plan_item_id is not None:
        item = session.get(models.PlanItem, attempt.plan_item_id)
        if item is not None:
            return session.get_one(models.DailyPlan, item.plan_id)
    settings = engine.settings_row(session)
    return find_plan(session, engine.today(state, settings), settings.timezone)


# ---------------------------------------------------------------- the desk


@router.get("/desk")
def desk(session: deps.Db, state: deps.State) -> Desk:
    """Today's plan in both lanes, checks due and any attempt in progress.
    During a hidden assessment only "Assessment in progress" + Resume."""
    settings = engine.settings_row(session)
    day = engine.today(state, settings)
    attempt = engine.unfinished_attempt(session)
    if attempt is not None and attempt.context == Context.MIXED.value:
        return Desk(
            hidden_assessment=True,
            active_attempt=ActiveAttemptBrief(
                id=attempt.id,
                problem_title=None,
                context=Context.MIXED,
                status=AttemptStatus(attempt.status),
            ),
            today=day,
            plan=None,
            left_today=0,
            total_today=0,
            checks_due=0,
            bank_empty=False,
        )
    active = None
    if attempt is not None:
        problem = session.get_one(models.Problem, attempt.problem_id)
        active = ActiveAttemptBrief(
            id=attempt.id,
            problem_title=problem.title,
            context=Context(attempt.context),
            status=AttemptStatus(attempt.status),
        )
    row = current_plan(session, state)
    out = plan_out(session, state, row) if row is not None else None
    items = out.items if out is not None else []
    live = [i for i in items if i.status is not PlanItemStatus.SKIPPED]
    checks_due = session.scalar(
        select(func.count())
        .select_from(models.ReviewTarget)
        .where(
            models.ReviewTarget.action != ReviewAction.NONE.value,
            models.ReviewTarget.effective_date.is_not(None),
            models.ReviewTarget.effective_date <= day.isoformat(),
        )
    )
    return Desk(
        hidden_assessment=False,
        active_attempt=active,
        today=day,
        plan=out,
        left_today=sum(1 for i in live if i.status is not PlanItemStatus.COMPLETED),
        total_today=len(live),
        checks_due=int(checks_due or 0),
        bank_empty=settings.bank_status is None,
    )


# ---------------------------------------------------------------- making and re-making the plan


def _insert(
    session: Session, plan_id: str, items: list[plan.PlannedItem]
) -> list[models.PlanItem]:
    rows = [
        models.PlanItem(
            id=new_id(),
            plan_id=plan_id,
            lane=i.lane.value,
            position=i.position,
            problem_id=i.problem_id,
            status=i.status.value,
            reason=i.reason,
            kind=i.kind.value if i.kind else None,
            review_of=i.review_of,
        )
        for i in items
    ]
    session.add_all(rows)
    session.flush()
    return rows


def ensure_plan(session: Session, state: AppState) -> models.DailyPlan:
    """Today's plan, made if needed (SPEC §10.1)."""
    attempt = engine.unfinished_attempt(session)
    if attempt is not None and attempt.plan_item_id is not None:
        item = session.get(models.PlanItem, attempt.plan_item_id)
        if item is not None:
            return session.get_one(models.DailyPlan, item.plan_id)
    settings = engine.settings_row(session)
    day = engine.today(state, settings)
    row = find_plan(session, day, settings.timezone)
    if row is not None and (row.version != 1 or plan_items(session, row.id)):
        return row
    if row is None:
        row = models.DailyPlan(
            id=new_id(), date=day.isoformat(), timezone=settings.timezone, version=1
        )
        session.add(row)
        session.flush()
    leetcode, atcoder = engine.active_lists(session, settings)
    current = engine.current_attempt(session)
    planned = plan.build_plan(
        engine.plan_context(session, state, settings, day),
        questions_per_day=settings.questions_per_day,
        atcoder_per_day=settings.atcoder_per_day,
        leetcode_list=leetcode,
        atcoder_list=atcoder,
        current=current,
    )
    rows = _insert(session, row.id, planned)
    if attempt is not None and current is not None:
        # The unplanned attempt in progress is slot 0: link both ways.
        for r in rows:
            if r.problem_id == attempt.problem_id and r.reason == plan.CURRENT_REASON:
                r.attempt_id = attempt.id
                attempt.plan_item_id = r.id
                break
    session.flush()
    return row


@router.post("/plans/today/ensure")
def ensure(session: deps.Db, state: deps.State) -> PlanOut:
    """Locked during a hidden assessment like every plan route: the other
    items' reasons name topics. The desk shows "Assessment in progress"."""
    deps.forbid_during_assessment(session)
    return plan_out(session, state, ensure_plan(session, state))


def existing_items(session: Session, plan_id: str) -> list[plan.ExistingItem]:
    return [
        plan.ExistingItem(
            id=i.id,
            lane=Lane(i.lane),
            position=i.position,
            status=PlanItemStatus(i.status),
            problem_id=i.problem_id,
            reason=i.reason,
            kind=PlanItemKind(i.kind) if i.kind else None,
            review_of=i.review_of,
            started=i.attempt_id is not None or i.status in _DONE,
        )
        for i in plan_items(session, plan_id)
    ]


def _is_today(session: Session, state: AppState, row: models.DailyPlan) -> bool:
    current = current_plan(session, state)
    return current is not None and current.id == row.id


@router.post("/plans/{plan_id}/rebuild", response_model=PlanOut)
def rebuild(
    plan_id: str,
    body: PlanVersionIn,
    request: Request,
    session: deps.Db,
    state: deps.State,
    key: deps.IdempotencyKey,
) -> JSONResponse:
    """ "Re-plan today": keep started and finished items, re-pick the rest."""

    deps.forbid_during_assessment(session)

    def run() -> PlanOut:
        row = get_plan(session, plan_id)
        deps.check_version(row.version, body.version, "The plan")
        if not _is_today(session, state, row):
            raise ApiError(409, "STALE", "Only today's plan can be re-planned")
        settings = engine.settings_row(session)
        leetcode, atcoder = engine.active_lists(session, settings)
        result = plan.rebuild_plan(
            engine.plan_context(session, state, settings, date.fromisoformat(row.date)),
            existing_items(session, row.id),
            questions_per_day=settings.questions_per_day,
            atcoder_per_day=settings.atcoder_per_day,
            leetcode_list=leetcode,
            atcoder_list=atcoder,
        )
        for item_id in result.removed:
            session.delete(session.get_one(models.PlanItem, item_id))
        session.flush()
        _insert(session, row.id, list(result.added))
        row.version += 1
        session.flush()
        return plan_out(session, state, row)

    return deps.idempotent(session, state, key, request, body, run)


# ---------------------------------------------------------------- item actions (§10.4)


def get_item(session: Session, plan_id: str, item_id: str) -> models.PlanItem:
    item = session.get(models.PlanItem, item_id)
    if item is None or item.plan_id != plan_id:
        raise not_found("Plan item")
    return item


@router.post("/plans/{plan_id}/items/{item_id}/activate")
def activate(
    plan_id: str, item_id: str, body: PlanVersionIn, session: deps.Db, state: deps.State
) -> PlanOut:
    """ "Make next": this item becomes the active one."""
    deps.forbid_during_assessment(session)
    row = get_plan(session, plan_id)
    deps.check_version(row.version, body.version, "The plan")
    item = get_item(session, plan_id, item_id)
    if item.status in _DONE:
        raise ApiError(409, "COMPLETED", "This item is finished or skipped")
    attempt = engine.unfinished_attempt(session)
    if attempt is not None and attempt.plan_item_id != item.id:
        raise ApiError(409, "ACTIVE_ATTEMPT", "Finish the attempt in progress first")
    for other in plan_items(session, plan_id):
        if other.status == PlanItemStatus.ACTIVE.value and other.id != item.id:
            other.status = PlanItemStatus.QUEUED.value
    item.status = PlanItemStatus.ACTIVE.value
    row.version += 1
    session.flush()
    return plan_out(session, state, row)


@router.post("/plans/{plan_id}/reorder")
def reorder(
    plan_id: str, body: ReorderIn, session: deps.Db, state: deps.State
) -> PlanOut:
    """New order for one lane: every item of the lane, once."""
    deps.forbid_during_assessment(session)
    row = get_plan(session, plan_id)
    deps.check_version(row.version, body.version, "The plan")
    lane_items = {
        i.id: i for i in plan_items(session, plan_id) if i.lane == body.lane.value
    }
    if sorted(body.item_ids) != sorted(lane_items) or len(set(body.item_ids)) != len(
        body.item_ids
    ):
        raise ApiError(
            422, "VALIDATION", "item_ids: list every item of the lane exactly once"
        )
    for position, item_id in enumerate(body.item_ids):
        lane_items[item_id].position = position
    row.version += 1
    session.flush()
    return plan_out(session, state, row)


@router.post("/plans/{plan_id}/items/{item_id}/disposition")
def disposition(
    plan_id: str, item_id: str, body: DispositionIn, session: deps.Db, state: deps.State
) -> PlanOut:
    """Replace, postpone or skip an unstarted item."""
    deps.forbid_during_assessment(session)
    row = get_plan(session, plan_id)
    deps.check_version(row.version, body.version, "The plan")
    item = get_item(session, plan_id, item_id)
    if item.status in _DONE:
        raise ApiError(409, "COMPLETED", "This item is finished or skipped")
    if item.attempt_id is not None:
        raise ApiError(409, "ACTIVE_ATTEMPT", "This item has been started")
    settings = engine.settings_row(session)
    day = date.fromisoformat(row.date)
    if body.action is Disposition.SNOOZE:
        if body.snooze_until is None or body.snooze_until <= engine.today(
            state, settings
        ):
            raise ApiError(422, "VALIDATION", "snooze_until: choose a date after today")
        engine.write_target(
            session,
            review.snooze_target(
                engine.target_of(session, item.problem_id),
                item.problem_id,
                body.snooze_until,
            ),
        )
    elif body.action is Disposition.SWAP:
        _, atcoder = engine.active_lists(session, settings)
        existing = existing_items(session, plan_id)
        mine = next(e for e in existing if e.id == item.id)
        spec = plan.replacement(
            engine.plan_context(session, state, settings, day), mine, existing, atcoder
        )
        if spec is None:
            raise ApiError(
                409,
                "NO_REPLACEMENT",
                "No other question fits your current training levels",
            )
        lane_positions = [
            i.position
            for i in plan_items(session, plan_id)
            if i.lane == spec.lane.value
        ]
        session.add(
            models.PlanItem(
                id=new_id(),
                plan_id=plan_id,
                lane=spec.lane.value,
                position=max(lane_positions, default=-1) + 1,
                problem_id=spec.problem_id,
                status=item.status,
                reason=spec.reason,
                kind=spec.kind.value if spec.kind else None,
                review_of=spec.review_of,
            )
        )
    was_active = item.status == PlanItemStatus.ACTIVE.value
    item.status = PlanItemStatus.SKIPPED.value
    item.disposition = body.action.value
    session.flush()
    if was_active and body.action is not Disposition.SWAP:
        promote_next(session, plan_id)
    row.version += 1
    session.flush()
    return plan_out(session, state, row)
