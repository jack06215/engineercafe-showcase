"""API test harness for the algo_tutor routes.

It runs a real runtime on a temporary repo root and data folder, the app with a
scripted tutor, and a client that passes the local-only guard.
"""

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from packages.algo_tutor.api.app import AppState, create_app
from packages.algo_tutor.api.routes_setup import BANK_JOB
from packages.algo_tutor.catalogue.bank import BankService
from packages.algo_tutor.catalogue.testing import bank_pages
from packages.algo_tutor.config import TaskConfig
from packages.algo_tutor.runtime import Runtime, open_runtime
from packages.algo_tutor.store.models import (
    Attempt,
    Problem,
    ProblemPopularity,
    RatingEstimate,
)
from packages.algo_tutor.store.timeutil import iso_utc, new_id
from packages.algo_tutor.tutor.fake_models import ScriptedChat

PORT = 4317
NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)  # 18:00 in Tokyo

PATTERN_README = "# Sliding Window\n\nKeep a window over the input.\n"


class Clock:
    """A settable clock for the app and the stopwatch."""

    def __init__(self, now: datetime = NOW) -> None:
        """Start the clock at *now*."""
        self.now = now

    def __call__(self) -> datetime:
        """Return the current fake time."""
        return self.now


@dataclass
class Harness:
    """A test app with a temporary database, fake clock and scripted tutor."""

    folder: tempfile.TemporaryDirectory[str]
    runtime: Runtime
    client: TestClient
    clock: Clock
    script: list[Any]  # replies for the scripted tutor, shared by every call
    chats: list[ScriptedChat]

    @property
    def repo_root(self) -> Path:
        """The repo root that the app reads patterns from."""
        return self.runtime.paths.repo_root

    @property
    def state(self) -> AppState:
        """The app state of the test client's app."""
        state: AppState = self.client.app.state.algo  # type: ignore[attr-defined]
        return state

    def session(self) -> Session:
        """Open a new database session."""
        return self.runtime.sessions()

    def get(self, path: str, **kwargs: Any) -> httpx2.Response:
        """GET an API path, given without the /api prefix."""
        return self.client.get(f"/api{path}", **kwargs)

    def post(self, path: str, body: Any = None, **kwargs: Any) -> httpx2.Response:
        """POST a JSON body to an API path, given without the /api prefix."""
        return self.client.post(
            f"/api{path}", json=body if body is not None else {}, **kwargs
        )

    def patch(self, path: str, body: Any, **kwargs: Any) -> httpx2.Response:
        """PATCH a JSON body to an API path, given without the /api prefix."""
        return self.client.patch(f"/api{path}", json=body, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx2.Response:
        """DELETE an API path, given without the /api prefix."""
        headers = {"content-type": "application/json"} | kwargs.pop("headers", {})
        return self.client.delete(f"/api{path}", headers=headers, **kwargs)

    def close(self) -> None:
        """Close the client, the runtime and the temporary folder."""
        self.client.close()
        self.runtime.close()
        self.folder.cleanup()


def make_harness(
    config_yaml: str = "tutor:\n  enabled: true\n",
    timezone: str = "Asia/Tokyo",
    repo_files: dict[str, str] | None = None,
    start_worker: bool = False,
) -> Harness:
    """A fresh app.

    `repo_files` are written under the temporary repo root (relative paths),
    e.g. solution files for path suggestions.
    """
    folder = tempfile.TemporaryDirectory()
    root = Path(folder.name) / "repo"
    pattern = (
        root / "packages/programming_exercise/common_coding_pattern/01_sliding_window"
    )
    pattern.mkdir(parents=True)
    (pattern / "README.md").write_text(PATTERN_README)
    (root / "packages/algo_tutor").mkdir(parents=True)
    for rel, text in (repo_files or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    config = Path(folder.name) / "config.yaml"
    config.write_text(config_yaml)
    runtime = open_runtime(
        repo_root=root,
        data_dir=Path(folder.name) / "data",
        config=config,
        environ={"TZ": timezone},
    )
    clock = Clock()
    script: list[Any] = []
    chats: list[ScriptedChat] = []

    def factory(_: TaskConfig) -> ScriptedChat:
        chat = ScriptedChat(script=[])
        # Share the harness's list: pydantic copies a list passed to the
        # constructor, so replies would never be used up across calls.
        chat.script = script
        chats.append(chat)
        return chat

    chat_factory: Callable[[TaskConfig], Any] = factory
    app = create_app(
        runtime, chat_factory=chat_factory, clock=clock, start_worker=start_worker
    )
    client = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    client.__enter__()  # run the lifespan
    return Harness(folder, runtime, client, clock, script, chats)


# ---------------------------------------------------------------- rows for tests


def insert_problem(
    h: Harness,
    slug: str,
    title: str,
    *,
    source: str = "leetcode",
    difficulty: str | None = "Easy",
    tags: tuple[str, ...] = (),
    topic_id: str | None = None,
    number: int | None = None,
    contest: str | None = None,
) -> str:
    """A problem straight into the database; its id."""
    url = (
        f"https://leetcode.com/problems/{slug}/"
        if source == "leetcode"
        else f"https://atcoder.jp/contests/{contest}/tasks/{slug}"
    )
    with h.runtime.sessions() as session, session.begin():
        problem = Problem(
            id=new_id(),
            source=source,
            external_id=slug,
            title=title,
            url=url,
            difficulty_label=difficulty,
            source_tags=list(tags),
            topic_id=topic_id,
            number=number,
            contest=contest,
            created_at=iso_utc(NOW),
        )
        session.add(problem)
        return problem.id


def insert_attempt(
    h: Harness,
    problem_id: str,
    *,
    status: str = "completed",
    context: str = "targeted",
    outcome: str | None = "solved",
    active_seconds: int = 600,
    confidence: int | None = None,
    takeaway: str = "",
    labels: tuple[str, ...] = (),
    finished: datetime = NOW,
) -> str:
    """Insert an attempt straight into the database and return its id.

    An unfinished `mixed` attempt is a hidden assessment.
    """
    done = status == "completed"
    with h.runtime.sessions() as session, session.begin():
        attempt = Attempt(
            id=new_id(),
            problem_id=problem_id,
            context=context,
            status=status,
            evidence="unseen" if context == "mixed" else "near_transfer",
            outcome=outcome if done else None,
            active_seconds=active_seconds,
            confidence=confidence,
            takeaway=takeaway,
            mistake_labels=list(labels),
            started_at=iso_utc(finished - timedelta(seconds=active_seconds)),
            finished_at=iso_utc(finished) if done else None,
            study_date=finished.date().isoformat(),
        )
        session.add(attempt)
        return attempt.id


# ---------------------------------------------------------------- seeding (engine tests)


def seed_problem(
    h: Harness,
    title: str,
    *,
    topic: str | None = None,
    label: str | None = "Easy",
    rating: int | None = None,
    popularity: int | None = None,
    source: str = "leetcode",
    contest: str | None = None,
    paid_only: bool = False,
    number: int | None = None,
) -> str:
    """Add a library problem with a made-up slug, so no zerotrac rating applies.

    `rating` is stored as a fitted estimate.
    """
    slug = "t-" + "-".join(title.lower().split())
    with h.session() as session, session.begin():
        problem = Problem(
            id=new_id(),
            source=source,
            external_id=slug if source == "leetcode" else f"{contest}_{slug[-1]}",
            title=title,
            url=f"https://leetcode.com/problems/{slug}/"
            if source == "leetcode"
            else f"https://atcoder.jp/contests/{contest}/tasks/{contest}_{slug[-1]}",
            difficulty_label=label,
            topic_id=topic,
            contest=contest,
            paid_only=paid_only,
            number=number,
            created_at=iso_utc(NOW),
        )
        session.add(problem)
        session.flush()
        if rating is not None:
            session.add(
                RatingEstimate(
                    problem_id=problem.id,
                    rating=rating,
                    method="test",
                    fitted_at=iso_utc(NOW),
                )
            )
        if popularity is not None:
            session.add(
                ProblemPopularity(
                    problem_id=problem.id,
                    likes=popularity,
                    dislikes=0,
                    percentile=popularity,
                )
            )
        return problem.id


def finish_body(version: int, **overrides: Any) -> dict[str, Any]:
    """A solved-alone finish form; override any field."""
    return {
        "version": version,
        "outcome": "solved",
        "help": "none",
        "time": "10:00",
        "language": "python",
        "notes": "",
        "code": "class Solution: ...",
    } | overrides


@dataclass
class FakeResponse:
    """A canned HTTP response for the bank download."""

    status_code: int
    body: Any

    def json(self) -> Any:
        """Return the canned body."""
        return self.body


def install_fake_bank(h: Harness) -> BankService:
    """The app's bank service, fetching recorded pages instead of LeetCode.

    The pages are agent B's recordings. Call `.join()` on it after POST
    /bank/refresh.
    """
    pages = bank_pages()

    def post(url: str, *, json: Any, headers: Any, timeout: float) -> FakeResponse:
        return FakeResponse(200, pages[json["variables"]["skip"] // 100])

    service = BankService(
        h.runtime.sessions,
        h.runtime.manifests,
        h.runtime.paths.bank_file,
        post=post,
        sleep=lambda _: None,
        clock=h.clock,
    )
    h.state.jobs[BANK_JOB] = service
    return service
