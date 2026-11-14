"""The problem page's review schedule editor (SPEC §8.2, §15)."""

from fastapi import APIRouter

from packages.algo_tutor.api import deps, engine
from packages.algo_tutor.api.errors import ApiError, not_found
from packages.algo_tutor.api.schemas import ReviewPatch, ReviewTargetOut
from packages.algo_tutor.domain import review
from packages.algo_tutor.domain.enums import ReviewAction
from packages.algo_tutor.store import models

router = APIRouter(tags=["reviews"])


def target_out(row: models.ReviewTarget) -> ReviewTargetOut:
    """Return the API view of a stored review target."""
    target = engine.target_from_row(row)
    return ReviewTargetOut(
        problem_id=target.problem_id,
        recommended_date=target.recommended_date,
        effective_date=target.effective_date,
        action=target.action,
        stage=target.stage,
        version=target.version,
    )


@router.patch("/reviews/{problem_id}")
def edit_review(
    problem_id: str, body: ReviewPatch, session: deps.Db
) -> ReviewTargetOut:
    """Recommended, a date of your own, snooze, or no review.

    A problem with no schedule yet can only be snoozed (it then waits, like
    a postponed plan item); everything else needs a first attempt.
    """
    deps.forbid_during_assessment(session)
    if session.get(models.Problem, problem_id) is None:
        raise not_found("Problem")
    if (
        body.action in (ReviewAction.MANUAL, ReviewAction.SNOOZE)
        and body.review_date is None
    ):
        raise ApiError(422, "VALIDATION", "review_date: choose a date")
    current = engine.target_of(session, problem_id)
    if current is None:
        if body.action is not ReviewAction.SNOOZE or body.review_date is None:
            raise not_found("Review schedule")
        if body.version != 1:
            raise ApiError(
                409, "STALE", "This review schedule changed elsewhere; reload it"
            )
        updated = review.snooze_target(None, problem_id, body.review_date)
    else:
        deps.check_version(current.version, body.version, "This review schedule")
        updated = review.edit_target(current, body.action, body.review_date)
    return target_out(engine.write_target(session, updated))
