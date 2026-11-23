"""Tests for practice.py: request content, request settings and answer checks."""

import json
import unittest
from typing import Any

import anthropic

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.practice import (
    BUSY,
    DECLINED,
    FALLBACK_BETA,
    GROUP_EFFORT,
    INCOMPLETE,
    KEY_REJECTED,
    MODEL,
    NO_CONNECTION,
    TEXT_EFFORT,
    TIMEOUT,
    ClaudeError,
    Confusion,
    Group,
    Problems,
    ProblemWord,
    TypoCount,
    Usage,
    check_text,
    group_by_cause,
    group_content,
    problems,
    request_text,
    text_content,
    write_practice_text,
)
from packages.monkeytype_analysis_console.results import (
    merge,
)

NEIGHBOUR = "wrong key: neighbour"
USAGE = Usage(1234, 56)


def _problems(*paths: Any) -> Problems:
    return problems(merge([fixtures.read(path) for path in paths]).results)


def _word(word: str, results: int = 2) -> ProblemWord:
    return ProblemWord(word, results, 0, results, ())


def _confusion(pair: str, count: int = 2) -> Confusion:
    return Confusion(pair, count, NEIGHBOUR)


def _group(
    name: str, words: list[str], confusions: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "name": name,
        "cause": f"{name}.",
        "words": words,
        "confusions": list(confusions),
    }


def _sent(client: Any, call: int = 0) -> dict[str, Any]:
    """The keyword arguments of one request the fake client got."""
    return client.beta.messages.create.call_args_list[call].kwargs


def _content(client: Any, call: int = 0) -> dict[str, Any]:
    """The content of one request, read back from its user message."""
    (message,) = _sent(client, call)["messages"]
    return json.loads(message["content"])


class ProblemsTest(unittest.TestCase):
    def test_words_carry_their_typos_and_confusions_their_category(self) -> None:
        found = _problems(fixtures.PROGRESS)
        self.assertEqual(
            [(w.word, w.results, w.slow, w.mistyped) for w in found.words],
            [
                ("century", 3, 3, 0),
                ("salt", 2, 0, 2),
                ("self", 2, 2, 0),
                ("they", 2, 0, 2),
            ],
        )
        they = found.words[-1]
        self.assertEqual(they.typos, (TypoCount(NEIGHBOUR, '"e"→"r"', 2),))
        self.assertEqual(found.confusions, (Confusion("e→r", 2, NEIGHBOUR),))
        self.assertFalse(found.empty)

    def test_nothing_recurring(self) -> None:
        self.assertTrue(_problems(fixtures.REAL, fixtures.CHART_ERROR).empty)


class RequestContentTest(unittest.TestCase):
    def test_group_content_holds_only_words_counts_typos_and_confusions(self) -> None:
        content = group_content(_problems(fixtures.PROGRESS))
        self.assertEqual(set(content), {"keyboard", "words", "confusions"})
        for word in content["words"]:
            self.assertEqual(
                set(word), {"word", "results", "slow", "mistyped", "typos"}
            )
        self.assertEqual(
            content["words"][-1]["typos"],
            [{"category": NEIGHBOUR, "detail": '"e"→"r"', "count": 2}],
        )
        self.assertEqual(
            content["confusions"],
            [{"pair": "e→r", "count": 2, "category": NEIGHBOUR}],
        )
        text = request_text(content)
        for left_out in ("progress.yml", "2026", "wpm", "acc"):
            self.assertNotIn(left_out, text)

    def test_text_content_without_focus_holds_every_problem(self) -> None:
        content = text_content(_problems(fixtures.PROGRESS), 40)
        self.assertEqual(
            content,
            {
                "length_words": 40,
                "words": [
                    {"word": "century", "results": 3},
                    {"word": "salt", "results": 2},
                    {"word": "self", "results": 2},
                    {"word": "they", "results": 2},
                ],
                "confusions": [{"pair": "e→r", "count": 2}],
            },
        )

    def test_focus_sends_only_the_group(self) -> None:
        focus = Group("Left index reach", "It reaches.", ("they", "salt"), ("e→r",))
        content = text_content(_problems(fixtures.PROGRESS), 50, focus)
        self.assertEqual(
            [word["word"] for word in content["words"]], ["salt", "they"]
        )
        self.assertEqual(content["confusions"], [{"pair": "e→r", "count": 2}])
        self.assertEqual(
            content["focus"], {"name": "Left index reach", "cause": "It reaches."}
        )


class RequestSettingsTest(unittest.TestCase):
    def test_group_request(self) -> None:
        found = _problems(fixtures.PROGRESS)
        client = fixtures.fake_claude(fixtures.claude_message({"groups": []}))
        group_by_cause(client, found)
        sent = _sent(client)
        self.assertEqual(sent["model"], MODEL)
        self.assertEqual(sent["output_config"]["effort"], GROUP_EFFORT)
        self.assertEqual(GROUP_EFFORT, "high")
        self.assertEqual(sent["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(sent["betas"], [FALLBACK_BETA])
        self.assertEqual(sent["fallbacks"], "default")
        self.assertEqual(sent["timeout"], TIMEOUT)
        self.assertEqual(_content(client), group_content(found))

    def test_text_request(self) -> None:
        found = _problems(fixtures.PROGRESS)
        client = fixtures.fake_claude(fixtures.claude_message({"text": "salt"}))
        write_practice_text(client, found, 30)
        sent = _sent(client)
        self.assertEqual(sent["model"], MODEL)
        self.assertEqual(sent["output_config"]["effort"], TEXT_EFFORT)
        self.assertEqual(TEXT_EFFORT, "medium")
        self.assertEqual(_content(client), text_content(found, 30))


class GroupCheckTest(unittest.TestCase):
    found = Problems(
        tuple(_word(word) for word in ("they", "the", "salt", "self", "sell")),
        (_confusion("e→r"), _confusion("t→r")),
    )

    def group(self, groups: list[dict[str, Any]]) -> Any:
        client = fixtures.fake_claude(fixtures.claude_message({"groups": groups}))
        return group_by_cause(client, self.found)

    def test_unknown_and_repeated_items_are_dropped(self) -> None:
        grouping = self.group(
            [
                _group("Th", ["they", "the", "them", "they"], ["e→r", "x→y"]),
                _group("Repeats", ["they", "salt", "self"]),
            ]
        )
        self.assertEqual(
            [(g.words, g.confusions) for g in grouping.groups],
            [(("they", "the"), ("e→r",)), (("salt", "self"), ())],
        )
        self.assertEqual(grouping.ungrouped_words, ("sell",))
        self.assertEqual(grouping.ungrouped_confusions, ("t→r",))
        self.assertEqual(grouping.usage, USAGE)
        self.assertEqual(grouping.problems, self.found)

    def test_small_groups_are_dropped(self) -> None:
        grouping = self.group(
            [
                _group("Alone", ["they"]),
                _group("Only unknown", ["xyz", "abc"]),
                _group("Pair", ["they"], ["t→r"]),
            ]
        )
        self.assertEqual([g.name for g in grouping.groups], ["Pair"])

    def test_at_most_six_groups_are_kept(self) -> None:
        words = [f"w{n}" for n in range(14)]
        found = Problems(tuple(_word(word) for word in words), ())
        groups = [_group(f"G{n}", words[2 * n : 2 * n + 2]) for n in range(7)]
        client = fixtures.fake_claude(fixtures.claude_message({"groups": groups}))
        grouping = group_by_cause(client, found)
        self.assertEqual(
            [g.name for g in grouping.groups], ["G0", "G1", "G2", "G3", "G4", "G5"]
        )
        self.assertEqual(grouping.ungrouped_words, ("w12", "w13"))

    def test_no_groups(self) -> None:
        grouping = self.group([])
        self.assertEqual(grouping.groups, ())
        self.assertEqual(len(grouping.ungrouped_words), 5)


class TextCheckTest(unittest.TestCase):
    def test_whitespace_word_count_and_coverage(self) -> None:
        text = check_text(
            Problems(),
            ["they", "salt", "self"],
            "  they said\n\nthey,  salted\tthey're salt ",
            USAGE,
        )
        self.assertEqual(text.text, "they said they, salted they're salt")
        self.assertEqual(text.word_count, 6)
        # "they're" has "they" as a whole word; "salted" doesn't have "salt".
        self.assertEqual(text.coverage, (("they", 3), ("salt", 1), ("self", 0)))
        self.assertEqual(text.unused, ["self"])
        self.assertEqual(text.unusual, ())

    def test_characters_outside_printable_ascii(self) -> None:
        text = check_text(Problems(), [], "“salt” — they “sell”", USAGE)
        self.assertEqual(text.unusual, ("“", "”", "—"))

    def test_answer_after_a_fallback(self) -> None:
        client = fixtures.fake_claude(
            fixtures.claude_message({"text": "they sell salt"}, declined_first=True)
        )
        text = write_practice_text(client, _problems(fixtures.PROGRESS), 20)
        self.assertEqual(text.text, "they sell salt")


class ErrorTest(unittest.TestCase):
    def assert_message(self, reply: Any, message: str) -> None:
        client = fixtures.fake_claude(reply)
        with self.assertRaises(ClaudeError) as caught:
            write_practice_text(client, _problems(fixtures.PROGRESS), 50)
        self.assertEqual(str(caught.exception), message)

    def test_key_rejected(self) -> None:
        self.assert_message(
            fixtures.api_error(anthropic.AuthenticationError, 401), KEY_REJECTED
        )
        self.assert_message(
            fixtures.api_error(anthropic.PermissionDeniedError, 403), KEY_REJECTED
        )

    def test_rate_limit(self) -> None:
        self.assert_message(
            fixtures.api_error(anthropic.RateLimitError, 429, {"retry-after": "30"}),
            "Too many requests. Try again in 30 seconds.",
        )
        self.assert_message(
            fixtures.api_error(anthropic.RateLimitError, 429),
            "Too many requests. Try again in a minute.",
        )

    def test_busy(self) -> None:
        self.assert_message(fixtures.api_error(anthropic.OverloadedError, 529), BUSY)
        self.assert_message(
            fixtures.api_error(anthropic.InternalServerError, 500), BUSY
        )

    def test_no_connection(self) -> None:
        self.assert_message(fixtures.connection_error(), NO_CONNECTION)
        self.assert_message(fixtures.timeout_error(), NO_CONNECTION)

    def test_other_api_error(self) -> None:
        self.assert_message(
            fixtures.api_error(anthropic.BadRequestError, 400),
            "Claude returned an error: error from the test",
        )

    def test_refusal(self) -> None:
        self.assert_message(
            fixtures.claude_message("", stop_reason="refusal"), DECLINED
        )

    def test_cut_off(self) -> None:
        self.assert_message(
            fixtures.claude_message('{"text": "they se', stop_reason="max_tokens"),
            INCOMPLETE,
        )

    def test_answer_not_in_the_schema(self) -> None:
        self.assert_message(fixtures.claude_message("not json"), INCOMPLETE)
        self.assert_message(fixtures.claude_message({"words": "salt"}), INCOMPLETE)
        self.assert_message(fixtures.claude_message({"text": 3}), INCOMPLETE)
        client = fixtures.fake_claude(fixtures.claude_message({"groups": [{}]}))
        with self.assertRaises(ClaudeError):
            group_by_cause(client, _problems(fixtures.PROGRESS))


if __name__ == "__main__":
    unittest.main()
