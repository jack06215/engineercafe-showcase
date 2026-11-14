"""Review scheduling: when an idea comes back, and its stored target (SPEC §8).

Ported from BloomCode's `attempts/review-schedule.ts` and `closeout.ts`, with
one addition: the AtCoder retirement rule (§8.5).

A review target belongs to one problem (the idea's first problem). Every
function here returns new `ReviewTarget` values; the caller writes them,
assigning ids and checking the stored version.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta

from packages.algo_tutor.domain.constants import (
    MIXED_DAYS,
    RECONSTRUCTION_DAYS,
    REPAIR_DAYS,
    TRANSFER_DAYS,
)
from packages.algo_tutor.domain.enums import (
    Evidence,
    Help,
    Outcome,
    ReviewAction,
    ReviewChoice,
    ReviewStage,
    Source,
)


class ReviewDateRequired(ValueError):
    """A manual or snooze action came without a date (400 VALIDATION)."""


@dataclass(frozen=True)
class Recommendation:
    date: date
    stage: ReviewStage


def is_repair(outcome: Outcome, help: Help) -> bool:
    """Not solved, or solved with major help, the solution, or unknown help."""
    return outcome is not Outcome.SOLVED or help in (
        Help.MAJOR,
        Help.SOLUTION,
        Help.UNKNOWN,
    )


def recommendation(
    outcome: Outcome, help: Help, evidence: Evidence, study_date: date
) -> Recommendation:
    """The interval rules at finish (SPEC §8.1): repair → reconstruction → transfer → mixed.

    | repair                          | +1  | repair         |
    | solved, small hint              | +3  | reconstruction |
    | solved alone, retention         | +7  | transfer       |
    | solved alone, any other evidence| +14 | mixed          |
    """
    if is_repair(outcome, help):
        days, stage = REPAIR_DAYS, ReviewStage.REPAIR
    elif help is Help.SMALL:
        days, stage = RECONSTRUCTION_DAYS, ReviewStage.RECONSTRUCTION
    elif evidence is Evidence.RETENTION:
        days, stage = TRANSFER_DAYS, ReviewStage.TRANSFER
    else:
        days, stage = MIXED_DAYS, ReviewStage.MIXED
    return Recommendation(study_date + timedelta(days=days), stage)


@dataclass(frozen=True)
class ReviewTarget:
    problem_id: str
    recommended_date: date | None
    effective_date: date | None  # what is shown and used; None = "No scheduled review"
    action: ReviewAction
    stage: ReviewStage
    version: int = 1
    # Consecutive solo solves at stage `transfer` (AtCoder only, SPEC §8.5).
    solo_transfer_streak: int = 0


@dataclass(frozen=True)
class Choice:
    """A requested action: the finish form's "Next review", or a snooze."""

    action: ReviewAction
    day: date | None = None  # required for manual and snooze

    @classmethod
    def from_finish(cls, choice: ReviewChoice, chosen: date | None = None) -> "Choice":
        return cls(ReviewAction(choice.value), chosen)


RECOMMENDED = Choice(ReviewAction.RECOMMENDED)
NO_REVIEW = Choice(ReviewAction.NONE)


def update_target(
    prior: ReviewTarget | None,
    problem_id: str,
    recommended_date: date | None,
    stage: ReviewStage,
    choice: Choice | None = None,
) -> ReviewTarget:
    """Upstream's `updateTarget`: a new recommendation, then the learner's choice.

    A non-recommended choice sets the action and effective date. A
    recommended one only moves the effective date while the target's action
    is still `recommended`: a hand-set date survives an ordinary finish.
    """
    if prior is None:
        t = ReviewTarget(
            problem_id=problem_id,
            recommended_date=recommended_date,
            effective_date=recommended_date,
            action=ReviewAction.RECOMMENDED,
            stage=stage,
        )
    else:
        t = replace(
            prior,
            version=prior.version + 1,
            recommended_date=recommended_date,
            stage=stage,
        )
    if choice is not None and choice.action is not ReviewAction.RECOMMENDED:
        if (
            choice.action in (ReviewAction.MANUAL, ReviewAction.SNOOZE)
            and choice.day is None
        ):
            raise ReviewDateRequired("A date is required for this review action")
        effective = None if choice.action is ReviewAction.NONE else choice.day
        t = replace(t, action=choice.action, effective_date=effective)
    elif t.action is ReviewAction.RECOMMENDED:
        t = replace(t, effective_date=recommended_date)
    return t


def edit_target(
    target: ReviewTarget, action: ReviewAction, chosen: date | None = None
) -> ReviewTarget:
    """The problem page's schedule editor (`PATCH /reviews/{problem_id}`).

    Recommended goes back to the recommended date; none clears the date;
    manual and snooze need a date. The stage is unchanged.
    """
    if action in (ReviewAction.MANUAL, ReviewAction.SNOOZE) and chosen is None:
        raise ReviewDateRequired("A date is required")
    if action is ReviewAction.NONE:
        effective = None
    elif action is ReviewAction.RECOMMENDED:
        effective = target.recommended_date
    else:
        effective = chosen
    return replace(
        target, action=action, effective_date=effective, version=target.version + 1
    )


def snooze_target(
    prior: ReviewTarget | None, problem_id: str, until: date
) -> ReviewTarget:
    """Postponing a plan item (SPEC §10.4): stage `snoozed`, action `snooze`."""
    return update_target(
        prior, problem_id, None, ReviewStage.SNOOZED, Choice(ReviewAction.SNOOZE, until)
    )


@dataclass(frozen=True)
class FinishedReview:
    """What finishing an attempt does to the schedule.

    `targets` are the review targets to write (one or two). The attempt's
    `next_review_date` is `next_review`: the effective date of the target its
    result moved (the original idea's, for a check).
    """

    targets: tuple[ReviewTarget, ...]
    next_review: date | None


def review_at_finish(
    *,
    problem_id: str,
    source: Source,
    outcome: Outcome,
    help: Help,
    evidence: Evidence,
    study_date: date,
    choice: Choice,
    own_target: ReviewTarget | None,
    review_of: str | None = None,
    idea_target: ReviewTarget | None = None,
) -> FinishedReview:
    """Closeout's schedule step (SPEC §6.6 step 2, §8.1–§8.5).

    A plain attempt moves its own problem's target. A check (`review_of`
    set, from its plan item) moves the original idea's target instead, and
    the check problem gets a `covered` target with no date. A hand-set date
    on the idea that came due is served by the check and goes back to
    recommended. Two solo solves at the 14-day stage retire the idea.

    AtCoder (no `review_of`, the same problem comes back): two consecutive
    solo solves at stage `transfer` retire it, and a hand-set date that came
    due is served by the re-solve.
    """
    r = recommendation(outcome, help, evidence, study_date)
    if review_of is not None:
        idea = idea_target
        if (
            idea is not None
            and idea.action in (ReviewAction.MANUAL, ReviewAction.SNOOZE)
            and choice.action is ReviewAction.RECOMMENDED
        ):
            idea = replace(idea, action=ReviewAction.RECOMMENDED)
        if (
            idea_target is not None
            and idea_target.stage is ReviewStage.MIXED
            and r.stage is ReviewStage.MIXED
            and choice.action is ReviewAction.RECOMMENDED
        ):
            moved = update_target(idea, review_of, None, ReviewStage.RETIRED, NO_REVIEW)
        else:
            moved = update_target(idea, review_of, r.date, r.stage, choice)
        covered = update_target(
            own_target, problem_id, None, ReviewStage.COVERED, NO_REVIEW
        )
        return FinishedReview((moved, covered), moved.effective_date)

    if source is Source.ATCODER:
        moved = _atcoder_finish(own_target, problem_id, r, choice, study_date)
    else:
        moved = update_target(own_target, problem_id, r.date, r.stage, choice)
    return FinishedReview((moved,), moved.effective_date)


def _atcoder_finish(
    prior: ReviewTarget | None,
    problem_id: str,
    r: Recommendation,
    choice: Choice,
    study_date: date,
) -> ReviewTarget:
    """SPEC §8.5. A re-solve is never `unseen`, so BloomCode's retirement
    (two `mixed` results) can't fire; count solo solves at `transfer` instead."""
    if (
        prior is not None
        and prior.action in (ReviewAction.MANUAL, ReviewAction.SNOOZE)
        and prior.effective_date is not None
        and prior.effective_date <= study_date
        and choice.action is ReviewAction.RECOMMENDED
    ):
        # The due hand-set date has been served by this re-solve.
        prior = replace(prior, action=ReviewAction.RECOMMENDED)
    if r.stage is ReviewStage.TRANSFER:
        streak = (prior.solo_transfer_streak if prior is not None else 0) + 1
    else:
        streak = 0
    if streak >= 2 and choice.action is ReviewAction.RECOMMENDED:
        t = update_target(prior, problem_id, None, ReviewStage.RETIRED, NO_REVIEW)
    else:
        t = update_target(prior, problem_id, r.date, r.stage, choice)
    return replace(t, solo_transfer_streak=streak)


def is_waiting(target: ReviewTarget | None, today: date) -> bool:
    """A problem waits while its target is `none` or has a future date (SPEC §8.2).

    Waiting problems are never offered as new practice, even before a first attempt.
    """
    if target is None:
        return False
    return target.action is ReviewAction.NONE or (
        target.effective_date is not None and target.effective_date > today
    )


@dataclass(frozen=True)
class DueCandidate:
    """A problem with a review target, as checks-due selection needs it."""

    problem_id: str
    title: str
    source: Source
    topic_id: str | None
    rating: int | None
    target: ReviewTarget
    completed_attempts: int
    in_unfinished_attempt: bool


@dataclass(frozen=True)
class DueCheck:
    """An attempted idea that is due again: after a struggle a repair, else a transfer check."""

    problem_id: str
    title: str
    source: Source
    topic_id: str | None
    rating: int | None
    is_repair: bool
    due: date


def title_key(title: str) -> tuple[str, str]:
    """Title order. Upstream uses JS `localeCompare`; casefold first is close."""
    return (title.casefold(), title)


def due_checks(problems: Iterable[DueCandidate], today: date) -> list[DueCheck]:
    """Checks due today (SPEC §8.3): an effective date today or earlier, not
    in an unfinished attempt, and at least one completed attempt (a snoozed
    never-attempted problem is just new again). Sorted by date, then title.
    """
    checks: list[DueCheck] = []
    for p in problems:
        due = p.target.effective_date
        if (
            due is None
            or due > today
            or p.in_unfinished_attempt
            or p.completed_attempts == 0
        ):
            continue
        checks.append(
            DueCheck(
                problem_id=p.problem_id,
                title=p.title,
                source=p.source,
                topic_id=p.topic_id,
                rating=p.rating,
                is_repair=p.target.stage is ReviewStage.REPAIR,
                due=due,
            )
        )
    return sorted(checks, key=lambda c: (c.due, title_key(c.title)))
