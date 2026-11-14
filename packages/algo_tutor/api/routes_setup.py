"""Routes for setup, settings, the problem bank, backups and the tutor.

See SPEC §5.4, §12.1, §13, §14 Setup and §17.

These routes don't take the per-request transaction (`deps.Db`): the bank
service and the backup open their own sessions, and every transaction here
starts with BEGIN IMMEDIATE, so holding one across those calls would make
them wait out the busy timeout. Each route runs its own short transactions
in turn instead.
"""

from typing import Literal

from fastapi import APIRouter
from sqlalchemy import func, select

from packages.algo_tutor.api import deps, schemas
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import ApiError
from packages.algo_tutor.catalogue.bank import BankService, BankState
from packages.algo_tutor.catalogue.setup import complete_setup, setup_state
from packages.algo_tutor.domain.enums import TutorErrorKind
from packages.algo_tutor.runtime import take_backup
from packages.algo_tutor.store.backups import BackupError, list_backups
from packages.algo_tutor.store.db import transaction
from packages.algo_tutor.store.models import RatingEstimate, Settings
from packages.algo_tutor.store.timeutil import parse_iso
from packages.algo_tutor.tutor.connection import check_connection
from packages.algo_tutor.tutor.worker import pending_count

router = APIRouter(tags=["setup"])

BANK_JOB = "bank"
_SHOWN: dict[BankState, Literal["never", "running", "done", "failed"]] = {
    "idle": "never",
    "running": "running",
    "done": "done",
    "failed": "failed",
}


def bank_service(state: AppState) -> BankService:
    """The app's one bank service, made on first use.

    Tests put their own (with a stubbed fetch) in `state.jobs` first.
    """
    service = state.jobs.get(BANK_JOB)
    if not isinstance(service, BankService):
        runtime = state.runtime
        service = BankService(
            runtime.sessions,
            runtime.manifests,
            runtime.paths.bank_file,
            clock=state.clock,
        )
        state.jobs[BANK_JOB] = service
    return service


def bank_status(state: AppState) -> schemas.BankStatus:
    """Return the bank download status with the estimate count."""
    status = bank_service(state).status()
    with state.runtime.sessions() as session:
        estimated = (
            session.scalar(select(func.count()).select_from(RatingEstimate)) or 0
        )
    report = status.last_report or {}
    return schemas.BankStatus(
        status=_SHOWN[status.state],
        fetched_at=parse_iso(status.fetched_at) if status.fetched_at else None,
        pages_done=0,
        pages_total=None,
        problems=status.problems,
        estimated=int(estimated),
        method=status.method,
        unknown_tags=list(report.get("unknown_tags", [])),
        error=status.message if status.state == "failed" else None,
    )


def settings_out(state: AppState) -> schemas.SettingsOut:
    """Return the API view of the settings."""
    with state.runtime.sessions() as session:
        row = deps.settings_row(session)  # loaded; stays readable once closed
    return schemas.SettingsOut(
        timezone=row.timezone,
        questions_per_day=row.questions_per_day,
        atcoder_per_day=row.atcoder_per_day,
        target_rating=row.target_rating,
        include_paid_only=row.include_paid_only,
        onboarding_complete=row.onboarding_complete,
        active_list_leetcode=row.active_list_leetcode,
        active_list_atcoder=row.active_list_atcoder,
        last_backup_at=parse_iso(row.last_backup_at) if row.last_backup_at else None,
        bank=bank_status(state),
    )


# ---------------------------------------------------------------- setup


@router.get("/setup")
def get_setup(state: deps.State) -> schemas.SetupState:
    """Return the onboarding state."""
    with state.runtime.sessions() as session:
        current = setup_state(session)
    return schemas.SetupState(
        onboarding_complete=current.onboarding_complete,
        timezone=current.timezone,
        questions_per_day=current.questions_per_day,
    )


@router.post("/setup")
def post_setup(body: schemas.SetupIn, state: deps.State) -> schemas.SetupState:
    """Finish setup once (409 afterwards).

    The bank download starts after the setup commits, in the background.
    """
    runtime = state.runtime
    with transaction(runtime.sessions) as session:
        result = complete_setup(
            session,
            runtime.manifests,
            state.clock(),
            questions_per_day=body.questions_per_day,
            download_bank=body.download_bank,
            course=body.follow,
            bank=runtime.saved_bank(),
        )
    if result.start_bank_download:
        bank_service(state).start()
    return get_setup(state)


# ---------------------------------------------------------------- settings


@router.get("/settings")
def get_settings(state: deps.State) -> schemas.SettingsOut:
    """Return the settings."""
    return settings_out(state)


@router.patch("/settings")
def patch_settings(
    body: schemas.SettingsPatch, state: deps.State
) -> schemas.SettingsOut:
    """Change any of the §13 settings; a field sent as null is left alone."""
    with transaction(state.runtime.sessions) as session:
        row = session.get_one(Settings, 1)
        for name in body.model_fields_set:
            value = getattr(body, name)
            if value is not None:
                setattr(row, name, value)
    return settings_out(state)


# ---------------------------------------------------------------- bank


@router.get("/bank")
def get_bank(state: deps.State) -> schemas.BankStatus:
    """Return the bank download status."""
    return bank_status(state)


@router.post("/bank/refresh")
def refresh_bank(state: deps.State) -> schemas.BankStatus:
    """Start a bank download in the background, or keep the running one.

    Poll GET /bank every 2 s for its status.
    """
    bank_service(state).start()
    return bank_status(state)


# ---------------------------------------------------------------- backups


def backup_status(state: AppState) -> schemas.BackupStatus:
    """Return when the last backup was taken and where."""
    files = list_backups(state.runtime.paths.backups_dir)
    with state.runtime.sessions() as session:
        last = deps.settings_row(session).last_backup_at
    return schemas.BackupStatus(
        last_backup_at=parse_iso(last) if last else None,
        path=str(files[-1]) if files else None,
        kept=len(files),
    )


@router.get("/backup")
def get_backup(state: deps.State) -> schemas.BackupStatus:
    """Return the backup status."""
    return backup_status(state)


@router.post("/backup")
def post_backup(state: deps.State) -> schemas.BackupStatus:
    """Take a database backup now and return the new status."""
    try:
        take_backup(state.runtime, state.clock())
    except (BackupError, OSError) as failure:
        raise ApiError(500, "BACKUP_FAILED", str(failure)) from failure
    return backup_status(state)


# ---------------------------------------------------------------- tutor


@router.get("/tutor/status")
def tutor_status(state: deps.State) -> schemas.TutorStatus:
    """Return the tutor's config and its pending report count."""
    tutor = state.runtime.config.tutor
    with state.runtime.sessions() as session:
        pending = pending_count(session)
    return schemas.TutorStatus(
        enabled=tutor.enabled,
        provider=tutor.default.provider,
        model=tutor.default.model,
        leaves_machine=tutor.default.provider != "ollama",
        pending_reports=pending,
    )


@router.post("/tutor/test")
def tutor_test(state: deps.State) -> schemas.TutorTest:
    """One tiny structured call (SPEC §12.1).

    Synchronous: up to the test task's timeout.
    """
    tutor = state.runtime.config.tutor
    task = tutor.task("test")
    if not tutor.enabled:
        return schemas.TutorTest(
            ok=False,
            provider=task.provider,
            model=task.model,
            latency_ms=None,
            error_kind=TutorErrorKind.DISABLED,
            message="The tutor is off: tutor.enabled is false in config.yaml.",
        )
    try:
        chat = state.chat_factory(task)
    except Exception as failure:  # noqa: BLE001 -- a missing API key or bad setting shows in the panel
        return schemas.TutorTest(
            ok=False,
            provider=task.provider,
            model=task.model,
            latency_ms=None,
            error_kind=TutorErrorKind.ERROR,
            message=f"{type(failure).__name__}: {failure}",
        )
    result = check_connection(chat, task)
    return schemas.TutorTest(
        ok=result.ok,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        error_kind=result.error_kind,
        message=result.message,
    )
