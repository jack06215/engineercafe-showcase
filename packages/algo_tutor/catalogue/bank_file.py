"""Fetching LeetCode's problem list and reading it back (SPEC.md §5.4).

LeetCode's public GraphQL `questionList(categorySlug: "algorithms")`, without
logging in, in pages of 100, 300 ms apart (about 37 requests). The raw pages
are kept in `<data>/bank/leetcode-bank.json`, so "Add problem" and pasted
lists can find a title without fetching again.

The problem number is `questionFrontendId` and the paid flag `isPaidOnly`.
Unverified against the live API while building (the one probe was refused),
so a missing or non-numeric number is tolerated: numbers also come from the
bundled NeetCode and zerotrac files.
"""

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from packages.algo_tutor.domain import constants
from packages.algo_tutor.domain.enums import Difficulty

GRAPHQL_URL = "https://leetcode.com/graphql"
QUERY = """query bank($skip: Int, $limit: Int) {
  questionList(categorySlug: "algorithms", limit: $limit, skip: $skip, filters: {}) {
    totalNum
    data { questionFrontendId title titleSlug difficulty acRate isPaidOnly likes dislikes topicTags { name } }
  }
}"""
HEADERS = {
    "content-type": "application/json",
    "referer": "https://leetcode.com",
    "user-agent": "algo_tutor (local study app)",
}


class BankFetchError(RuntimeError):
    """The LeetCode bank could not be downloaded."""


@dataclass(frozen=True)
class BankQuestion:
    """One problem from the LeetCode bank download."""

    slug: str
    title: str
    difficulty: Difficulty | None
    ac_rate: float  # percent
    paid_only: bool
    likes: int
    dislikes: int
    tags: tuple[str, ...]
    number: int | None


class _Response(Protocol):
    status_code: int

    def json(self) -> Any: ...


class HttpPost(Protocol):
    """`requests.post`, or a fake in tests."""

    def __call__(
        self, url: str, *, json: Any, headers: Mapping[str, str], timeout: float
    ) -> _Response:
        """Send a POST request with a JSON body."""


def parse_question(raw: Mapping[str, Any]) -> BankQuestion:
    """Build a BankQuestion from one raw question of the download."""
    number_text = str(raw.get("questionFrontendId") or "")
    label = raw.get("difficulty")
    return BankQuestion(
        slug=str(raw["titleSlug"]),
        title=str(raw["title"]),
        difficulty=Difficulty(label)
        if label in {d.value for d in Difficulty}
        else None,
        ac_rate=float(raw.get("acRate") or 0),
        paid_only=bool(raw.get("isPaidOnly")),
        likes=int(raw.get("likes") or 0),
        dislikes=int(raw.get("dislikes") or 0),
        tags=tuple(str(t["name"]) for t in raw.get("topicTags") or []),
        number=int(number_text) if number_text.isdigit() else None,
    )


def questions_from_pages(pages: list[Any]) -> list[BankQuestion]:
    """Every question in the raw GraphQL pages, in order."""
    out = []
    for body in pages:
        for raw in body["data"]["questionList"]["data"]:
            out.append(parse_question(raw))
    return out


def fetch_pages(
    post: HttpPost,
    sleep: Callable[[float], None] = time.sleep,
    page_size: int = constants.BANK_PAGE_SIZE,
    delay: float = constants.BANK_PAGE_DELAY_SECONDS,
    timeout: float = 30,
) -> list[Any]:
    """The raw response bodies, one per page, until `totalNum` is reached."""
    pages: list[Any] = []
    skip, total = 0, None
    while total is None or skip < total:
        response = post(
            GRAPHQL_URL,
            json={"query": QUERY, "variables": {"skip": skip, "limit": page_size}},
            headers=HEADERS,
            timeout=timeout,
        )
        if response.status_code != 200:
            raise BankFetchError(
                f"LeetCode returned {response.status_code} while listing problems."
            )
        body = response.json()
        page = (
            (body.get("data") or {}).get("questionList")
            if isinstance(body, dict)
            else None
        )
        if not page or not isinstance(page.get("data"), list):
            raise BankFetchError("LeetCode returned an unexpected problem listing.")
        total = int(page["totalNum"])
        pages.append(body)
        skip += page_size
        if skip < total:
            sleep(delay)
    return pages


def save_pages(path: Path, pages: list[Any], fetched_at: str) -> None:
    """Keep the last raw download, replacing the previous one atomically."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = path.with_suffix(".partial")
    partial.write_text(
        json.dumps({"fetched_at": fetched_at, "pages": pages}), encoding="utf-8"
    )
    partial.replace(path)


def load_saved(path: Path) -> dict[str, BankQuestion]:
    """The last download's questions by slug; empty if there is none or it's unreadable."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {q.slug: q for q in questions_from_pages(raw["pages"])}
    except OSError, ValueError, KeyError, TypeError:
        return {}
