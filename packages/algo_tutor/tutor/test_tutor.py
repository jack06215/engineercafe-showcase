import json
import unittest
from datetime import date

import httpx
import ollama

from packages.algo_tutor.config import TaskConfig
from packages.algo_tutor.domain.enums import (
    Difficulty,
    Help,
    HintLevel,
    HintRole,
    Language,
    Outcome,
    Source,
    TutorErrorKind,
)
from packages.algo_tutor.tutor import hints, language, report
from packages.algo_tutor.tutor.connection import check_connection
from packages.algo_tutor.tutor.fake_models import ScriptedChat
from packages.algo_tutor.tutor.llm import TutorError

TASK = TaskConfig(
    provider="ollama", model="qwen3.6:35b", temperature=0, reasoning=False, timeout_s=90
)
PROBLEM = report.ProblemInfo(
    title="Two Sum",
    url="https://leetcode.com/problems/two-sum/",
    source=Source.LEETCODE,
    difficulty=Difficulty.EASY,
)
REPORT = {
    "summary": "Solved with a hash map.",
    "strengths": "Clear names.",
    "improvements": "Check the empty input.",
    "complexity": "O(n) time, O(n) space; optimal.",
    "practice": "Another complement-lookup problem.",
}


def report_input(
    notes: str = "", check_of: report.CheckOf | None = None
) -> report.ReportInput:
    return report.ReportInput(
        problem=PROBLEM,
        attempt=report.AttemptInfo(
            code="def twoSum(self, nums, target): ...",
            notes=notes,
            language=Language.PYTHON,
            outcome=Outcome.SOLVED,
            help=Help.NONE,
            time="12:05",
            confidence=4,
        ),
        takeaway=None,
        history=tuple(
            report.EarlierAttempt(
                date(2026, 11, i),
                Outcome.NOT_SOLVED,
                Help.MAJOR,
                "30:00",
                2,
                Language.PYTHON,
                "n",
                "c" * 9000,
            )
            for i in range(1, 8)
        ),
        check_of=check_of,
    )


class LanguageTest(unittest.TestCase):
    def test_kana_means_japanese(self) -> None:
        self.assertEqual(language.detect("二分探索でいけそう"), "Japanese")
        self.assertEqual(language.detect("ハッシュマップ"), "Japanese")
        self.assertEqual(language.detect("ｶﾀｶﾅ"), "Japanese")

    def test_everything_else_is_english(self) -> None:
        self.assertEqual(language.detect(""), "English")
        self.assertEqual(
            language.detect("used a 二分 search"), "English"
        )  # kanji alone
        self.assertEqual(language.detect("two pointers"), "English")

    def test_hint_follows_the_message_then_the_notes(self) -> None:
        self.assertEqual(language.for_hint("why does this fail?", "メモ"), "English")
        self.assertEqual(language.for_hint("  ", "メモ"), "Japanese")
        self.assertEqual(language.for_report("plain", "学んだこと"), "Japanese")


class ReportTest(unittest.TestCase):
    def test_report_and_its_context(self) -> None:
        chat = ScriptedChat(script=[json.dumps(REPORT)])
        answer = report.generate(
            chat,
            TASK,
            report_input(check_of=report.CheckOf("Contains Duplicate", "transfer")),
        )
        self.assertEqual(answer.value.summary, "Solved with a hash map.")
        self.assertFalse(answer.repaired)
        system, user = chat.calls[0]
        self.assertIn("coding-interview tutor", system.text)
        self.assertNotIn("LeetCode tutor", system.text)
        self.assertNotIn("FAANG", system.text)
        self.assertIn("ListNode", system.text)
        self.assertTrue(system.text.endswith("Write every field in English."))
        sent = json.loads(user.text)
        self.assertEqual(len(sent["history"]), report.HISTORY_LIMIT)
        self.assertEqual(len(sent["history"][0]["code"]), report.HISTORY_CODE_CHARS)
        self.assertEqual(
            sent["check_of"], {"title": "Contains Duplicate", "kind": "transfer"}
        )
        self.assertNotIn("topic", json.dumps(sent))

    def test_japanese_notes_pin_japanese(self) -> None:
        chat = ScriptedChat(script=[json.dumps(REPORT)])
        report.generate(chat, TASK, report_input(notes="境界でミスした"))
        self.assertTrue(
            chat.calls[0][0].text.endswith("Write every field in Japanese.")
        )

    def test_one_repair_then_success(self) -> None:
        broken = dict(REPORT, complexity="")
        chat = ScriptedChat(
            script=[json.dumps(broken), "```json\n" + json.dumps(REPORT) + "\n```"]
        )
        answer = report.generate(chat, TASK, report_input())
        self.assertTrue(answer.repaired)
        repair = chat.calls[1]
        self.assertEqual(len(repair), 4)
        self.assertIn("complexity", repair[-1].text)
        self.assertEqual(
            report.from_column(report.to_column(answer.value)), answer.value
        )

    def test_invalid_after_repair(self) -> None:
        chat = ScriptedChat(script=["not json", "{}"])
        with self.assertRaises(TutorError) as caught:
            report.generate(chat, TASK, report_input())
        self.assertEqual(caught.exception.kind, TutorErrorKind.INVALID_OUTPUT)
        self.assertEqual(len(chat.calls), 2)

    def test_atcoder_prompt(self) -> None:
        atcoder = report.ProblemInfo(
            "Logs",
            "https://atcoder.jp/contests/abc174/tasks/abc174_e",
            Source.ATCODER,
            None,
        )
        chat = ScriptedChat(script=[json.dumps(REPORT)])
        report.generate(
            chat, TASK, report.ReportInput(atcoder, report_input().attempt, None)
        )
        self.assertIn("AtCoder", chat.calls[0][0].text)
        self.assertNotIn("ListNode", chat.calls[0][0].text)


class ErrorKindTest(unittest.TestCase):
    def kind_of(self, exc: Exception) -> TutorErrorKind:
        with self.assertRaises(TutorError) as caught:
            report.generate(ScriptedChat(script=[exc]), TASK, report_input())
        return caught.exception.kind

    def test_kinds(self) -> None:
        self.assertEqual(
            self.kind_of(ConnectionError("refused")), TutorErrorKind.UNAVAILABLE
        )
        self.assertEqual(
            self.kind_of(httpx.ConnectError("refused")), TutorErrorKind.UNAVAILABLE
        )
        self.assertEqual(
            self.kind_of(httpx.ReadTimeout("slow")), TutorErrorKind.TIMEOUT
        )
        self.assertEqual(
            self.kind_of(ollama.ResponseError("model 'qwen3.6:35b' not found", 404)),
            TutorErrorKind.MODEL_MISSING,
        )
        self.assertEqual(self.kind_of(ValueError("boom")), TutorErrorKind.ERROR)

    def test_connection_check(self) -> None:
        good = check_connection(ScriptedChat(script=['{"ok": "yes"}']), TASK)
        self.assertTrue(good.ok)
        self.assertIsNotNone(good.latency_ms)
        bad = check_connection(ScriptedChat(script=[ConnectionError("refused")]), TASK)
        self.assertEqual((bad.ok, bad.error_kind), (False, TutorErrorKind.UNAVAILABLE))


class HintTest(unittest.TestCase):
    def hint_input(
        self, history: tuple[hints.Message, ...] = (), stuck: int = 300
    ) -> hints.HintInput:
        return hints.HintInput(
            problem=PROBLEM,
            language=Language.PYTHON,
            code="x" * 25_000,
            notes="",
            stuck_at_seconds=stuck,
            history=history,
            message="I'm stuck on duplicates",
        )

    def test_first_hint_is_a_new_stuck_point(self) -> None:
        reply = {
            "reply": "What if the same number appears twice?",
            "hint": "Consider duplicates.",
            "level": "Small",
            "analysis": "Nested loops; stuck on duplicates.",
        }
        chat = ScriptedChat(script=[json.dumps(reply)])
        answer = hints.generate(chat, TASK, self.hint_input())
        self.assertEqual(answer.value.hint_level, HintLevel.SMALL)
        sent = json.loads(chat.calls[0][1].text)
        self.assertEqual((sent["stuck_at"], sent["new_stuck"]), ("05:00", True))
        self.assertEqual(len(sent["code"]), hints.CODE_CHARS)
        self.assertNotIn("topic", sent["problem"])
        block = hints.notes_block(answer.value, 300, True)
        self.assertEqual(
            block,
            "[Stuck at 05:00] Asked Algo-chan for help.\n"
            "Where I was: Nested loops; stuck on duplicates.\n"
            "Hint (small): Consider duplicates.",
        )
        self.assertEqual(
            hints.append_to_notes("my approach", block, True), f"my approach\n\n{block}"
        )

    def test_follow_up_drops_the_analysis(self) -> None:
        history = (
            hints.Message(HintRole.LEARNER, "help", 240),
            hints.Message(HintRole.TUTOR, "What about duplicates?"),
        )
        reply = {
            "reply": "Use a map from value to index.",
            "hint": "Map value to index.",
            "level": "major",
            "analysis": "leaked",
        }
        answer = hints.generate(
            ScriptedChat(script=[json.dumps(reply)]),
            TASK,
            self.hint_input(history, stuck=300),
        )
        self.assertIsNone(answer.value.analysis)
        self.assertEqual(
            hints.notes_block(answer.value, 300, False),
            "Hint (major): Map value to index.",
        )
        self.assertTrue(
            hints.is_new_stuck(history, 240 + hints.NEW_STUCK_AFTER_SECONDS)
        )

    def test_bad_level_goes_to_repair(self) -> None:
        bad = {"reply": "r", "hint": "h", "level": "medium"}
        good = {"reply": "r", "hint": "h", "level": "small", "analysis": None}
        chat = ScriptedChat(script=[json.dumps(bad), json.dumps(good)])
        self.assertTrue(hints.generate(chat, TASK, self.hint_input()).repaired)

    def test_strongest(self) -> None:
        self.assertIsNone(hints.strongest([None]))
        self.assertEqual(hints.strongest([HintLevel.SMALL, None]), HintLevel.SMALL)
        self.assertEqual(
            hints.strongest([HintLevel.SMALL, HintLevel.MAJOR]), HintLevel.MAJOR
        )


if __name__ == "__main__":
    unittest.main()
