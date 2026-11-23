"""Claude requests for the Practice page (SPEC.md §13), and checks of the answers.

A request holds only what the console's own code computed from the newest
results: recurring words, their counts and typos, and repeated key confusions.
It never holds file names, dates or stats such as wpm. Each answer is checked
against its request, and what wasn't asked for is dropped.

    found = problems(results)
    grouping = group_by_cause(client, found)
    text = write_practice_text(client, found, 50, grouping.groups[0])
"""

import collections
import dataclasses
import json
import math
import re
from collections.abc import Iterable, Sequence
from typing import Any, Literal

import anthropic
from anthropic.types.beta import BetaContentBlock

from packages.monkeytype_analysis_console.progress import (
    latest_results,
    recurring_problems,
    repeated_confusions,
)
from packages.monkeytype_analysis_console.results import (
    Result,
)
from packages.monkeytype_analysis_console.typos import (
    classify_words,
)

MODEL = "claude-opus-5-5"
GROUP_EFFORT: Literal["high"] = "high"
TEXT_EFFORT: Literal["medium"] = "medium"
TIMEOUT = 120.0  # seconds per attempt; the SDK retries twice on its own
MAX_TOKENS = 16000
# Lets the API retry a declined request on another model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
KEYBOARD = "US QWERTY, touch typing"
MAX_GROUPS = 6
MIN_GROUP_ITEMS = 2

KEY_REJECTED = "Claude didn't accept the API key. Check ANTHROPIC_API_KEY."
RATE_LIMITED = "Too many requests. Try again in {seconds} seconds."
RATE_LIMITED_NO_WAIT = "Too many requests. Try again in a minute."
BUSY = "Claude is busy. Try again in a minute."
NO_CONNECTION = "Couldn't reach Claude. Check your connection."
DECLINED = "Claude declined this request."
INCOMPLETE = "Claude's answer was incomplete. Try again."
OTHER_ERROR = "Claude returned an error: {message}"

GROUP_INSTRUCTIONS = """\
You help a touch typist decide what to practise on Monkeytype. The user \
message is JSON. "words" holds the words they keep typing slowly or wrongly: \
in how many recent results each one was slow or mistyped, and the typos in \
its first attempts. "confusions" holds the key confusions they keep making; \
in "e→r", the letters before the arrow are what they meant to press and the \
letters after it are what they pressed.

Group the words and confusions by a cause they share, such as a finger or \
hand, a reach between rows, a letter pair, a word ending, or a habit of \
typing a similar word.

- Use only the words and confusions given, spelled exactly as given.
- Put each item in at most one group. Leave out an item that fits no group.
- Make 1 to 6 groups, each with at least 2 items.
- Name each group in 2 to 5 words. Give its cause in one sentence."""

TEXT_INSTRUCTIONS = """\
You write practice texts that a touch typist types in Monkeytype's custom \
mode. The user message is JSON. "words" holds the words they keep typing \
slowly or wrongly, with in how many recent results each one was a problem. \
"confusions" holds the key confusions they keep making. "focus", when it is \
there, names the cause these problems share.

- Write about "length_words" words of English for a typing test.
- Use every given word at least once. Use the words with more "results" more \
often.
- Include words that practise each confusion. In a confusion such as "e→r", \
the letters before the arrow are what the typist meant to press, and the \
letters after it are what they pressed.
- Use lower case letters and spaces only, unless a given word has capitals or \
symbols. Use ASCII characters only.
- Sentences may be odd, but they should read as English, not as a list of \
words."""

_STRINGS = {"type": "array", "items": {"type": "string"}}
GROUP_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "cause": {"type": "string"},
                    "words": _STRINGS,
                    "confusions": _STRINGS,
                },
                "required": ["name", "cause", "words", "confusions"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["groups"],
    "additionalProperties": False,
}
TEXT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


class ClaudeError(Exception):
    """A request that gave no answer. The message is for the page to show."""


@dataclasses.dataclass(frozen=True)
class TypoCount:
    """How often one typo occurred in a word's first attempts."""

    category: str
    detail: str
    count: int


@dataclasses.dataclass(frozen=True)
class ProblemWord:
    """A recurring word (§5) and the typos of its first attempts.

    Attributes:
        results: Results it was slow or mistyped in.
        slow: Results it was slow in.
        mistyped: Results it was mistyped in.
        typos: The typos of its first attempts in the same results.
    """

    word: str
    results: int
    slow: int
    mistyped: int
    typos: tuple[TypoCount, ...]


@dataclasses.dataclass(frozen=True)
class Confusion:
    """A key confusion seen at least twice, and the typo category it is from."""

    pair: str
    count: int
    category: str


@dataclasses.dataclass(frozen=True)
class Problems:
    """What the Practice page works from: the newest results' problems."""

    words: tuple[ProblemWord, ...] = ()
    confusions: tuple[Confusion, ...] = ()

    @property
    def empty(self) -> bool:
        """True when there is nothing to practise."""
        return not self.words and not self.confusions


@dataclasses.dataclass(frozen=True)
class Usage:
    """The tokens one request used."""

    input_tokens: int
    output_tokens: int


@dataclasses.dataclass(frozen=True)
class Group:
    """Problems that share a cause, as Claude named them."""

    name: str
    cause: str
    words: tuple[str, ...]
    confusions: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Grouping:
    """Checked cause groups, and the items Claude left in no group.

    Attributes:
        problems: The problems the request was made from.
    """

    problems: Problems
    groups: tuple[Group, ...]
    ungrouped_words: tuple[str, ...]
    ungrouped_confusions: tuple[str, ...]
    usage: Usage


@dataclasses.dataclass(frozen=True)
class PracticeText:
    """A checked practice text.

    Attributes:
        problems: The problems the request was made from.
        text: The text, each run of whitespace made one space.
        unusual: Characters outside printable ASCII, in order of appearance.
        word_count: Words in the text.
        coverage: Each requested word and how often it appears as a whole word.
    """

    problems: Problems
    text: str
    unusual: tuple[str, ...]
    word_count: int
    coverage: tuple[tuple[str, int], ...]
    usage: Usage

    @property
    def unused(self) -> list[str]:
        """The requested words that don't appear in the text."""
        return [word for word, count in self.coverage if not count]


def problems(results: Iterable[Result]) -> Problems:
    """The recurring words and repeated confusions of the newest results."""
    results = list(results)
    typos: dict[str, collections.Counter[tuple[str, str]]] = {}
    categories: dict[str, collections.Counter[str]] = {}
    for result in latest_results(results):
        for item in classify_words(result.words):
            for typo in item.typos:
                typos.setdefault(item.word.word, collections.Counter())[
                    (typo.category, typo.detail)
                ] += 1
                if typo.confusion:
                    categories.setdefault(typo.confusion, collections.Counter())[
                        typo.category
                    ] += 1
    words = tuple(
        ProblemWord(
            item.word,
            item.results,
            item.slow,
            item.mistyped,
            tuple(
                TypoCount(category, detail, count)
                for (category, detail), count in typos.get(
                    item.word, collections.Counter()
                ).most_common()
            ),
        )
        for item in recurring_problems(results)
    )
    confusions = tuple(
        Confusion(pair, count, categories[pair].most_common(1)[0][0])
        for pair, count in repeated_confusions(results)
    )
    return Problems(words, confusions)


def group_content(found: Problems) -> dict[str, Any]:
    """The content of a cause-group request (§13.4)."""
    return {
        "keyboard": KEYBOARD,
        "words": [
            {
                "word": word.word,
                "results": word.results,
                "slow": word.slow,
                "mistyped": word.mistyped,
                "typos": [
                    {"category": typo.category, "detail": typo.detail, "count": typo.count}
                    for typo in word.typos
                ],
            }
            for word in found.words
        ],
        "confusions": [
            {"pair": item.pair, "count": item.count, "category": item.category}
            for item in found.confusions
        ],
    }


def text_content(
    found: Problems, length: int, focus: Group | None = None
) -> dict[str, Any]:
    """The content of a practice-text request (§13.5).

    With a focus, only the group's words and confusions go in, with its name
    and cause.
    """
    words = found.words
    confusions = found.confusions
    if focus is not None:
        words = tuple(word for word in words if word.word in focus.words)
        confusions = tuple(item for item in confusions if item.pair in focus.confusions)
    content: dict[str, Any] = {
        "length_words": length,
        "words": [{"word": word.word, "results": word.results} for word in words],
        "confusions": [{"pair": item.pair, "count": item.count} for item in confusions],
    }
    if focus is not None:
        content["focus"] = {"name": focus.name, "cause": focus.cause}
    return content


def request_text(content: dict[str, Any]) -> str:
    """The user message of a request: its content as JSON."""
    return json.dumps(content, ensure_ascii=False, indent=2)


def group_by_cause(client: anthropic.Anthropic, found: Problems) -> Grouping:
    """Asks Claude to group the problems by cause, and checks the answer.

    Raises:
        ClaudeError: The request failed or the answer can't be used.
    """
    answer, usage = _ask(
        client, GROUP_INSTRUCTIONS, group_content(found), GROUP_SCHEMA, GROUP_EFFORT
    )
    raw = [
        Group(
            _string(_field(item, "name")).strip(),
            _string(_field(item, "cause")).strip(),
            tuple(_strings(_field(item, "words"))),
            tuple(_strings(_field(item, "confusions"))),
        )
        for item in _list(_field(answer, "groups"))
    ]
    return check_groups(found, raw, usage)


def check_groups(found: Problems, raw: Sequence[Group], usage: Usage) -> Grouping:
    """Drops what wasn't asked for, repeated items and small groups (§13.4).

    An item counts as taken only once a group that holds it is kept.
    """
    known_words = [word.word for word in found.words]
    known_pairs = [item.pair for item in found.confusions]
    taken_words: set[str] = set()
    taken_pairs: set[str] = set()
    groups: list[Group] = []
    for group in raw:
        if len(groups) == MAX_GROUPS:
            break
        words = _new_items(group.words, known_words, taken_words)
        pairs = _new_items(group.confusions, known_pairs, taken_pairs)
        if len(words) + len(pairs) < MIN_GROUP_ITEMS:
            continue
        groups.append(Group(group.name, group.cause, words, pairs))
        taken_words.update(words)
        taken_pairs.update(pairs)
    return Grouping(
        found,
        tuple(groups),
        tuple(word for word in known_words if word not in taken_words),
        tuple(pair for pair in known_pairs if pair not in taken_pairs),
        usage,
    )


def write_practice_text(
    client: anthropic.Anthropic,
    found: Problems,
    length: int,
    focus: Group | None = None,
) -> PracticeText:
    """Asks Claude for a practice text, and checks the answer.

    Raises:
        ClaudeError: The request failed or the answer can't be used.
    """
    content = text_content(found, length, focus)
    answer, usage = _ask(client, TEXT_INSTRUCTIONS, content, TEXT_SCHEMA, TEXT_EFFORT)
    words = [item["word"] for item in content["words"]]
    return check_text(found, words, _string(_field(answer, "text")), usage)


def check_text(
    found: Problems, words: Sequence[str], text: str, usage: Usage
) -> PracticeText:
    """Tidies the whitespace and counts what the page shows (§13.5)."""
    text = " ".join(text.split())
    unusual = tuple(dict.fromkeys(char for char in text if not " " <= char <= "~"))
    coverage = tuple(
        (word, len(re.findall(rf"(?<!\w){re.escape(word)}(?!\w)", text)))
        for word in words
    )
    return PracticeText(found, text, unusual, len(text.split()), coverage, usage)


def _ask(
    client: anthropic.Anthropic,
    instructions: str,
    content: dict[str, Any],
    schema: dict[str, object],
    effort: Literal["high", "medium"],
) -> tuple[object, Usage]:
    try:
        message = client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=instructions,
            messages=[{"role": "user", "content": request_text(content)}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            betas=[FALLBACK_BETA],
            fallbacks="default",
            timeout=TIMEOUT,
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise ClaudeError(KEY_REJECTED) from e
    except anthropic.RateLimitError as e:
        raise ClaudeError(_rate_limited(e.response.headers.get("retry-after"))) from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise ClaudeError(BUSY) from e
        raise ClaudeError(OTHER_ERROR.format(message=e.message)) from e
    except anthropic.APIConnectionError as e:
        raise ClaudeError(NO_CONNECTION) from e
    except anthropic.APIError as e:
        raise ClaudeError(OTHER_ERROR.format(message=e.message)) from e
    if message.stop_reason == "refusal":
        raise ClaudeError(DECLINED)
    if message.stop_reason != "end_turn":
        raise ClaudeError(INCOMPLETE)
    try:
        answer = json.loads(_answer_text(message.content))
    except json.JSONDecodeError as e:
        raise ClaudeError(INCOMPLETE) from e
    return answer, Usage(message.usage.input_tokens, message.usage.output_tokens)


def _answer_text(content: Sequence[BetaContentBlock]) -> str:
    # A model that declined and handed over to a fallback model may have
    # written text before the fallback block; only the text after it counts.
    parts: list[str] = []
    for block in content:
        if block.type == "fallback":
            parts = []
        elif block.type == "text":
            parts.append(block.text)
    return "".join(parts)


def _rate_limited(retry_after: str | None) -> str:
    try:
        seconds = math.ceil(float(retry_after or ""))
    except ValueError:
        return RATE_LIMITED_NO_WAIT
    return RATE_LIMITED.format(seconds=seconds)


def _new_items(
    items: Iterable[str], known: Sequence[str], taken: set[str]
) -> tuple[str, ...]:
    return tuple(
        item for item in dict.fromkeys(items) if item in known and item not in taken
    )


def _field(value: object, name: str) -> object:
    if not isinstance(value, dict) or name not in value:
        raise ClaudeError(INCOMPLETE)
    return value[name]


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ClaudeError(INCOMPLETE)
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ClaudeError(INCOMPLETE)
    return value


def _strings(value: object) -> list[str]:
    return [_string(item) for item in _list(value)]
