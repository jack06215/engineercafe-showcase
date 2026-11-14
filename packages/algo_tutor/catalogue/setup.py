"""First-run setup (SPEC.md §14 "Setup"): questions per day, the bank, a course.

`complete_setup` writes everything in the caller's transaction. It doesn't
download the bank itself: when `download_bank` is set, the caller starts
`BankService` after committing (the download takes a minute).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from packages.algo_tutor.catalogue.bank_file import BankQuestion
from packages.algo_tutor.catalogue.courses import follow_course
from packages.algo_tutor.catalogue.errors import Conflict, InvalidInput, NotFound
from packages.algo_tutor.catalogue.lists import activate_list
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import BundledSet
from packages.algo_tutor.store.models import Settings


@dataclass(frozen=True)
class SetupState:
    """The onboarding settings that the setup screen shows."""

    onboarding_complete: bool
    timezone: str
    questions_per_day: int
    bank_status: str | None


@dataclass(frozen=True)
class SetupResult:
    """What the client must do after setup is saved."""

    start_bank_download: bool
    course_list_id: str | None


def _settings(session: Session) -> Settings:
    settings = session.get(Settings, 1)
    if settings is None:
        raise NotFound("Settings are missing; the database wasn't initialised.")
    return settings


def setup_state(session: Session) -> SetupState:
    """Return the current onboarding settings."""
    s = _settings(session)
    return SetupState(
        s.onboarding_complete, s.timezone, s.questions_per_day, s.bank_status
    )


def complete_setup(
    session: Session,
    manifests: Manifests,
    now: datetime,
    *,
    questions_per_day: int,
    download_bank: bool,
    course: BundledSet | None,
    bank: dict[str, BankQuestion] | None = None,
) -> SetupResult:
    """Finish setup once. Following a course also makes it the active LeetCode list."""
    settings = _settings(session)
    if settings.onboarding_complete:
        raise Conflict("Setup is already done.")
    low, high = constants.QUESTIONS_PER_DAY_RANGE
    if not low <= questions_per_day <= high:
        raise InvalidInput(f"Questions per day is {low}–{high}.")
    settings.questions_per_day = questions_per_day
    list_id = None
    if course is not None:
        followed = follow_course(session, manifests, course, now, bank)
        activate_list(session, followed.study_list.id)
        list_id = followed.study_list.id
    settings.onboarding_complete = True
    session.flush()
    return SetupResult(start_bank_download=download_bank, course_list_id=list_id)
