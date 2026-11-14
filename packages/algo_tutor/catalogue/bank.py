"""The LeetCode problem bank (SPEC.md §5.4–§5.6), ported from BloomCode.

`build_bank` turns a download into ratings and popularity; `apply_bank`
writes it in the caller's transaction, additively by slug: a refresh adds
problems rated up to 2000, refreshes LeetCode's own metadata on problems you
already have, recomputes primary topics you haven't overridden, and replaces
the rating estimates and popularity wholesale. It never touches your notes,
patterns, overrides or attempts. `BankService` runs a refresh in the
background for the API and reports status for polling.
"""

import math
import threading
import time
from bisect import bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import requests
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from packages.algo_tutor.catalogue.bank_file import (
    BankFetchError,
    BankQuestion,
    HttpPost,
    fetch_pages,
    questions_from_pages,
    save_pages,
)
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.catalogue.problems import (
    apply_bank_metadata,
    assign_topic,
    ensure_leetcode,
)
from packages.algo_tutor.catalogue.rating_model import (
    ProblemFeatures,
    RatedFeatures,
    RatingModel,
    TooFewRatedProblemsError,
    fit_rating_model,
)
from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import Source
from packages.algo_tutor.store.models import (
    ImportBatch,
    Problem,
    ProblemPopularity,
    RatingEstimate,
    Settings,
)
from packages.algo_tutor.store.timeutil import iso_utc, new_id, now_utc


@dataclass(frozen=True)
class Popularity:
    """Likes, dislikes and percentile of a LeetCode problem."""

    likes: int
    dislikes: int
    percentile: int


@dataclass(frozen=True)
class Bank:
    """The processed LeetCode bank: kept problems, estimates and popularity."""

    model: RatingModel
    estimates: dict[str, int]  # slug → fitted rating, for problems without an exact one
    popularity: dict[str, Popularity]  # slug → popularity, algorithm problems only
    kept: list[BankQuestion]  # algorithm problems rated up to the cap
    algorithms: dict[str, BankQuestion]  # every algorithm problem in the download
    unknown_tags: list[str]


@dataclass(frozen=True)
class BankReport:
    """Counts from one bank import."""

    downloaded: int
    kept: int
    added: int
    updated: int
    method: str
    unknown_tags: list[str]

    def as_json(self) -> dict[str, Any]:
        """Return the report as a JSON-ready dict."""
        return {
            "downloaded": self.downloaded,
            "kept": self.kept,
            "added": self.added,
            "updated": self.updated,
            "method": self.method,
            "unknown_tags": self.unknown_tags,
        }


def _round_half_up(value: float) -> int:
    """JavaScript's Math.round, which upstream's numbers were made with."""
    return math.floor(value + 0.5)


def _features(q: BankQuestion) -> ProblemFeatures | None:
    if q.difficulty is None:
        return None
    return ProblemFeatures(difficulty=q.difficulty, ac_rate=q.ac_rate, tags=q.tags)


def popularity_of(questions: Iterable[BankQuestion]) -> dict[str, Popularity]:
    """Likes percentile among `questions` (SPEC §5.6)."""
    listed = list(questions)
    likes = sorted(q.likes for q in listed)
    n = max(1, len(likes))
    return {
        q.slug: Popularity(
            q.likes, q.dislikes, _round_half_up(100 * bisect_right(likes, q.likes) / n)
        )
        for q in listed
    }


def build_bank(
    questions: list[BankQuestion], manifests: Manifests, cap: int = constants.BANK_CAP
) -> Bank:
    """Ratings, popularity and the problems to keep, from one download."""
    exact = manifests.exact_ratings
    rated: list[RatedFeatures] = []
    for q in questions:
        f = _features(q)
        if f is not None and q.slug in exact:
            rated.append(
                RatedFeatures(
                    f.difficulty, f.ac_rate, f.tags, rating=exact[q.slug].rating
                )
            )
    if len(rated) < constants.RIDGE_MIN_ROWS:
        raise TooFewRatedProblemsError(
            f"Only {len(rated)} downloaded problems have contest ratings; "
            f"the rating model needs {constants.RIDGE_MIN_ROWS}."
        )
    model = fit_rating_model(rated)
    estimates: dict[str, int] = {}
    for q in questions:
        f = _features(q)
        if q.slug not in exact and f is not None:
            estimates[q.slug] = _round_half_up(model.predict(f))

    catalog = manifests.topics
    algorithms = {q.slug: q for q in questions if not catalog.is_excluded(q.tags)}

    def rating(q: BankQuestion) -> float:
        if q.slug in exact:
            return exact[q.slug].rating
        return estimates.get(q.slug, math.inf)

    kept = sorted(
        (q for q in algorithms.values() if rating(q) <= cap), key=lambda q: q.slug
    )
    unknown = sorted(
        {tag for q in algorithms.values() for tag in catalog.unknown_tags(q.tags)}
    )
    return Bank(
        model=model,
        estimates=estimates,
        popularity=popularity_of(algorithms.values()),
        kept=kept,
        algorithms=algorithms,
        unknown_tags=unknown,
    )


def apply_bank(
    session: Session, bank: Bank, manifests: Manifests, now: datetime
) -> BankReport:
    """Write `bank` in the caller's transaction (additive by slug)."""
    added = updated = 0
    for q in bank.kept:
        result = ensure_leetcode(session, manifests, q.slug, now, bank=q)
        if result.created:
            added += 1
    # LeetCode's own metadata, refreshed on every library problem it lists,
    # including ones over the cap that a course or list brought in.
    library = session.scalars(
        select(Problem).where(Problem.source == Source.LEETCODE.value)
    )
    for problem in library:
        question = bank.algorithms.get(problem.external_id)
        if question is None:
            continue
        before = (
            tuple(problem.source_tags),
            problem.topic_id,
            problem.number,
            problem.paid_only,
        )
        apply_bank_metadata(problem, question)
        assign_topic(problem, manifests.topics)
        after = (
            tuple(problem.source_tags),
            problem.topic_id,
            problem.number,
            problem.paid_only,
        )
        if before != after:
            updated += 1
    session.flush()

    # A comprehension, not dict(): a Result has .keys(), so dict() reads it as a mapping.
    ids = {
        slug: problem_id
        for slug, problem_id in session.execute(
            select(Problem.external_id, Problem.id).where(
                Problem.source == Source.LEETCODE.value
            )
        )
    }
    fitted_at = iso_utc(now)
    session.execute(delete(RatingEstimate))
    session.add_all(
        RatingEstimate(
            problem_id=ids[slug],
            rating=rating,
            method=bank.model.method,
            fitted_at=fitted_at,
        )
        for slug, rating in bank.estimates.items()
        if slug in ids
    )
    session.execute(delete(ProblemPopularity))
    session.add_all(
        ProblemPopularity(
            problem_id=ids[slug],
            likes=p.likes,
            dislikes=p.dislikes,
            percentile=p.percentile,
        )
        for slug, p in bank.popularity.items()
        if slug in ids
    )
    report = BankReport(
        downloaded=len(bank.algorithms),
        kept=len(bank.kept),
        added=added,
        updated=updated,
        method=bank.model.method,
        unknown_tags=bank.unknown_tags,
    )
    session.add(
        ImportBatch(
            id=new_id(),
            kind="bank",
            fingerprint=bank.model.method,
            applied_at=fitted_at,
            report=report.as_json(),
        )
    )
    settings = session.get(Settings, 1)
    if settings is not None:
        settings.bank_status = "done"
        settings.bank_fetched_at = fitted_at
    session.flush()
    return report


BankState = Literal["idle", "running", "done", "failed"]


@dataclass(frozen=True)
class BankStatus:
    """The bank download's state and the library's LeetCode counts."""

    state: BankState
    message: str | None
    problems: int  # LeetCode problems in the library
    method: str | None  # the estimates' method, e.g. "ridge-v1 mae=148"
    fetched_at: str | None
    last_report: dict[str, Any] | None = field(default=None)


def bank_summary(
    session: Session,
) -> tuple[int, str | None, str | None, dict[str, Any] | None]:
    """Return the problem count, estimate method, fetch time and last report."""
    problems = session.scalar(
        select(func.count())
        .select_from(Problem)
        .where(Problem.source == Source.LEETCODE.value)
    )
    method = session.scalar(select(RatingEstimate.method).limit(1))
    settings = session.get(Settings, 1)
    last = session.scalar(
        select(ImportBatch)
        .where(ImportBatch.kind == "bank")
        .order_by(ImportBatch.applied_at.desc())
        .limit(1)
    )
    return (
        int(problems or 0),
        method,
        settings.bank_fetched_at if settings else None,
        last.report if last else None,
    )


def reset_interrupted(session: Session) -> None:
    """At startup: a refresh that was running when the process died has failed."""
    settings = session.get(Settings, 1)
    if settings is not None and settings.bank_status == "running":
        settings.bank_status = "failed"


class BankService:
    """Runs one refresh at a time, in a background thread or inline."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        manifests: Manifests,
        bank_file: Path,
        post: HttpPost | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        """Set up the service; *post*, *sleep* and *clock* are injectable for tests."""
        self._sessions = sessions
        self._manifests = manifests
        self._bank_file = bank_file
        self._post: HttpPost = post if post is not None else requests.post
        self._sleep = sleep if sleep is not None else time.sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._running = False
        self._message: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> BankStatus:
        """Return the bank's current state and counts."""
        with self._sessions() as session:
            problems, method, fetched_at, report = bank_summary(session)
            settings = session.get(Settings, 1)
            stored = settings.bank_status if settings else None
        state: BankState
        if self._running:
            state = "running"
        elif stored == "done":
            state = "done"
        elif stored in ("failed", "running"):
            # "running" with nothing running here: a process stopped mid-refresh.
            state = "failed"
        else:
            state = "idle"
        return BankStatus(state, self._message, problems, method, fetched_at, report)

    def start(self) -> bool:
        """Start a refresh in the background; False if one is already running."""
        if not self._claim():
            return False
        self._thread = threading.Thread(
            target=self._run, name="algo_tutor-bank", daemon=True
        )
        self._thread.start()
        return True

    def refresh(self) -> BankReport:
        """Refresh inline (the CLI). Raises if one is already running or it fails."""
        if not self._claim():
            raise BankFetchError("A problem bank refresh is already running.")
        report = self._run()
        if report is None:
            raise BankFetchError(self._message or "The problem bank refresh failed.")
        return report

    def join(self, timeout: float | None = None) -> None:
        """Wait for a running download to finish, up to *timeout* seconds."""
        if self._thread is not None:
            self._thread.join(timeout)

    def _claim(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._message = "Downloading LeetCode problems…"
        with self._sessions() as session, session.begin():
            settings = session.get(Settings, 1)
            if settings is not None:
                settings.bank_status = "running"
        return True

    def _run(self) -> BankReport | None:
        try:
            pages = fetch_pages(self._post, self._sleep)
            now = self._clock()
            save_pages(self._bank_file, pages, iso_utc(now))
            self._message = "Rating problems…"
            bank = build_bank(questions_from_pages(pages), self._manifests)
            with self._sessions() as session, session.begin():
                report = apply_bank(session, bank, self._manifests, now)
            self._message = (
                f"Rated {report.downloaded:,} LeetCode problems; {report.added:,} new."
            )
            return report
        except (
            requests.RequestException,
            BankFetchError,
            TooFewRatedProblemsError,
            ValueError,
            KeyError,
            OSError,
        ) as exc:
            self._message = f"Couldn't update the problem bank. {exc}".strip()
            with self._sessions() as session, session.begin():
                settings = session.get(Settings, 1)
                if settings is not None:
                    settings.bank_status = "failed"
            return None
        finally:
            with self._lock:
                self._running = False
