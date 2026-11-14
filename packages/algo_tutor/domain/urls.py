"""Problem identity from URLs (SPEC §5.1). Pure."""

import re
from dataclasses import dataclass

from packages.algo_tutor.domain.enums import Source

# BloomCode's rule (problem-model.ts), `.cn` included: a slug, an optional
# description/editorial/solutions/submissions tab, a trailing slash, and an
# optional query or fragment.
_LEETCODE = re.compile(
    r"^https://(?:www\.)?leetcode\.(?:com|cn)/problems/([a-z0-9]+(?:-[a-z0-9]+)*)"
    r"(?:/(?:description|editorial|solutions|submissions))?/?(?:\?[^\s#\\]*)?(?:#[^\s\\]*)?$"
)
_ATCODER = re.compile(
    r"^https://atcoder\.jp/contests/([A-Za-z0-9_-]+)/tasks/([A-Za-z0-9_-]+)/?(?:\?[^\s#\\]*)?(?:#[^\s\\]*)?$"
)
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ProblemRef:
    source: Source
    external_id: str  # LeetCode slug or AtCoder task id
    contest: str | None = None  # AtCoder only

    @property
    def url(self) -> str:
        """The canonical URL stored on the problem."""
        if self.source is Source.LEETCODE:
            return f"https://leetcode.com/problems/{self.external_id}/"
        return f"https://atcoder.jp/contests/{self.contest}/tasks/{self.external_id}"


def parse_problem_url(url: str) -> ProblemRef | None:
    """The problem a LeetCode or AtCoder URL names, or None if it's neither."""
    text = url.strip()
    if m := _LEETCODE.match(text):
        return ProblemRef(Source.LEETCODE, m.group(1))
    if m := _ATCODER.match(text):
        return ProblemRef(Source.ATCODER, m.group(2), contest=m.group(1))
    return None


def is_leetcode_slug(text: str) -> bool:
    return bool(_SLUG.match(text))
