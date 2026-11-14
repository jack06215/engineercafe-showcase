"""Store rows → the domain's inputs and the contract's shared pieces.

Every route that shows a rating or a problem row goes through here, so the
rating rule (SPEC §5.5) is applied in one place.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.algo_tutor.api.schemas import ProblemBrief, RatingOut
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.domain.enums import Difficulty, Source
from packages.algo_tutor.domain.ratings import Rating, problem_rating
from packages.algo_tutor.store.models import Problem, RatingEstimate


def rating_of(
    problem: Problem, manifests: Manifests, estimate: int | None
) -> Rating | None:
    exact = (
        manifests.exact_ratings.get(problem.external_id)
        if problem.source == Source.LEETCODE
        else None
    )
    label = Difficulty(problem.difficulty_label) if problem.difficulty_label else None
    return problem_rating(
        Source(problem.source), label, exact.rating if exact else None, estimate
    )


def estimates(
    session: Session, problem_ids: Iterable[str] | None = None
) -> dict[str, int]:
    """Fitted ratings by problem id; all of them when `problem_ids` is None."""
    query = select(RatingEstimate.problem_id, RatingEstimate.rating)
    if problem_ids is not None:
        query = query.where(RatingEstimate.problem_id.in_(list(problem_ids)))
    return {pid: rating for pid, rating in session.execute(query).tuples()}


def ratings(
    session: Session, manifests: Manifests, problems: Iterable[Problem]
) -> dict[str, Rating | None]:
    rows = list(problems)
    fitted = estimates(session, [p.id for p in rows])
    return {p.id: rating_of(p, manifests, fitted.get(p.id)) for p in rows}


def rating_out(rating: Rating | None) -> RatingOut | None:
    return (
        None
        if rating is None
        else RatingOut(value=rating.value, estimated=rating.estimated)
    )


def brief(problem: Problem, rating: Rating | None) -> ProblemBrief:
    return ProblemBrief(
        id=problem.id,
        source=Source(problem.source),
        title=problem.title,
        url=problem.url,
        number=problem.number,
        contest=problem.contest,
        difficulty=Difficulty(problem.difficulty_label)
        if problem.difficulty_label
        else None,
        rating=rating_out(rating),
    )


def brief_one(session: Session, manifests: Manifests, problem: Problem) -> ProblemBrief:
    fitted = estimates(session, [problem.id])
    return brief(problem, rating_of(problem, manifests, fitted.get(problem.id)))
