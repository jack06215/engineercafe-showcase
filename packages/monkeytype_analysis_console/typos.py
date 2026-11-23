"""Typo classification and the keyboard model (SPEC.md §7).

Ported from the monkeytype-review skill, `analyze.py:256-433` in the dotfiles
repo at commit efca31a. Each typo in a word's first attempt is found by
aligning the attempt with the target word, then named by where the keys sit on
a US QWERTY keyboard with the standard touch-typing fingers. This copy may
change without changing the skill's.

    for typo in classify(word):
        print(typo.category, typo.detail, typo.confusion)
"""

import collections
import dataclasses
import math
from collections.abc import Iterable, Sequence

from packages.monkeytype_analysis_console.results import (
    Word,
)

# Each row's offset from the left edge, in key widths, and its keys.
ROWS: tuple[tuple[float, str], ...] = (
    (0.0, "`1234567890-="),
    (1.5, "qwertyuiop[]\\"),
    (1.75, "asdfghjkl;'"),
    (2.25, "zxcvbnm,./"),
)
SHIFTED = dict(zip('~!@#$%^&*()_+{}|:"<>?', "`1234567890-=[]\\;',./", strict=True))
FINGERS: dict[tuple[str, str], str] = {
    ("left", "pinky"): "`1qaz",
    ("left", "ring"): "2wsx",
    ("left", "middle"): "3edc",
    ("left", "index"): "45rtfgvb",
    ("right", "index"): "67yuhjnm",
    ("right", "middle"): "8ik,",
    ("right", "ring"): "9ol.",
    ("right", "pinky"): "0-=p[]\\;'/",
}
# Side and diagonal neighbours are less than this many key widths apart.
NEIGHBOUR_DISTANCE = 1.3
# A wrong key costs more than one extra or missing key but less than two, so a
# slip that shifts the rest of the word ("/Mlti" for "Multi") reads as an
# extra key plus a missing one rather than as two wrong keys.
WRONG_KEY_COST = 1.5

SWAPPED = "swapped letters"
NEIGHBOUR = "wrong key: neighbour"
SAME_FINGER = "wrong key: same finger"
MIRROR = "wrong key: mirror"
OTHER_KEY = "wrong key: other"
SHIFT_ERROR = "Shift error"
MISSING = "missing letter"
EXTRA = "extra letter"
DOUBLED = "doubled letter"
EARLY_SPACE = "early space"
UNFINISHED = "unfinished word"
CATEGORIES = (
    SWAPPED,
    NEIGHBOUR,
    SAME_FINGER,
    MIRROR,
    OTHER_KEY,
    SHIFT_ERROR,
    MISSING,
    EXTRA,
    DOUBLED,
    EARLY_SPACE,
    UNFINISHED,
)
WRONG_KEY_CATEGORIES = frozenset({NEIGHBOUR, SAME_FINGER, MIRROR, OTHER_KEY})


@dataclasses.dataclass(frozen=True)
class Typo:
    """One typo in a word's first attempt.

    Attributes:
        category: One of `CATEGORIES`.
        detail: A short description, such as `"e"→"r"`.
        expected: The letters wanted, for a wrong key, a Shift error or a
            swap; otherwise "".
        typed: The letters typed in their place, under the same condition.
    """

    category: str
    detail: str
    expected: str = ""
    typed: str = ""

    @property
    def confusion(self) -> str:
        """The expected→typed pair, such as "e→r", or "" when there is none."""
        return f"{self.expected}→{self.typed}" if self.expected else ""


@dataclasses.dataclass(frozen=True)
class WordTypos:
    """A word and the typos in its first attempt."""

    word: Word
    typos: tuple[Typo, ...]


def _key_positions() -> dict[str, tuple[float, int]]:
    positions = {}
    for row, (offset, keys) in enumerate(ROWS):
        for i, key in enumerate(keys):
            positions[key] = (offset + i, row)
    return positions


def _fingers_by_key() -> dict[str, tuple[str, str]]:
    fingers = {}
    for finger, keys in FINGERS.items():
        for key in keys:
            fingers[key] = finger
    return fingers


KEY_POSITIONS = _key_positions()
_FINGER_OF = _fingers_by_key()


def base_key(character: str) -> str:
    """The key that types `character`: lower case, and unshifted for symbols."""
    lower = character.lower()
    return SHIFTED.get(lower, lower)


def shift_presses(text: str) -> int:
    """Characters typed with Shift: capitals and shifted symbols."""
    return sum(1 for character in text if character.isupper() or character in SHIFTED)


def symbols(text: str) -> int:
    """Characters that are not letters or digits."""
    return sum(1 for character in text if not character.isalnum())


def wrong_key_kind(expected: str, typed: str) -> str:
    """The category of typing `typed` where `expected` was wanted."""
    wanted, pressed = base_key(expected), base_key(typed)
    if wanted == pressed:
        return SHIFT_ERROR
    wanted_at, pressed_at = KEY_POSITIONS.get(wanted), KEY_POSITIONS.get(pressed)
    if (
        wanted_at
        and pressed_at
        and math.dist(wanted_at, pressed_at) < NEIGHBOUR_DISTANCE
    ):
        return NEIGHBOUR
    wanted_finger, pressed_finger = _FINGER_OF.get(wanted), _FINGER_OF.get(pressed)
    if wanted_finger and pressed_finger:
        if wanted_finger == pressed_finger:
            return SAME_FINGER
        if wanted_finger[1] == pressed_finger[1]:
            return MIRROR  # the same finger of the other hand
    return OTHER_KEY


def classify(word: Word) -> list[Typo]:
    """The typos in the word's first attempt, in typed order.

    A word without `typed` has no first attempt to compare, so no typos.
    """
    target, typed = word.word, word.typed
    if typed is None:
        return []
    # Monkeytype shows a space pressed before the word was finished as `_`.
    early_space = (
        typed.endswith("_")
        and len(typed) <= len(target)
        and target[len(typed) - 1] != "_"
    )
    if early_space:
        typed = typed[:-1]

    # `typed` holds the first key pressed at each position. After an extra or
    # missing key the rest of the word is shifted until the typist notices and
    # backspaces, and a word can be left unfinished, so the end of the target
    # may have no first attempt at all. Let it go unmatched: always after an
    # early space, as one "unfinished" typo for words left wrong, and for
    # corrected words at half the cost of a missing letter, so a shifted
    # attempt ("sched_yieol") reads as one extra key while a wrong last key
    # ("addresd") still reads as a wrong key.
    table = _alignment_costs(target, typed)
    target_length, typed_length = len(target), len(typed)
    end = target_length
    if target_length:
        prefix = min(
            range(target_length),
            key=lambda k: (table[k][typed_length], abs(k - typed_length)),
        )
        unmatched_cost = 1 if word.error else 0.5
        if (
            early_space
            or table[prefix][typed_length] + unmatched_cost
            < table[target_length][typed_length]
        ):
            end = prefix

    typos = [
        _typo(operation, expected, got)
        for operation, expected, got in _edits(table, target, typed, end, typed_length)
    ]
    if early_space:
        typos.append(Typo(EARLY_SPACE, f'space after "{typed}"'))
    elif end < target_length and word.error:
        typos.append(Typo(UNFINISHED, f"{target_length - end} letters not typed"))
    return typos


def classify_words(words: Iterable[Word]) -> list[WordTypos]:
    """Each word that has a first attempt, with its typos."""
    return [WordTypos(word, tuple(classify(word))) for word in words if word.typed]


def category_counts(
    classified: Sequence[WordTypos], examples: int = 3
) -> list[tuple[str, int, list[str]]]:
    """Each category that occurs, in `CATEGORIES` order: its count and examples.

    An example reads like `they ("e"→"r")`.
    """
    counts: collections.Counter[str] = collections.Counter()
    found: dict[str, list[str]] = {}
    for item in classified:
        for typo in item.typos:
            counts[typo.category] += 1
            found.setdefault(typo.category, []).append(
                f"{item.word.word} ({typo.detail})"
            )
    return [
        (category, counts[category], found[category][:examples])
        for category in CATEGORIES
        if counts[category]
    ]


def key_confusions(classified: Iterable[WordTypos]) -> collections.Counter[str]:
    """How often each expected→typed pair occurs."""
    counts: collections.Counter[str] = collections.Counter()
    for item in classified:
        for typo in item.typos:
            if typo.confusion:
                counts[typo.confusion] += 1
    return counts


def wrong_keys(
    classified: Iterable[WordTypos],
) -> dict[str, collections.Counter[str]]:
    """For each wanted key of a wrong-key typo, its confusions and their counts.

    Shifted symbols count on their base key. Shift errors and swaps don't count.
    """
    keys: dict[str, collections.Counter[str]] = {}
    for item in classified:
        for typo in item.typos:
            if typo.category in WRONG_KEY_CATEGORIES:
                keys.setdefault(base_key(typo.expected), collections.Counter())[
                    typo.confusion
                ] += 1
    return keys


def _typo(operation: str, expected: str, got: str) -> Typo:
    if operation == "swap":
        return Typo(SWAPPED, f'"{expected}"→"{got}"', expected, got)
    if operation == "sub":
        return Typo(
            wrong_key_kind(expected, got), f'"{expected}"→"{got}"', expected, got
        )
    if operation == "missing":
        return Typo(MISSING, f'"{expected}" missing')
    if operation == "doubled":
        return Typo(DOUBLED, f'doubled "{got}"')
    where = f' before "{expected}"' if expected else " at the end"
    if expected and wrong_key_kind(expected, got) == NEIGHBOUR:
        where += " (neighbour key)"
    return Typo(EXTRA, f'extra "{got}"{where}')


def _alignment_costs(target: str, typed: str) -> list[list[float]]:
    """Optimal string alignment cost of every target prefix against every typed prefix."""
    rows, columns = len(target), len(typed)
    table = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    for i in range(rows + 1):
        table[i][0] = float(i)
    for j in range(columns + 1):
        table[0][j] = float(j)
    for i in range(1, rows + 1):
        for j in range(1, columns + 1):
            cost = 0 if target[i - 1] == typed[j - 1] else WRONG_KEY_COST
            table[i][j] = min(
                table[i - 1][j] + 1,
                table[i][j - 1] + 1,
                table[i - 1][j - 1] + cost,
            )
            if _is_swap(target, typed, i, j):
                table[i][j] = min(table[i][j], table[i - 2][j - 2] + 1)
    return table


def _edits(
    table: list[list[float]], target: str, typed: str, i: int, j: int
) -> list[tuple[str, str, str]]:
    """The edits that align target[:i] with typed[:j], as (operation, expected, typed).

    For an extra key, `expected` is the next letter wanted.
    """
    edits = []
    while i > 0 or j > 0:
        if (
            i
            and j
            and target[i - 1] == typed[j - 1]
            and table[i][j] == table[i - 1][j - 1]
        ):
            i, j = i - 1, j - 1
        elif _is_swap(target, typed, i, j) and table[i][j] == table[i - 2][j - 2] + 1:
            edits.append(("swap", target[i - 2 : i], typed[j - 2 : j]))
            i, j = i - 2, j - 2
        elif i and j and table[i][j] == table[i - 1][j - 1] + WRONG_KEY_COST:
            edits.append(("sub", target[i - 1], typed[j - 1]))
            i, j = i - 1, j - 1
        elif i and table[i][j] == table[i - 1][j] + 1:
            edits.append(("missing", target[i - 1], ""))
            i -= 1
        else:
            wanted = target[i] if i < len(target) else ""
            doubled = typed[j - 1] in {typed[j - 2] if j > 1 else "", wanted}
            edits.append(("doubled" if doubled else "extra", wanted, typed[j - 1]))
            j -= 1
    return edits[::-1]


def _is_swap(target: str, typed: str, i: int, j: int) -> bool:
    return (
        i > 1
        and j > 1
        and target[i - 1] == typed[j - 2]
        and target[i - 2] == typed[j - 1]
        and target[i - 1] != target[i - 2]
    )
