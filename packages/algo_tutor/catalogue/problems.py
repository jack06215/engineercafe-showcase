"""Creating problems and keeping their primary topic (SPEC.md §5.1, §5.2, §5.7).

Everything here is additive: a problem that exists is returned as it is,
apart from LeetCode's own metadata (tags, number, paid-only, label) filling
in or refreshing. Your notes, patterns, titles and topic overrides are never
touched.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.algo_tutor.catalogue.bank_file import BankQuestion
from packages.algo_tutor.catalogue.errors import InvalidInput
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import Difficulty, Source
from packages.algo_tutor.domain.topics import TopicCatalog
from packages.algo_tutor.domain.urls import ProblemRef, parse_problem_url
from packages.algo_tutor.store.models import Problem
from packages.algo_tutor.store.timeutil import iso_utc, new_id


@dataclass(frozen=True)
class Added:
    """A problem and whether adding it created a new row."""

    problem: Problem
    created: bool


def find_problem(session: Session, source: Source, external_id: str) -> Problem | None:
    """Return the problem with *source* and *external_id*, or None."""
    return session.scalar(
        select(Problem).where(
            Problem.source == source.value, Problem.external_id == external_id
        )
    )


def assign_topic(problem: Problem, catalog: TopicCatalog) -> None:
    """Recompute the primary topic of a LeetCode problem unless you overrode it."""
    if problem.source != Source.LEETCODE.value or problem.topic_overridden:
        return
    problem.topic_id = catalog.primary_topic(
        problem.source_tags, problem.neetcode_category
    )


def title_from_slug(slug: str) -> str:
    """A readable stand-in title when nothing better is known: two-sum → Two Sum."""
    return " ".join(word.capitalize() for word in slug.split("-"))


def apply_bank_metadata(problem: Problem, question: BankQuestion) -> None:
    """LeetCode's own facts from the bank onto an existing problem; nothing of yours."""
    problem.source_tags = list(question.tags[: constants.MAX_SOURCE_TAGS])
    problem.paid_only = question.paid_only
    if question.number is not None:
        problem.number = question.number
    if question.difficulty is not None:
        problem.difficulty_label = question.difficulty.value


def ensure_leetcode(
    session: Session,
    manifests: Manifests,
    slug: str,
    now: datetime,
    *,
    title: str | None = None,
    difficulty: Difficulty | None = None,
    bank: BankQuestion | None = None,
) -> Added:
    """The LeetCode problem `slug`, created if missing from what's known about it.

    Title, label and number come from (first wins) the arguments, the bundled
    manifests, then the last bank download; tags and paid-only from the bank.
    """
    existing = find_problem(session, Source.LEETCODE, slug)
    if existing is not None:
        if existing.difficulty_label is None and difficulty is not None:
            existing.difficulty_label = difficulty.value
        return Added(existing, created=False)

    known = manifests.known.get(slug)
    neetcode = manifests.neetcode.get(slug)
    label = (
        difficulty
        or (known.difficulty if known else None)
        or (bank.difficulty if bank else None)
    )
    number = (known.number if known else None) or (bank.number if bank else None)
    problem = Problem(
        id=new_id(),
        source=Source.LEETCODE.value,
        external_id=slug,
        kind="problem",
        number=number,
        title=(
            title
            or (known.title if known else None)
            or (bank.title if bank else None)
            or title_from_slug(slug)
        ),
        url=ProblemRef(Source.LEETCODE, slug).url,
        difficulty_label=label.value if label else None,
        paid_only=bank.paid_only if bank else False,
        source_tags=list(bank.tags[: constants.MAX_SOURCE_TAGS]) if bank else [],
        neetcode_category=neetcode.neetcode_category if neetcode else None,
        topic_overridden=False,
        notes="",
        exposed=False,
        created_at=iso_utc(now),
    )
    assign_topic(problem, manifests.topics)
    session.add(problem)
    session.flush()
    return Added(problem, created=True)


def ensure_atcoder(
    session: Session, task_id: str, contest: str, title: str, now: datetime
) -> Added:
    """The AtCoder task, created with `title` if missing. No topic, no rating (SPEC §5.7)."""
    existing = find_problem(session, Source.ATCODER, task_id)
    if existing is not None:
        return Added(existing, created=False)
    ref = ProblemRef(Source.ATCODER, task_id, contest=contest)
    problem = Problem(
        id=new_id(),
        source=Source.ATCODER.value,
        external_id=task_id,
        kind="problem",
        contest=contest,
        title=title,
        url=ref.url,
        paid_only=False,
        source_tags=[],
        topic_overridden=False,
        notes="",
        exposed=False,
        created_at=iso_utc(now),
    )
    session.add(problem)
    session.flush()
    return Added(problem, created=True)


def add_problem_by_url(
    session: Session,
    manifests: Manifests,
    url: str,
    now: datetime,
    *,
    title: str | None = None,
    bank: dict[str, BankQuestion] | None = None,
) -> Added:
    """For "Add problem" in the library (SPEC §14).

    An existing problem comes back as is.

    AtCoder needs `title`; LeetCode finds its own when `title` is None.
    """
    ref = parse_problem_url(url)
    if ref is None:
        raise InvalidInput("Not a LeetCode problem URL or an AtCoder task URL.")
    title = title.strip() if title else None
    if title is not None and not 1 <= len(title) <= constants.MAX_TITLE_CHARS:
        raise InvalidInput(f"A title is 1–{constants.MAX_TITLE_CHARS} characters.")
    if ref.source is Source.LEETCODE:
        question = bank.get(ref.external_id) if bank else None
        return ensure_leetcode(
            session, manifests, ref.external_id, now, title=title, bank=question
        )
    existing = find_problem(session, Source.ATCODER, ref.external_id)
    if existing is not None:
        return Added(existing, created=False)
    if not title:
        raise InvalidInput("An AtCoder problem needs a title.")
    return ensure_atcoder(session, ref.external_id, ref.contest or "", title, now)
