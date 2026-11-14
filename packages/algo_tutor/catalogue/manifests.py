"""The bundled data in `manifests/` (SPEC.md §5.3), checked and parsed.

The upstream files are pinned by SHA-256; a mismatch stops startup with the
file's name. `topics.yaml` is ours and validated by `TopicCatalog` instead.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from packages.algo_tutor.domain.enums import BundledSet, Difficulty
from packages.algo_tutor.domain.topics import TopicCatalog, TopicCatalogError

# Beside the code in the runfiles tree, so `bazel run` and `bazel test` read the same files.
MANIFEST_DIR = Path(__file__).parent.parent / "manifests"

# neetcode-gh/leetcode @ 9f104d45b1efc8c2e42b6dcc7b1216cdf8c4f80e, MIT.
NEETCODE_FILE = "neetcode-problems.json"
NEETCODE_REVISION = "9f104d45b1efc8c2e42b6dcc7b1216cdf8c4f80e"
# zerotrac/leetcode_problem_rating @ 8c7a54008482a8b7464bedfb8ca2f3ea172aa0df, MIT.
ZEROTRAC_FILE = "zerotrac-ratings.txt"
# BloomCode @ b0a6975, hand-made from Hello Interview's table of contents.
STUDY_SETS_FILE = "study-sets.json"
TOPICS_FILE = "topics.yaml"

PINNED_SHA256 = {
    NEETCODE_FILE: "436dd487beb9126e30e9da8717ff76f2a78e3a94ca0ec4181d9d04de9f7b953c",
    ZEROTRAC_FILE: "c0da4136769e9f86e8faaccc5b710430a34075a7525c08783afaf8c572f3c58d",
    STUDY_SETS_FILE: "82b111972389da0b311f1536e8d05b18a8c038c0e74a0f72d15b4f9a0703c6d1",
}

_NEETCODE_SOURCE = f"https://github.com/neetcode-gh/leetcode/blob/{NEETCODE_REVISION}/.problemSiteData.json"
_CODE = re.compile(r"^(\d{4})-")


class ManifestError(ValueError):
    """A bundled file is missing, altered or malformed. The message names it."""


@dataclass(frozen=True)
class KnownProblem:
    """A LeetCode problem the bundled data names, with what it knows about it."""

    slug: str
    title: str
    difficulty: Difficulty | None
    number: int | None = None
    neetcode_category: str | None = None  # only for problems in the NeetCode list


@dataclass(frozen=True)
class CourseSection:
    name: str
    slugs: tuple[str, ...]


@dataclass(frozen=True)
class Course:
    """A bundled course "Follow" can turn into a study list (SPEC §5.10)."""

    id: BundledSet
    name: str
    source_url: str
    sections: tuple[CourseSection, ...]

    def slugs(self) -> list[str]:
        return [slug for section in self.sections for slug in section.slugs]


@dataclass(frozen=True)
class ExactRating:
    rating: int  # zerotrac's contest rating, rounded
    number: int  # LeetCode's problem number
    title: str


@dataclass(frozen=True)
class Manifests:
    topics: TopicCatalog
    exact_ratings: dict[str, ExactRating]  # by slug
    neetcode: dict[str, KnownProblem]  # every row of the NeetCode list, by slug
    courses: dict[BundledSet, Course]
    # Every LeetCode problem the bundled files name, merged, by slug: NeetCode
    # first, then the courses, then zerotrac (titles and numbers only).
    known: dict[str, KnownProblem] = field(default_factory=dict)
    by_title: dict[str, KnownProblem] = field(default_factory=dict)  # casefolded title

    def find_title(self, title: str) -> KnownProblem | None:
        """A known problem whose title matches exactly, ignoring case."""
        return self.by_title.get(title.strip().casefold())


def _read_pinned(directory: Path, name: str) -> bytes:
    path = directory / name
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"{name}: can't read {path}: {exc.strerror}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PINNED_SHA256[name]:
        raise ManifestError(
            f"{name}: SHA-256 {digest} doesn't match the pinned {PINNED_SHA256[name]}"
        )
    return raw


def _difficulty(value: Any) -> Difficulty | None:
    return Difficulty(value) if value in {d.value for d in Difficulty} else None


def parse_zerotrac(text: str) -> dict[str, ExactRating]:
    """zerotrac's TSV: Rating, ID, Title, Title ZH, Title Slug, Contest Slug, Problem Index."""
    out = {}
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        out[cols[4]] = ExactRating(
            rating=round(float(cols[0])), number=int(cols[1]), title=cols[2]
        )
    return out


def _neetcode(raw: bytes) -> tuple[dict[str, KnownProblem], list[dict[str, Any]]]:
    rows = json.loads(raw)
    problems: dict[str, KnownProblem] = {}
    for row in rows:
        slug = str(row["link"]).strip("/")
        code = _CODE.match(str(row.get("code", "")))
        problems[slug] = KnownProblem(
            slug=slug,
            title=str(row["problem"]),
            difficulty=_difficulty(row.get("difficulty")),
            number=int(code.group(1)) if code else None,
            neetcode_category=str(row["pattern"]),
        )
    return problems, rows


def _neetcode_course(
    set_id: BundledSet, name: str, flag: str, rows: list[dict[str, Any]], count: int
) -> Course:
    """A NeetCode course in manifest order, one section per pattern."""
    sections: dict[str, list[str]] = {}
    for row in rows:
        if row.get(flag):
            sections.setdefault(str(row["pattern"]), []).append(
                str(row["link"]).strip("/")
            )
    total = sum(len(s) for s in sections.values())
    if total != count:
        raise ManifestError(
            f"{NEETCODE_FILE}: {name} has {total} problems, expected {count}"
        )
    return Course(
        id=set_id,
        name=name,
        source_url=_NEETCODE_SOURCE,
        sections=tuple(CourseSection(n, tuple(s)) for n, s in sections.items()),
    )


def load_manifests(directory: Path = MANIFEST_DIR) -> Manifests:
    """Read, check and parse every file in `manifests/`."""
    try:
        topics = TopicCatalog.from_mapping(
            yaml.safe_load((directory / TOPICS_FILE).read_text(encoding="utf-8"))
        )
    except (OSError, yaml.YAMLError, TopicCatalogError) as exc:
        raise ManifestError(f"{TOPICS_FILE}: {exc}") from exc

    try:
        exact = parse_zerotrac(_read_pinned(directory, ZEROTRAC_FILE).decode("utf-8"))
    except (ValueError, IndexError) as exc:
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError(f"{ZEROTRAC_FILE}: {exc}") from exc

    try:
        neetcode, rows = _neetcode(_read_pinned(directory, NEETCODE_FILE))
        courses = {
            BundledSet.NEETCODE_150: _neetcode_course(
                BundledSet.NEETCODE_150, "NeetCode 150", "neetcode150", rows, 150
            ),
            BundledSet.BLIND_75: _neetcode_course(
                BundledSet.BLIND_75, "Blind 75", "blind75", rows, 75
            ),
        }
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError(f"{NEETCODE_FILE}: {exc!r}") from exc

    known: dict[str, KnownProblem] = dict(neetcode)
    try:
        sets = json.loads(_read_pinned(directory, STUDY_SETS_FILE))["sets"]
        for s in sets:
            set_id = BundledSet(s["id"])
            sections = []
            for section in s["sections"]:
                slugs = []
                for p in section["problems"]:
                    slugs.append(p["slug"])
                    known.setdefault(
                        p["slug"],
                        KnownProblem(
                            p["slug"], str(p["title"]), _difficulty(p.get("difficulty"))
                        ),
                    )
                sections.append(CourseSection(str(section["name"]), tuple(slugs)))
            courses[set_id] = Course(
                set_id, str(s["name"]), str(s["source"]), tuple(sections)
            )
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError(f"{STUDY_SETS_FILE}: {exc!r}") from exc

    # Fill in problem numbers from zerotrac where NeetCode's code didn't give
    # one, then add zerotrac's other problems (title and number, no label).
    for slug, problem in known.items():
        if problem.number is None and slug in exact:
            known[slug] = KnownProblem(
                slug,
                problem.title,
                problem.difficulty,
                exact[slug].number,
                problem.neetcode_category,
            )
    for slug, rated in exact.items():
        known.setdefault(slug, KnownProblem(slug, rated.title, None, rated.number))
    by_title: dict[str, KnownProblem] = {}
    for problem in known.values():
        by_title.setdefault(problem.title.casefold(), problem)
    return Manifests(
        topics=topics,
        exact_ratings=exact,
        neetcode=neetcode,
        courses=courses,
        known=known,
        by_title=by_title,
    )
