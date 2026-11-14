"""Attempts (SPEC §6, §9, §12.4–§12.5, §15).

Start, drafts with a linked file or the editor, the server-kept stopwatch,
finish (closeout), cancel, reflection, signals, the report queue and
interview hints. Draft, timer, reflection and signals all answer with the
full `AttemptOut`: the web client's write queue replaces its copy with it.
"""

from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import deps, engine, facts
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import ApiError, not_found
from packages.algo_tutor.api.schemas import (
    AttemptOut,
    AttemptStart,
    AttemptSummary,
    DraftPatch,
    FinishIn,
    FinishOut,
    HintConversation,
    HintIn,
    HintMessage,
    HintReply,
    ReflectionPatch,
    Report,
    Signals,
    SignalsPatch,
    TimerIn,
)
from packages.algo_tutor.domain import constants, review, timer
from packages.algo_tutor.domain.attempts import start_facts
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
    Context,
    Difficulty,
    DifficultyFeel,
    Evidence,
    Help,
    HintLevel,
    HintRole,
    Language,
    MistakeLabel,
    Outcome,
    PlanItemKind,
    PlanItemStatus,
    ReportStatus,
    ReviewChoice,
    Source,
    TutorErrorKind,
)
from packages.algo_tutor.store import models
from packages.algo_tutor.store.timeutil import iso_utc, new_id, parse_iso
from packages.algo_tutor.tutor import hints, worker
from packages.algo_tutor.tutor.llm import TutorError
from packages.algo_tutor.tutor.report import ProblemInfo, from_column

router = APIRouter(tags=["attempts"])

_UNFINISHED = (AttemptStatus.ACTIVE.value, AttemptStatus.PAUSED.value)


# ---------------------------------------------------------------- reading


def _ts(text: str | None) -> datetime | None:
    return None if text is None else parse_iso(text)


def get_attempt(session: Session, attempt_id: str) -> models.Attempt:
    attempt = session.get(models.Attempt, attempt_id)
    if attempt is None:
        raise not_found("Attempt")
    return attempt


def _hint_levels(session: Session, attempt_id: str) -> list[HintLevel | None]:
    return [
        HintLevel(level) if level else None
        for level in session.scalars(
            select(models.HintMessage.level).where(
                models.HintMessage.attempt_id == attempt_id
            )
        )
    ]


def report_out(attempt: models.Attempt) -> Report:
    sections = from_column(attempt.report)
    return Report(
        status=ReportStatus(attempt.report_status),
        summary=sections.summary if sections else None,
        strengths=sections.strengths if sections else None,
        improvements=sections.improvements if sections else None,
        complexity=sections.complexity if sections else None,
        practice=sections.practice if sections else None,
        error_kind=TutorErrorKind(attempt.report_error)
        if attempt.report_error
        else None,
        error_message=attempt.report_error_message,
        model=attempt.report_model,
        reported_at=_ts(attempt.reported_at),
    )


def signals_out(session: Session, attempt_id: str) -> Signals:
    row = session.get(models.AttemptSignals, attempt_id)
    return Signals(
        accepted_first_try=row.accepted_first_try if row else None,
        difficulty=DifficultyFeel(row.difficulty) if row and row.difficulty else None,
    )


def problem_patterns(session: Session, problem_id: str) -> list[str]:
    return list(
        session.scalars(
            select(models.ProblemPattern.pattern_id)
            .where(models.ProblemPattern.problem_id == problem_id)
            .order_by(models.ProblemPattern.pattern_id)
        )
    )


def attempt_out(
    session: Session, state: AppState, attempt: models.Attempt
) -> AttemptOut:
    """The full attempt. While a hidden assessment runs, completed attempts
    lose their reflection, signals and report, and no attempt shows the
    problem's patterns (SPEC §9)."""
    hidden = deps.assessment_attempt(session) is not None
    problem = session.get_one(models.Problem, attempt.problem_id)
    completed = attempt.status == AttemptStatus.COMPLETED.value
    show_after = completed and not hidden
    return AttemptOut(
        id=attempt.id,
        problem=facts.brief_one(session, state.runtime.manifests, problem),
        plan_item_id=attempt.plan_item_id,
        context=Context(attempt.context),
        evidence=Evidence(attempt.evidence),
        status=AttemptStatus(attempt.status),
        version=attempt.version,
        language=Language(attempt.language),
        code=attempt.code,
        solution_path=attempt.solution_path,
        code_copied_at=_ts(attempt.code_copied_at),
        notes=attempt.notes,
        outcome=Outcome(attempt.outcome) if attempt.outcome else None,
        help=Help(attempt.help),
        confidence=attempt.confidence,
        active_seconds=attempt.active_seconds,
        gap_seconds=attempt.gap_seconds or 0,
        running_since=_ts(attempt.running_since),
        last_heartbeat_at=_ts(attempt.last_heartbeat_at),
        needs_gap_decision=attempt.needs_gap_decision,
        started_at=parse_iso(attempt.started_at),
        finished_at=_ts(attempt.finished_at),
        study_date=date.fromisoformat(attempt.study_date),
        next_review_date=date.fromisoformat(attempt.next_review_date)
        if attempt.next_review_date
        else None,
        strongest_hint=hints.strongest(_hint_levels(session, attempt.id)),
        takeaway=attempt.takeaway if show_after else None,
        mistake_labels=[MistakeLabel(m) for m in attempt.mistake_labels]
        if show_after
        else None,
        signals=signals_out(session, attempt.id) if show_after else None,
        patterns=None if hidden else problem_patterns(session, problem.id),
        report=report_out(attempt) if show_after else None,
        server_now=state.clock(),
    )


def summary_out(attempt: models.Attempt) -> AttemptSummary:
    return AttemptSummary(
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
        finished_at=_ts(attempt.finished_at),
        study_date=date.fromisoformat(attempt.study_date),
    )


@router.get("/attempts")
def list_attempts(
    session: deps.Db,
    problem_id: Annotated[str | None, Query()] = None,
) -> list[AttemptSummary]:
    """Newest first; optionally one problem's."""
    query = select(models.Attempt).order_by(
        models.Attempt.started_at.desc(), literal_column("attempts.rowid").desc()
    )
    if problem_id is not None:
        query = query.where(models.Attempt.problem_id == problem_id)
    return [summary_out(a) for a in session.scalars(query)]


@router.get("/attempts/{attempt_id}")
def read_attempt(attempt_id: str, session: deps.Db, state: deps.State) -> AttemptOut:
    return attempt_out(session, state, get_attempt(session, attempt_id))


# ---------------------------------------------------------------- linked solution files (§6.4)


def _invalid(message: str) -> ApiError:
    return ApiError(400, "SOLUTION_PATH_INVALID", message)


def normalise_path(text: str) -> str:
    """A repo-relative POSIX path, or SOLUTION_PATH_INVALID."""
    raw = text.strip()
    if not raw:
        raise _invalid("The solution path is empty")
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith("~"):
        raise _invalid("Give the path relative to the repo root")
    parts = [p for p in path.parts if p != "."]
    if not parts or ".." in parts:
        raise _invalid("The path must stay inside the repo")
    return "/".join(parts)


def read_solution(repo_root: Path, relative: str) -> str:
    """The linked file's text: inside the repo once symlinks are resolved,
    a regular file, at most 1,000,000 bytes, UTF-8 (SPEC §6.4)."""
    root = repo_root.resolve()
    candidate = root / relative
    if not candidate.exists():
        raise ApiError(
            400,
            "SOLUTION_FILE_MISSING",
            f"{relative} doesn't exist; fix the path or switch to the editor",
        )
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise _invalid(f"{relative} points outside the repo")
    if not resolved.is_file():
        raise _invalid(f"{relative} isn't a regular file")
    if resolved.stat().st_size > constants.MAX_SOLUTION_FILE_BYTES:
        raise _invalid(
            f"{relative} is over {constants.MAX_SOLUTION_FILE_BYTES:,} bytes"
        )
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid(f"{relative} isn't UTF-8 text") from exc


def _copy_linked(state: AppState, attempt: models.Attempt, relative: str) -> None:
    attempt.code = read_solution(state.runtime.paths.repo_root, relative)
    attempt.code_copied_at = iso_utc(state.clock())


# ---------------------------------------------------------------- start


def _check_writable(attempt: models.Attempt, version: int) -> None:
    if attempt.status == AttemptStatus.COMPLETED.value:
        raise ApiError(
            409, "COMPLETED", "This attempt is finished; its code and result are fixed"
        )
    deps.check_version(attempt.version, version, "This attempt")


@router.post("/attempts", status_code=201)
def start_attempt(
    body: AttemptStart, session: deps.Db, state: deps.State
) -> AttemptOut:
    """Start an attempt (SPEC §6.2). One unfinished attempt app-wide."""
    if engine.unfinished_attempt(session) is not None:
        raise ApiError(
            409, "ACTIVE_ATTEMPT", "Finish or cancel the attempt in progress first"
        )
    problem = session.get(models.Problem, body.problem_id)
    if problem is None:
        raise not_found("Problem")
    item = None
    if body.plan_item_id is not None:
        item = session.get(models.PlanItem, body.plan_item_id)
        if item is None or item.problem_id != problem.id:
            raise not_found("Plan item")
        if item.attempt_id is not None or item.status in (
            PlanItemStatus.COMPLETED,
            PlanItemStatus.SKIPPED,
        ):
            raise ApiError(409, "COMPLETED", "This plan item was already started")
    completed = session.scalar(
        select(func.count())
        .select_from(models.Attempt)
        .where(
            models.Attempt.problem_id == problem.id,
            models.Attempt.status == AttemptStatus.COMPLETED.value,
        )
    )
    # A "Current attempt" row (kind None, no idea checked) left by a cancel
    # is not a transfer check: starting it again is ordinary practice.
    from_check = item is not None and not (item.kind is None and item.review_of is None)
    started = start_facts(
        from_plan=from_check,
        plan_item_kind=PlanItemKind(item.kind)
        if item is not None and item.kind
        else None,
        exposed=problem.exposed,
        has_completed_attempt=bool(completed),
    )
    now = state.clock()
    settings = engine.settings_row(session)
    attempt = models.Attempt(
        id=new_id(),
        problem_id=problem.id,
        plan_item_id=item.id if item else None,
        context=started.context.value,
        status=AttemptStatus.ACTIVE.value,
        evidence=started.evidence.value,
        language=body.language.value,
        running_since=iso_utc(now),
        last_heartbeat_at=iso_utc(now),
        started_at=iso_utc(now),
        study_date=engine.today(state, settings).isoformat(),
        mistake_labels=[],
    )
    session.add(attempt)
    problem.exposed = True
    if item is not None:
        for other in session.scalars(
            select(models.PlanItem).where(
                models.PlanItem.plan_id == item.plan_id,
                models.PlanItem.status == PlanItemStatus.ACTIVE.value,
                models.PlanItem.id != item.id,
            )
        ):
            other.status = PlanItemStatus.QUEUED.value
        item.status = PlanItemStatus.ACTIVE.value
        item.attempt_id = attempt.id
        plan = session.get_one(models.DailyPlan, item.plan_id)
        plan.version += 1
    session.flush()
    return attempt_out(session, state, attempt)


# ---------------------------------------------------------------- drafts and the stopwatch


@router.patch("/attempts/{attempt_id}/draft")
def save_draft(
    attempt_id: str, body: DraftPatch, session: deps.Db, state: deps.State
) -> AttemptOut:
    """Autosave (SPEC §6.5). A linked file is copied at every save."""
    attempt = get_attempt(session, attempt_id)
    _check_writable(attempt, body.version)
    sent = body.model_fields_set
    if "solution_path" in sent:
        if body.solution_path is None:
            attempt.solution_path = None
        else:
            relative = normalise_path(body.solution_path)
            _copy_linked(state, attempt, relative)
            attempt.solution_path = relative
    elif attempt.solution_path is not None:
        # A file that vanished mid-attempt only fails at finish.
        try:
            _copy_linked(state, attempt, attempt.solution_path)
        except ApiError:
            pass
    if "code" in sent and body.code is not None and attempt.solution_path is None:
        attempt.code = body.code
    if "notes" in sent and body.notes is not None:
        attempt.notes = body.notes
    if "language" in sent and body.language is not None:
        attempt.language = body.language.value
    attempt.version += 1
    session.flush()
    return attempt_out(session, state, attempt)


def timer_state(attempt: models.Attempt) -> timer.TimerState:
    return timer.TimerState(
        status=AttemptStatus(attempt.status),
        active_seconds=attempt.active_seconds,
        gap_seconds=attempt.gap_seconds or 0,
        running_since=_ts(attempt.running_since),
        last_heartbeat_at=_ts(attempt.last_heartbeat_at),
        needs_gap_decision=attempt.needs_gap_decision,
    )


@router.post("/attempts/{attempt_id}/timer")
def timer_action(
    attempt_id: str, body: TimerIn, session: deps.Db, state: deps.State
) -> AttemptOut:
    """Heartbeat, pause or resume (SPEC §6.3)."""
    attempt = get_attempt(session, attempt_id)
    _check_writable(attempt, body.version)
    try:
        after = timer.apply_timer(
            timer_state(attempt), body.action, state.clock(), body.include_gap
        )
    except timer.GapDecisionRequired as exc:
        raise ApiError(409, "GAP_DECISION", str(exc)) from exc
    attempt.status = after.status.value
    attempt.active_seconds = after.active_seconds
    attempt.gap_seconds = after.gap_seconds
    attempt.running_since = (
        iso_utc(after.running_since) if after.running_since else None
    )
    attempt.last_heartbeat_at = (
        iso_utc(after.last_heartbeat_at) if after.last_heartbeat_at else None
    )
    attempt.needs_gap_decision = after.needs_gap_decision
    attempt.version += 1
    session.flush()
    return attempt_out(session, state, attempt)


# ---------------------------------------------------------------- finish (closeout, §6.6)


def promote_next(session: Session, plan_id: str) -> None:
    """Make the first queued item active if none is (LeetCode lane first)."""
    items = session.scalars(
        select(models.PlanItem).where(models.PlanItem.plan_id == plan_id)
    ).all()
    if any(i.status == PlanItemStatus.ACTIVE.value for i in items):
        return
    queued = sorted(
        (i for i in items if i.status == PlanItemStatus.QUEUED.value),
        key=lambda i: (i.lane != "leetcode", i.position),
    )
    if queued:
        queued[0].status = PlanItemStatus.ACTIVE.value


def _finish(
    session: Session,
    state: AppState,
    attempt: models.Attempt,
    body: FinishIn,
    background: BackgroundTasks,
) -> FinishOut:
    _check_writable(attempt, body.version)
    if attempt.solution_path is not None:
        _copy_linked(state, attempt, attempt.solution_path)
    elif body.code is not None:
        attempt.code = body.code
    if not attempt.code.strip():
        raise ApiError(
            422, "VALIDATION", "code: paste your solution code before saving"
        )
    if body.review_choice is ReviewChoice.MANUAL and body.review_date is None:
        raise ApiError(
            422, "VALIDATION", "review_date: choose a date for the next review"
        )
    problem = session.get_one(models.Problem, attempt.problem_id)
    item = (
        session.get(models.PlanItem, attempt.plan_item_id)
        if attempt.plan_item_id
        else None
    )
    review_of = item.review_of if item is not None else None
    now = state.clock()
    finished = review.review_at_finish(
        problem_id=problem.id,
        source=Source(problem.source),
        outcome=body.outcome,
        help=body.help,
        evidence=Evidence(attempt.evidence),
        study_date=date.fromisoformat(attempt.study_date),
        choice=review.Choice.from_finish(body.review_choice, body.review_date),
        own_target=engine.target_of(session, problem.id),
        review_of=review_of,
        idea_target=engine.target_of(session, review_of) if review_of else None,
    )
    for target in finished.targets:
        engine.write_target(session, target)
    attempt.status = AttemptStatus.COMPLETED.value
    attempt.outcome = body.outcome.value
    attempt.help = body.help.value
    attempt.confidence = body.confidence
    attempt.active_seconds = min(
        timer.parse_mmss(body.time), constants.MAX_ACTIVE_SECONDS
    )
    attempt.language = body.language.value
    attempt.notes = body.notes
    attempt.finished_at = iso_utc(now)
    attempt.next_review_date = (
        finished.next_review.isoformat() if finished.next_review else None
    )
    attempt.running_since = None
    attempt.needs_gap_decision = False
    attempt.gap_seconds = 0
    attempt.version += 1
    problem.exposed = True
    if item is not None:
        item.status = PlanItemStatus.COMPLETED.value
        session.flush()
        promote_next(session, item.plan_id)
        session.get_one(models.DailyPlan, item.plan_id).version += 1
    session.flush()
    if worker.request_report(session, attempt, state.tutor_enabled):
        background.add_task(state.wake_worker)
    return FinishOut(
        attempt=attempt_out(session, state, attempt),
        next_review_date=finished.next_review,
        review_stage=finished.targets[0].stage,
    )


@router.post("/attempts/{attempt_id}/finish", response_model=FinishOut)
def finish_attempt(
    attempt_id: str,
    body: FinishIn,
    request: Request,
    background: BackgroundTasks,
    session: deps.Db,
    state: deps.State,
    key: deps.IdempotencyKey,
) -> JSONResponse:
    """Save the result (SPEC §6.6), once per Idempotency-Key."""
    attempt = get_attempt(session, attempt_id)
    try:
        return deps.idempotent(
            session,
            state,
            key,
            request,
            body,
            lambda: _finish(session, state, attempt, body, background),
        )
    except review.ReviewDateRequired as exc:
        raise ApiError(422, "VALIDATION", str(exc)) from exc


# ---------------------------------------------------------------- cancel, reflection, signals


@router.delete("/attempts/{attempt_id}", status_code=204)
def cancel_attempt(attempt_id: str, session: deps.Db) -> Response:
    """Delete an unfinished attempt and unlink its plan item (SPEC §6.1)."""
    attempt = get_attempt(session, attempt_id)
    if attempt.status == AttemptStatus.COMPLETED.value:
        raise ApiError(409, "COMPLETED", "A saved attempt can't be cancelled")
    for item in session.scalars(
        select(models.PlanItem).where(models.PlanItem.attempt_id == attempt.id)
    ):
        item.attempt_id = None
        session.get_one(models.DailyPlan, item.plan_id).version += 1
    session.execute(
        delete(models.HintMessage).where(models.HintMessage.attempt_id == attempt.id)
    )
    session.delete(attempt)
    session.flush()
    return Response(status_code=204)


def _completed(attempt: models.Attempt) -> None:
    if attempt.status != AttemptStatus.COMPLETED.value:
        raise ApiError(422, "VALIDATION", "Save the attempt first")


@router.patch("/attempts/{attempt_id}/reflection")
def save_reflection(
    attempt_id: str, body: ReflectionPatch, session: deps.Db, state: deps.State
) -> AttemptOut:
    """Mistake labels and the takeaway (SPEC §6.7), versioned."""
    attempt = get_attempt(session, attempt_id)
    _completed(attempt)
    deps.check_version(attempt.version, body.version, "This attempt")
    labels = list(dict.fromkeys(body.mistake_labels))
    attempt.mistake_labels = [label.value for label in labels]
    attempt.takeaway = body.takeaway
    attempt.version += 1
    session.flush()
    return attempt_out(session, state, attempt)


@router.patch("/attempts/{attempt_id}/signals")
def save_signals(
    attempt_id: str, body: SignalsPatch, session: deps.Db, state: deps.State
) -> AttemptOut:
    """First-try acceptance and how it felt (SPEC §6.7). Not versioned; only
    the fields sent change, and null clears one."""
    attempt = get_attempt(session, attempt_id)
    _completed(attempt)
    row = session.get(models.AttemptSignals, attempt.id)
    if row is None:
        row = models.AttemptSignals(
            attempt_id=attempt.id, recorded_at=iso_utc(state.clock())
        )
        session.add(row)
    sent = body.model_fields_set
    if "accepted_first_try" in sent:
        row.accepted_first_try = body.accepted_first_try
    if "difficulty" in sent:
        row.difficulty = body.difficulty.value if body.difficulty else None
    row.recorded_at = iso_utc(state.clock())
    session.flush()
    return attempt_out(session, state, attempt)


# ---------------------------------------------------------------- the report (§12.4)


def _tutor_off() -> ApiError:
    return ApiError(
        503,
        "TUTOR_UNAVAILABLE",
        "Algo-chan is off (tutor.enabled in config.yaml)",
        TutorErrorKind.DISABLED,
    )


@router.post("/attempts/{attempt_id}/report")
def request_report(
    attempt_id: str, background: BackgroundTasks, session: deps.Db, state: deps.State
) -> Report:
    """ "Ask for a report" / "Try again". Not repeated once a report exists."""
    attempt = get_attempt(session, attempt_id)
    if not state.tutor_enabled:
        raise _tutor_off()
    _completed(attempt)
    if worker.request_report(session, attempt, True):
        background.add_task(state.wake_worker)
    return report_out(attempt)


# ---------------------------------------------------------------- interview hints (§12.5)


def _message_out(row: models.HintMessage) -> HintMessage:
    return HintMessage(
        id=row.id,
        position=row.position,
        role=HintRole(row.role),
        text=row.text,
        stuck_at_seconds=row.stuck_at_seconds,
        level=HintLevel(row.level) if row.level else None,
        hint=row.hint,
        analysis=row.analysis,
        created_at=parse_iso(row.created_at),
    )


def _messages(session: Session, attempt_id: str) -> list[models.HintMessage]:
    return list(
        session.scalars(
            select(models.HintMessage)
            .where(models.HintMessage.attempt_id == attempt_id)
            .order_by(models.HintMessage.position)
        )
    )


@router.get("/attempts/{attempt_id}/hints")
def read_hints(attempt_id: str, session: deps.Db) -> HintConversation:
    get_attempt(session, attempt_id)
    rows = _messages(session, attempt_id)
    return HintConversation(
        messages=[_message_out(r) for r in rows],
        strongest_level=hints.strongest(
            [HintLevel(r.level) if r.level else None for r in rows]
        ),
    )


def _hint_input(
    session: Session, state: AppState, attempt: models.Attempt, text: str
) -> hints.HintInput:
    """Never the topic, tags or patterns (SPEC §9, §12.5)."""
    problem = session.get_one(models.Problem, attempt.problem_id)
    code = attempt.code
    if attempt.solution_path is not None:
        try:
            code = read_solution(state.runtime.paths.repo_root, attempt.solution_path)
        except ApiError:
            pass  # the last copy will do
    history = tuple(
        hints.Message(HintRole(r.role), r.text, r.stuck_at_seconds)
        for r in _messages(session, attempt.id)
    )
    return hints.HintInput(
        problem=ProblemInfo(
            title=problem.title,
            url=problem.url,
            source=Source(problem.source),
            difficulty=Difficulty(problem.difficulty_label)
            if problem.difficulty_label
            else None,
        ),
        language=Language(attempt.language),
        code=code,
        notes=attempt.notes,
        stuck_at_seconds=timer.current_seconds(timer_state(attempt), state.clock()),
        history=history,
        message=text,
    )


@router.post("/attempts/{attempt_id}/hints")
def ask_for_hint(attempt_id: str, body: HintIn, state: deps.State) -> HintReply:
    """Send a message to Algo-chan during an attempt. The model call runs
    between two short transactions, so a slow reply never holds the
    database: heartbeats and drafts carry on meanwhile."""
    if not state.tutor_enabled:
        raise _tutor_off()
    sessions = state.runtime.sessions
    with sessions() as session, session.begin():
        attempt = get_attempt(session, attempt_id)
        if attempt.status == AttemptStatus.COMPLETED.value:
            raise ApiError(409, "COMPLETED", "Hints are for an attempt in progress")
        hint_input = _hint_input(session, state, attempt, body.text)
    new_stuck = hints.is_new_stuck(hint_input.history, hint_input.stuck_at_seconds)
    task = state.runtime.config.tutor.task("hint")
    try:
        answer = hints.generate(state.chat_factory(task), task, hint_input)
    except TutorError as failure:
        raise ApiError(
            503, "TUTOR_UNAVAILABLE", failure.message, failure.kind
        ) from failure
    reply = answer.value
    with sessions() as session, session.begin():
        attempt = get_attempt(session, attempt_id)
        if attempt.status == AttemptStatus.COMPLETED.value:
            raise ApiError(
                409, "COMPLETED", "The attempt was saved while Algo-chan was answering"
            )
        now = iso_utc(state.clock())
        position = len(_messages(session, attempt.id))
        session.add(
            models.HintMessage(
                id=new_id(),
                attempt_id=attempt.id,
                position=position,
                role=HintRole.LEARNER.value,
                text=body.text,
                stuck_at_seconds=hint_input.stuck_at_seconds,
                created_at=now,
            )
        )
        tutor_row = models.HintMessage(
            id=new_id(),
            attempt_id=attempt.id,
            position=position + 1,
            role=HintRole.TUTOR.value,
            text=reply.reply,
            level=reply.hint_level.value,
            hint=reply.hint,
            analysis=reply.analysis,
            created_at=now,
        )
        session.add(tutor_row)
        block = hints.notes_block(reply, hint_input.stuck_at_seconds, new_stuck)
        attempt.notes = hints.append_to_notes(attempt.notes, block, new_stuck)[
            : constants.MAX_NOTES_CHARS
        ]
        attempt.version += 1
        session.flush()
        levels = _hint_levels(session, attempt.id)
        return HintReply(
            message=_message_out(tutor_row),
            attempt_version=attempt.version,
            notes=attempt.notes,
            strongest_level=hints.strongest(levels),
        )
