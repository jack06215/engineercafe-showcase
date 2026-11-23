"""Reads the Monkeytype results that the Surfingkeys `yr` mapping copies as YAML.

A file holds one or more YAML documents, one result each. `parse_file` turns a
file into `Result` objects and error messages, and `merge` combines files,
drops results that appear twice and sorts the rest by date. A bad document or
file never hides the others.

    parsed = [parse_file(name, data) for name, data in files]
    loaded = merge(parsed)
"""

import dataclasses
import datetime
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

# libyaml parses a 740-row chart much faster; the pure-Python loader is the
# fallback for a PyYAML build without it.
_LOADER: Any = yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader

RESULT_SUFFIXES = frozenset({".yml", ".yaml"})


@dataclasses.dataclass(frozen=True)
class Keys:
    """Keypresses, as Monkeytype's accuracy tooltip counts them."""

    correct: int
    incorrect: int


@dataclasses.dataclass(frozen=True)
class Chars:
    """Characters of the final text, as Monkeytype's "characters" stat shows them."""

    correct: int
    incorrect: int
    extra: int
    missed: int


@dataclasses.dataclass(frozen=True)
class ChartRow:
    """One second of the result chart. Speeds are in the result's unit."""

    t: float
    wpm: float | None
    raw: float | None
    burst: float | None
    errors: float | None


@dataclasses.dataclass(frozen=True)
class Word:
    """One typed word of the input history.

    Attributes:
        i: Position in the test, from 0.
        word: The target word.
        wpm: Burst speed in the result's unit; `inf` when too fast to measure.
        bucket: Heatmap band, 0 (slowest) to 4; None without a finite speed.
        typed: The first attempt, when it differs from `word`; `_` is a space.
        fixed: Letters fixed with backspace.
        error: Whether the word was still wrong when submitted.
        extra_fixed: Whether an extra letter was typed and deleted.
        marks: One mark per shown letter (`.`, `f`, `x`, `+`, `-`), or None
            when every letter was correct.
        letters: The shown letters, only when there are extras.
    """

    i: int
    word: str
    wpm: float | None
    bucket: int | None
    typed: str | None = None
    fixed: int = 0
    error: bool = False
    extra_fixed: bool = False
    marks: str | None = None
    letters: str | None = None


@dataclasses.dataclass(frozen=True)
class TypedTime:
    """Monkeytype's session or today time, shown under the test time."""

    label: str
    seconds: float


@dataclasses.dataclass(frozen=True)
class Crown:
    """The crown next to the speed: `kind` is normal, pending, ineligible, ..."""

    kind: str
    text: str


@dataclasses.dataclass(frozen=True)
class Result:
    """One Monkeytype result.

    `wpm` and `raw` are always in wpm. The chart, `steps`, word speeds and
    `wpm_threshold` are in `unit`.

    Attributes:
        source: Where it came from, such as "results.yml, document 2".
        copied_at: When `yr` copied it.
    """

    source: str
    copied_at: datetime.datetime
    test: str
    language: str | None
    unit: str
    wpm: float
    raw: float | None = None
    acc: float | None = None
    consistency: float | None = None
    key_consistency: float | None = None
    keys: Keys | None = None
    chars: Chars | None = None
    time: float | None = None
    afk: float | None = None
    afk_pct: float | None = None
    typed_time: TypedTime | None = None
    pb: bool = False
    crown: Crown | None = None
    steps: tuple[float, ...] = ()
    chart: tuple[ChartRow, ...] = ()
    chart_error: str | None = None
    words: tuple[Word, ...] = ()
    flags: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    quote_source: str | None = None
    wpm_threshold: float | None = None
    word_list: tuple[str, ...] = ()
    missed_word_list: tuple[str, ...] = ()
    slow_word: tuple[str, ...] = ()

    @property
    def word_list_name(self) -> str:
        """The word list, or "custom" in custom mode."""
        return self.language or "custom"

    @property
    def identity(self) -> tuple[object, ...]:
        """What makes two copies the same result.

        Copying one result twice gives two dates, so the date is not part of it.
        """
        return (
            self.test,
            self.language,
            self.wpm,
            self.raw,
            self.acc,
            self.consistency,
            self.time,
        )


@dataclasses.dataclass(frozen=True)
class ParsedFile:
    """The results of one file, and what went wrong reading it."""

    name: str
    results: tuple[Result, ...]
    errors: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Loaded:
    """Every result loaded, oldest first, without duplicates.

    Attributes:
        files: Files read, with or without errors.
        duplicates: Results skipped because an equal one was read first.
        errors: One message per bad document or file.
        files_with_errors: Files that had at least one error.
    """

    results: tuple[Result, ...] = ()
    files: int = 0
    duplicates: int = 0
    errors: tuple[str, ...] = ()
    files_with_errors: int = 0


class _DocumentError(ValueError):
    """A document that is not a `yr` result."""


def parse_file(name: str, data: bytes) -> ParsedFile:
    """Reads every result in one file.

    Documents before a YAML syntax error still load; the rest of that file
    does not.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        return ParsedFile(name, (), (f"{name}: not UTF-8 text ({e.reason})",))
    results: list[Result] = []
    errors: list[str] = []
    number = 0
    try:
        for document in yaml.load_all(text, Loader=_LOADER):
            number += 1
            if document is None:
                continue
            source = f"{name}, document {number}"
            try:
                results.append(_result(document, source))
            except _DocumentError as e:
                errors.append(f"{source}: {e}")
    except yaml.YAMLError as e:
        errors.append(f"{name}: {_yaml_error_text(e)}")
    return ParsedFile(name, tuple(results), tuple(errors))


def merge(files: Iterable[ParsedFile]) -> Loaded:
    """Combines parsed files: the first copy of each result wins, oldest first."""
    seen: set[tuple[object, ...]] = set()
    results: list[Result] = []
    errors: list[str] = []
    file_count = duplicates = files_with_errors = 0
    for parsed in files:
        file_count += 1
        errors.extend(parsed.errors)
        files_with_errors += bool(parsed.errors)
        for result in parsed.results:
            if result.identity in seen:
                duplicates += 1
                continue
            seen.add(result.identity)
            results.append(result)
    results.sort(key=lambda result: result.copied_at)
    return Loaded(
        tuple(results), file_count, duplicates, tuple(errors), files_with_errors
    )


def resolve_folder(text: str, environ: Mapping[str, str] | None = None) -> Path:
    """The folder that the results folder box names.

    `bazel run` starts the app in its runfiles folder, so a relative path is
    read from the folder `bazel run` was started in.
    """
    environ = os.environ if environ is None else environ
    path = Path(text.strip()).expanduser()
    if path.is_absolute():
        return path
    base = environ.get("BUILD_WORKING_DIRECTORY")
    return Path(base) / path if base else Path.cwd() / path


def result_files(folder: Path) -> list[Path]:
    """The `.yml` and `.yaml` files directly in `folder`, by name."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.suffix.lower() in RESULT_SUFFIXES and path.is_file()
    )


def _yaml_error_text(error: yaml.YAMLError) -> str:
    if isinstance(error, yaml.MarkedYAMLError) and error.problem_mark is not None:
        problem = error.problem or error.context or "invalid YAML"
        return f"YAML error on line {error.problem_mark.line + 1}: {problem}"
    return f"YAML error: {error}"


def _result(document: object, source: str) -> Result:
    if not isinstance(document, Mapping):
        raise _DocumentError("not a yr result: the document is not a mapping")
    detail = document.get("detail")
    if "datetime" not in document or not isinstance(detail, Mapping):
        raise _DocumentError('not a yr result: needs "datetime:" and "detail:"')
    wpm = _number(detail, "wpm")
    if wpm is None:
        raise _DocumentError("not a yr result: detail has no wpm")
    summary = _mapping(document, "result")
    return Result(
        source=source,
        copied_at=_datetime(document["datetime"]),
        test=_text(detail, "test") or "",
        language=_text(detail, "language"),
        unit=_text(detail, "unit") or "wpm",
        wpm=wpm,
        raw=_number(detail, "raw"),
        acc=_number(detail, "acc"),
        consistency=_number(detail, "consistency"),
        key_consistency=_number(detail, "key_consistency"),
        keys=_keys(detail),
        chars=_chars(detail),
        time=_number(detail, "time"),
        afk=_number(detail, "afk"),
        afk_pct=_number(detail, "afk_pct"),
        typed_time=_typed_time(detail),
        pb=_flag(detail, "pb"),
        crown=_crown(detail),
        steps=_steps(detail),
        chart=_chart(detail),
        chart_error=_text(detail, "chart_error"),
        words=_words(detail),
        flags=_texts(detail, "other"),
        options=_texts(detail, "options"),
        tags=_texts(detail, "tags"),
        quote_source=_text(detail, "source"),
        wpm_threshold=_number(summary, "wpm_threshold"),
        word_list=_word_block(summary, "word_list"),
        missed_word_list=_word_block(summary, "missed_word_list"),
        slow_word=_word_block(summary, "slow_word"),
    )


def _datetime(value: object) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        moment = value
    elif isinstance(value, datetime.date):
        moment = datetime.datetime.combine(value, datetime.time())
    elif isinstance(value, str):
        try:
            moment = datetime.datetime.fromisoformat(value)
        except ValueError:
            raise _DocumentError(f"datetime is not a date: {value!r}") from None
    else:
        raise _DocumentError(f"datetime is not a date: {value!r}")
    # A date without an offset is local time, so that dates compare.
    return moment if moment.tzinfo is not None else moment.astimezone()


def _mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _DocumentError(f"{key} is not a mapping")
    return value


def _number(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _DocumentError(f"{key} is not a number: {value!r}")
    return float(value)


def _count(data: Mapping[str, Any], key: str) -> int:
    value = _number(data, key)
    if value is None:
        return 0
    if not value.is_integer():
        raise _DocumentError(f"{key} is not a whole number: {value!r}")
    return int(value)


def _flag(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _DocumentError(f"{key} is not true or false: {value!r}")
    return value


def _text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _DocumentError(f"{key} is not text: {value!r}")
    return value


def _texts(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    items = value if isinstance(value, list) else [value]
    if not all(isinstance(item, str) for item in items):
        raise _DocumentError(f"{key} is not a list of text: {value!r}")
    return tuple(items)


def _word_block(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    text = _text(data, key)
    return tuple(text.split()) if text else ()


def _keys(detail: Mapping[str, Any]) -> Keys | None:
    if detail.get("keys") is None:
        return None
    keys = _mapping(detail, "keys")
    return Keys(_count(keys, "correct"), _count(keys, "incorrect"))


def _chars(detail: Mapping[str, Any]) -> Chars | None:
    if detail.get("chars") is None:
        return None
    chars = _mapping(detail, "chars")
    return Chars(
        _count(chars, "correct"),
        _count(chars, "incorrect"),
        _count(chars, "extra"),
        _count(chars, "missed"),
    )


def _typed_time(detail: Mapping[str, Any]) -> TypedTime | None:
    for label in ("session", "today"):
        seconds = _number(detail, f"{label}_time")
        if seconds is not None:
            return TypedTime(label, seconds)
    return None


def _crown(detail: Mapping[str, Any]) -> Crown | None:
    if detail.get("crown") is None:
        return None
    crown = _mapping(detail, "crown")
    return Crown(_text(crown, "type") or "", _text(crown, "text") or "")


def _steps(detail: Mapping[str, Any]) -> tuple[float, ...]:
    heatmap = _mapping(detail, "heatmap")
    steps = heatmap.get("steps")
    if steps is None:
        return ()
    if not isinstance(steps, list) or not all(
        isinstance(step, int | float) and not isinstance(step, bool) for step in steps
    ):
        raise _DocumentError(f"heatmap.steps is not a list of numbers: {steps!r}")
    return tuple(float(step) for step in steps)


def _records(detail: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    records = detail.get(key)
    if records is None:
        return []
    if not isinstance(records, list) or not all(
        isinstance(record, Mapping) for record in records
    ):
        raise _DocumentError(f"{key} is not a list of records")
    return records


def _chart(detail: Mapping[str, Any]) -> tuple[ChartRow, ...]:
    rows = []
    for row in _records(detail, "chart"):
        t = _number(row, "t")
        if t is None:
            raise _DocumentError("a chart row has no t")
        rows.append(
            ChartRow(
                t,
                _number(row, "wpm"),
                _number(row, "raw"),
                _number(row, "burst"),
                _number(row, "errors"),
            )
        )
    return tuple(rows)


def _words(detail: Mapping[str, Any]) -> tuple[Word, ...]:
    words = []
    for record in _records(detail, "words"):
        word = _text(record, "word")
        if word is None:
            raise _DocumentError("a word record has no word")
        has_bucket = record.get("bucket") is not None
        words.append(
            Word(
                i=_count(record, "i"),
                word=word,
                wpm=_number(record, "wpm"),
                bucket=_count(record, "bucket") if has_bucket else None,
                typed=_text(record, "typed"),
                fixed=_count(record, "fixed"),
                error=_flag(record, "error"),
                extra_fixed=_flag(record, "extra_fixed"),
                marks=_text(record, "marks"),
                letters=_text(record, "letters"),
            )
        )
    return tuple(words)
