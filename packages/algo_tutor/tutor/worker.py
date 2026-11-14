"""The report queue (SPEC §12.4).

The status lives on the attempt (`report_status`), so the queue survives a
restart: `recover` puts `generating` back to `pending` at startup. One
in-process thread takes pending reports oldest first, one at a time. The
model call runs outside any transaction; the result is written only if the
attempt is still `generating` (a cancelled or re-requested job loses).
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from packages.algo_tutor.config import TutorConfig
from packages.algo_tutor.domain.enums import (
    AttemptStatus,
    Difficulty,
    Help,
    Language,
    Outcome,
    ReportStatus,
    Source,
)
from packages.algo_tutor.store.models import Attempt, PlanItem, Problem
from packages.algo_tutor.store.timeutil import iso_utc, now_utc
from packages.algo_tutor.tutor import report
from packages.algo_tutor.tutor.llm import ChatFactory, TutorError, chat_model

_REQUESTABLE = frozenset({ReportStatus.NONE.value, ReportStatus.FAILED.value})


def request_report(session: Session, attempt: Attempt, tutor_enabled: bool) -> bool:
    """Queue a report for a completed attempt.

    False when it isn't queued: the tutor is off, the attempt isn't completed,
    or a report is already pending, generating or done ("not repeated once a
    report exists").
    """
    if not tutor_enabled or attempt.status != AttemptStatus.COMPLETED.value:
        return False
    if attempt.report_status not in _REQUESTABLE:
        return False
    attempt.report_status = ReportStatus.PENDING.value
    attempt.report_error = None
    attempt.report_error_message = None
    session.flush()
    return True


def recover(session: Session) -> int:
    """At startup: reports cut off mid-generation go back in the queue."""
    result = session.execute(
        update(Attempt)
        .where(Attempt.report_status == ReportStatus.GENERATING.value)
        .values(report_status=ReportStatus.PENDING.value)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def pending_count(session: Session) -> int:
    """Return how many attempts wait for a report or are generating one."""
    return len(
        session.scalars(
            select(Attempt.id).where(
                Attempt.report_status.in_(
                    [ReportStatus.PENDING.value, ReportStatus.GENERATING.value]
                )
            )
        ).all()
    )


@dataclass(frozen=True)
class Job:
    """One report to generate for an attempt."""

    attempt_id: str
    report_input: report.ReportInput


def _problem_info(problem: Problem) -> report.ProblemInfo:
    label = Difficulty(problem.difficulty_label) if problem.difficulty_label else None
    return report.ProblemInfo(problem.title, problem.url, Source(problem.source), label)


def build_input(session: Session, attempt: Attempt) -> report.ReportInput:
    """The SPEC §12.4 input for one completed attempt."""
    problem = session.get_one(Problem, attempt.problem_id)
    earlier = session.scalars(
        select(Attempt)
        .where(
            Attempt.problem_id == attempt.problem_id,
            Attempt.id != attempt.id,
            Attempt.status == AttemptStatus.COMPLETED.value,
            Attempt.finished_at <= (attempt.finished_at or ""),
        )
        .order_by(Attempt.finished_at.desc())
        .limit(report.HISTORY_LIMIT)
    ).all()
    check_of = None
    if attempt.plan_item_id is not None:
        item = session.get(PlanItem, attempt.plan_item_id)
        if item is not None and item.review_of is not None:
            original = session.get(Problem, item.review_of)
            if original is not None:
                check_of = report.CheckOf(
                    original.title, "transfer" if item.kind is None else "practice"
                )
    return report.ReportInput(
        problem=_problem_info(problem),
        attempt=report.AttemptInfo(
            code=attempt.code,
            notes=attempt.notes,
            language=Language(attempt.language),
            outcome=Outcome(attempt.outcome or Outcome.STOPPED),
            help=Help(attempt.help),
            time=report.mmss(attempt.active_seconds),
            confidence=attempt.confidence,
        ),
        takeaway=attempt.takeaway,
        history=tuple(
            report.EarlierAttempt(
                study_date=date.fromisoformat(e.study_date),
                outcome=Outcome(e.outcome or Outcome.STOPPED),
                help=Help(e.help),
                time=report.mmss(e.active_seconds),
                confidence=e.confidence,
                language=Language(e.language),
                notes=e.notes,
                code=e.code,
            )
            for e in earlier
        ),
        check_of=check_of,
    )


def claim(session: Session) -> Job | None:
    """Mark the oldest pending report `generating` and gather its input."""
    attempt = session.scalars(
        select(Attempt)
        .where(Attempt.report_status == ReportStatus.PENDING.value)
        .order_by(Attempt.finished_at, Attempt.id)
        .limit(1)
    ).first()
    if attempt is None:
        return None
    attempt.report_status = ReportStatus.GENERATING.value
    session.flush()
    return Job(attempt.id, build_input(session, attempt))


class ReportWorker:
    """Drains the queue on a daemon thread. `wake()` after queueing."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        config: TutorConfig,
        chat_factory: ChatFactory = chat_model,
        on_idle: Callable[[], None] | None = None,
    ) -> None:
        """Set up the worker; call `start` to run it."""
        self._sessions = sessions
        self._config = config
        self._chat_factory = chat_factory
        self._on_idle = on_idle
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Recover reports left mid-run, then start the background thread."""
        with self._sessions() as session, session.begin():
            recover(session)
        self._thread = threading.Thread(
            target=self._loop, name="algo_tutor-reports", daemon=True
        )
        self._thread.start()
        self.wake()

    def wake(self) -> None:
        """Wake the worker to check for pending reports now."""
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the worker and wait up to *timeout* seconds for its thread."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            while not self._stop.is_set() and self.run_once():
                pass
            if self._on_idle is not None:
                self._on_idle()

    def run_once(self) -> bool:
        """Generate one report. False when the queue is empty."""
        with self._sessions() as session, session.begin():
            job = claim(session)
        if job is None:
            return False
        task = self._config.task("report")
        try:
            answer = report.generate(self._chat_factory(task), task, job.report_input)
        except TutorError as failure:
            self._finish(job, ReportStatus.FAILED, error=failure)
            return True
        with self._sessions() as session, session.begin():
            attempt = session.get(Attempt, job.attempt_id)
            if (
                attempt is not None
                and attempt.report_status == ReportStatus.GENERATING.value
            ):
                attempt.report = report.to_column(answer.value)
                attempt.report_status = ReportStatus.DONE.value
                attempt.report_error = None
                attempt.report_error_message = None
                attempt.report_model = f"{task.provider}:{task.model}"
                attempt.reported_at = iso_utc(now_utc())
        return True

    def _finish(self, job: Job, status: ReportStatus, error: TutorError) -> None:
        with self._sessions() as session, session.begin():
            attempt = session.get(Attempt, job.attempt_id)
            if (
                attempt is not None
                and attempt.report_status == ReportStatus.GENERATING.value
            ):
                attempt.report_status = status.value
                attempt.report_error = error.kind.value
                attempt.report_error_message = error.message[:2000]
