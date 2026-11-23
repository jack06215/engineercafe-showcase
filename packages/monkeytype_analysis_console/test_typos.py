import unittest

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.results import (
    Word,
)
from packages.monkeytype_analysis_console.typos import (
    CATEGORIES,
    KEY_POSITIONS,
    base_key,
    category_counts,
    classify,
    classify_words,
    key_confusions,
    shift_presses,
    symbols,
    wrong_key_kind,
    wrong_keys,
)

# (target, first attempt, left wrong, [(category, detail, confusion)]), each
# recorded from analyze.py at dotfiles commit efca31a, so the port must match it.
CASES = [
    ("the", "teh", False, [("swapped letters", '"he"→"eh"', "he→eh")]),
    ("the", "thr", False, [("wrong key: neighbour", '"e"→"r"', "e→r")]),
    ("red", "rcd", False, [("wrong key: same finger", '"e"→"c"', "e→c")]),
    ("the", "thi", False, [("wrong key: mirror", '"e"→"i"', "e→i")]),
    ("tap", "pap", False, [("wrong key: other", '"t"→"p"', "t→p")]),
    ("The", "the", False, [("Shift error", '"T"→"t"', "T→t")]),
    ("about", "abut", False, [("missing letter", '"o" missing', "")]),
    ("the", "thxe", False, [("extra letter", 'extra "x" before "e"', "")]),
    ("the", "thhe", False, [("doubled letter", 'doubled "h"', "")]),
    ("about", "abo_", True, [("early space", 'space after "abo"', "")]),
    ("about", "ab", True, [("unfinished word", "3 letters not typed", "")]),
    # A slip shifts the rest of the attempt: one extra key plus one missing.
    (
        "Multiply",
        "/Mlti",
        True,
        [
            ("extra letter", 'extra "/" before "M"', ""),
            ("missing letter", '"u" missing', ""),
            ("unfinished word", "3 letters not typed", ""),
        ],
    ),
    # A shifted attempt of a corrected word reads as one extra key...
    (
        "sched_yield",
        "sched_yieol",
        False,
        [("extra letter", 'extra "o" before "l" (neighbour key)', "")],
    ),
    # ...while a wrong last key still reads as a wrong key.
    ("address", "addresd", False, [("wrong key: neighbour", '"s"→"d"', "s→d")]),
    ("test", "tests", True, [("extra letter", 'extra "s" at the end', "")]),
]


def _word(target: str, typed: str | None, error: bool = False) -> Word:
    return Word(i=0, word=target, wpm=40, bucket=1, typed=typed, error=error)


class ClassifyTest(unittest.TestCase):
    def test_matches_analyze_py(self) -> None:
        for target, typed, error, expected in CASES:
            with self.subTest(target=target, typed=typed):
                found = [
                    (typo.category, typo.detail, typo.confusion)
                    for typo in classify(_word(target, typed, error))
                ]
                self.assertEqual(found, expected)

    def test_every_category_is_covered(self) -> None:
        covered: set[str] = set()
        for *_, expected in CASES:
            covered.update(category for category, _, _ in expected)
        self.assertEqual(covered, set(CATEGORIES))

    def test_no_first_attempt_has_no_typos(self) -> None:
        self.assertEqual(classify(_word("salt", None, error=True)), [])


class KeyboardTest(unittest.TestCase):
    def test_base_key(self) -> None:
        self.assertEqual(base_key("A"), "a")
        self.assertEqual(base_key("<"), ",")
        self.assertEqual(base_key("_"), "-")

    def test_wrong_key_kind(self) -> None:
        self.assertEqual(wrong_key_kind("e", "r"), "wrong key: neighbour")
        self.assertEqual(wrong_key_kind("e", "c"), "wrong key: same finger")
        self.assertEqual(wrong_key_kind("e", "i"), "wrong key: mirror")
        self.assertEqual(wrong_key_kind("t", "p"), "wrong key: other")
        self.assertEqual(wrong_key_kind("<", ","), "Shift error")

    def test_key_positions(self) -> None:
        self.assertEqual(len(KEY_POSITIONS), 47)
        self.assertEqual(KEY_POSITIONS["q"], (1.5, 1))
        self.assertEqual(KEY_POSITIONS["a"], (1.75, 2))

    def test_shift_presses_and_symbols(self) -> None:
        self.assertEqual((shift_presses("Vec<T>"), symbols("Vec<T>")), (4, 2))
        self.assertEqual((shift_presses("a_b"), symbols("it's")), (1, 1))


class SummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.classified = classify_words(fixtures.result(fixtures.TYPOS).words)

    def test_only_words_with_a_first_attempt(self) -> None:
        self.assertEqual(
            [item.word.word for item in self.classified],
            ["sneeing", "test", "about", "null", "they"],
        )

    def test_category_counts_in_category_order(self) -> None:
        self.assertEqual(
            category_counts(self.classified),
            [
                ("wrong key: neighbour", 1, ['they ("e"→"r")']),
                ("wrong key: other", 1, ['sneeing ("n"→"e")']),
                ("extra letter", 1, ['test (extra "s" at the end)']),
                ("doubled letter", 1, ['null (doubled "l")']),
                ("early space", 1, ['about (space after "abo")']),
            ],
        )

    def test_examples_are_capped(self) -> None:
        words = [_word("the", "thr") for _ in range(5)]
        [(_, count, examples)] = category_counts(classify_words(words), examples=3)
        self.assertEqual((count, len(examples)), (5, 3))

    def test_key_confusions(self) -> None:
        self.assertEqual(key_confusions(self.classified), {"n→e": 1, "e→r": 1})

    def test_wrong_keys_count_wrong_keys_only_on_their_base_key(self) -> None:
        self.assertEqual(
            wrong_keys(self.classified), {"n": {"n→e": 1}, "e": {"e→r": 1}}
        )
        shifted = classify_words(
            [_word("a<b", "a>b"), _word("The", "the"), _word("the", "teh")]
        )
        # "<" and ">" sit on "," and "."; a Shift error and a swap don't count.
        self.assertEqual(wrong_keys(shifted), {",": {"<→>": 1}})


if __name__ == "__main__":
    unittest.main()
