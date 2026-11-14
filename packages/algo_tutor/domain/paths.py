"""Suggested solution-file paths (SPEC §6.4, Appendix D). Pure.

The caller lists the repo's existing files (repo-relative, `/`-separated);
this only decides names. Checking a path the learner confirms (inside the
repo, a regular UTF-8 file under 1 MB) is I/O and lives in the API layer.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from packages.algo_tutor.domain.enums import Difficulty, Language, Source

LEETCODE_SRC = "packages/programming_exercise/leetcode/src"
ATCODER_SRC = "packages/programming_exercise/atcoder/src"

EXTENSIONS: dict[Language, str] = {
    Language.PYTHON: ".py",
    Language.GO: ".go",
    Language.TYPESCRIPT: ".ts",
}

_NON_WORD = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class PathSuggestion:
    path: str  # repo-relative
    exists: bool  # an existing file was found; otherwise a new path to create
    alternatives: tuple[str, ...] = ()  # other existing matches (e.g. `_v2` files)


def snake(text: str) -> str:
    """Lowercase with runs of anything but [a-z0-9] collapsed to `_`."""
    return _NON_WORD.sub("_", text.lower()).strip("_")


def leetcode_file_name(
    number: int | None,
    slug: str,
    label: Difficulty | None,
    language: Language,
) -> str:
    """`<NNNN>_<slug with - → _>_<label lowercase>.<ext>`, e.g. `0088_merge_sorted_array_easy.py`.

    With no number the name starts at the slug; with no label the suffix is dropped.
    """
    parts = [] if number is None else [f"{number:04d}"]
    parts.append(slug.replace("-", "_"))
    if label is not None:
        parts.append(label.value.lower())
    return "_".join(parts) + EXTENSIONS[language]


def atcoder_file_name(task_id: str, title: str, language: Language) -> str:
    """`<part of the task id after the last _>_<title snake_case>.<ext>`, e.g. `e_logs.py`."""
    suffix = task_id.rsplit("_", 1)[-1]
    words = snake(title)
    return (f"{suffix}_{words}" if words else suffix) + EXTENSIONS[language]


def _matches(existing: Iterable[str], folder: str, prefix: str, ext: str) -> list[str]:
    """Existing files under `folder` whose name starts with `prefix` and ends with `ext`, in order."""
    root = PurePosixPath(folder)
    found = []
    for path in existing:
        p = PurePosixPath(path)
        if p.name.startswith(prefix) and p.suffix == ext and root in p.parents:
            found.append(path)
    return sorted(found, key=lambda f: (PurePosixPath(f).name, f))


def suggest_leetcode_path(
    *,
    number: int | None,
    slug: str,
    label: Difficulty | None,
    language: Language,
    topic_folder: str | None,
    existing: Iterable[str],
) -> PathSuggestion:
    """An existing file whose name starts with the problem's 4-digit number
    and has the language's extension, else a new path under the primary
    topic's folder (the `leetcode/src` root with no topic).
    """
    ext = EXTENSIONS[language]
    if number is not None:
        found = _matches(existing, LEETCODE_SRC, f"{number:04d}_", ext)
        if found:
            return PathSuggestion(found[0], True, tuple(found[1:]))
    folder = f"{LEETCODE_SRC}/{topic_folder}" if topic_folder else LEETCODE_SRC
    return PathSuggestion(
        f"{folder}/{leetcode_file_name(number, slug, label, language)}", False
    )


def suggest_atcoder_path(
    *,
    contest: str,
    task_id: str,
    title: str,
    language: Language,
    existing: Iterable[str],
) -> PathSuggestion:
    """`atcoder/src/<contest, - → _>/<task suffix>_<title_snake>.<ext>`.

    An existing file in that folder starting with `<task suffix>_` wins
    (`abc174_e` finds `abc174/e_logs.py`). Tessoku-book files use the book's
    own numbering (`a06_…`), so those suggestions get edited.
    """
    folder = f"{ATCODER_SRC}/{contest.replace('-', '_')}"
    ext = EXTENSIONS[language]
    suffix = task_id.rsplit("_", 1)[-1]
    found = [
        f
        for f in _matches(existing, folder, f"{suffix}_", ext)
        if str(PurePosixPath(f).parent) == folder
    ]
    if found:
        return PathSuggestion(found[0], True, tuple(found[1:]))
    path = f"{folder}/{atcoder_file_name(task_id, title, language)}"
    return PathSuggestion(path, path in set(existing))


def suggest_path(
    *,
    source: Source,
    external_id: str,
    title: str,
    language: Language,
    existing: Iterable[str],
    number: int | None = None,
    label: Difficulty | None = None,
    topic_folder: str | None = None,
    contest: str | None = None,
) -> PathSuggestion:
    """`GET /api/problems/{id}/suggested-path`: dispatch on the problem's source."""
    files = list(existing)
    if source is Source.LEETCODE:
        return suggest_leetcode_path(
            number=number,
            slug=external_id,
            label=label,
            language=language,
            topic_folder=topic_folder,
            existing=files,
        )
    if contest is None:
        raise ValueError("An AtCoder problem needs its contest")
    return suggest_atcoder_path(
        contest=contest,
        task_id=external_id,
        title=title,
        language=language,
        existing=files,
    )
