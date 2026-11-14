import unittest
from datetime import timedelta

from packages.algo_tutor.api.testing import (
    NOW,
    PATTERN_README,
    insert_attempt,
    insert_problem,
    make_harness,
)

PATTERN = "01_sliding_window"
README = (
    "packages/programming_exercise/common_coding_pattern/01_sliding_window/README.md"
)


class PatternTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_list(self) -> None:
        self.assertEqual(
            self.h.get("/patterns").json(),
            [
                {
                    "id": PATTERN,
                    "name": "Sliding Window",
                    "position": 1,
                    "missing": False,
                    "problems": 0,
                }
            ],
        )

    def test_readme_is_read_live(self) -> None:
        page = self.h.get(f"/patterns/{PATTERN}").json()
        self.assertEqual(
            (page["readme_path"], page["readme_markdown"]), (README, PATTERN_README)
        )
        path = self.h.repo_root / README
        path.write_text("# Sliding Window\n\nEdited.\n")
        self.assertIn(
            "Edited.", self.h.get(f"/patterns/{PATTERN}").json()["readme_markdown"]
        )
        path.unlink()
        self.assertIsNone(self.h.get(f"/patterns/{PATTERN}").json()["readme_markdown"])
        self.assertEqual(self.h.get("/patterns/99_nope").status_code, 404)

    def test_notebook_versions(self) -> None:
        saved = self.h.patch(
            f"/patterns/{PATTERN}/notebook",
            {"version": 1, "cues": "contiguous", "notes": "n"},
        ).json()
        self.assertEqual(
            (saved["cues"], saved["pitfalls"], saved["notes"], saved["version"]),
            ("contiguous", "", "n", 2),
        )
        self.assertEqual(saved["updated_at"], "2026-11-08T09:00:00Z")
        stale = self.h.patch(
            f"/patterns/{PATTERN}/notebook", {"version": 1, "pitfalls": "x"}
        )
        self.assertEqual(
            (stale.status_code, stale.json()["error"]["code"]), (409, "STALE")
        )
        self.assertEqual(
            self.h.get(f"/patterns/{PATTERN}").json()["notebook"]["version"], 2
        )

    def test_only_attempted_problems_are_listed(self) -> None:
        seen = insert_problem(self.h, "max-sum", "Maximum Sum")
        unseen = insert_problem(self.h, "fruit-baskets", "Fruit Into Baskets")
        for pid in (seen, unseen):
            self.h.patch(f"/problems/{pid}", {"patterns": [PATTERN]})
        insert_attempt(self.h, seen, outcome="not_solved")
        page = self.h.get(f"/patterns/{PATTERN}").json()
        self.assertEqual(
            [
                (p["problem"]["title"], p["attempts"], p["latest_outcome"])
                for p in page["problems"]
            ],
            [("Maximum Sum", 1, "not_solved")],
        )
        self.assertEqual(page["pattern"]["problems"], 1)


class MistakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)
        h = self.h
        a = insert_problem(h, "two-sum", "Two Sum")
        b = insert_problem(h, "lru-cache", "LRU Cache")
        insert_attempt(
            h, a, labels=("missed_edge_case",), finished=NOW - timedelta(days=2)
        )
        insert_attempt(
            h,
            b,
            takeaway="Evict from the tail, not the head.",
            finished=NOW - timedelta(days=1),
        )
        insert_attempt(
            h,
            b,
            labels=("wrong_approach", "implementation_bug"),
            takeaway="Use a dict + linked list.",
            finished=NOW,
        )
        insert_attempt(h, a, finished=NOW)  # no lesson: left out
        insert_attempt(
            h, a, status="active", labels=("wrong_approach",)
        )  # unfinished: left out

    def titles(self, query: str = "") -> list[tuple[str, str]]:
        items = self.h.get(f"/mistakes{query}").json()["items"]
        return [(i["problem"]["title"], i["takeaway"]) for i in items]

    def test_newest_first(self) -> None:
        self.assertEqual(
            self.titles(),
            [
                ("LRU Cache", "Use a dict + linked list."),
                ("LRU Cache", "Evict from the tail, not the head."),
                ("Two Sum", ""),
            ],
        )

    def test_search_and_filter(self) -> None:
        self.assertEqual(self.titles("?q=edge%20case"), [("Two Sum", "")])
        self.assertEqual(
            self.titles("?q=TAIL"),
            [("LRU Cache", "Evict from the tail, not the head.")],
        )
        self.assertEqual(self.titles("?q=two%20sum"), [("Two Sum", "")])
        self.assertEqual(
            self.titles("?label=implementation_bug"),
            [("LRU Cache", "Use a dict + linked list.")],
        )
        self.assertEqual(self.h.get("/mistakes?label=typo").status_code, 422)


class HiddenAssessmentTest(unittest.TestCase):
    def test_locked(self) -> None:
        h = make_harness()
        self.addCleanup(h.close)
        pid = insert_problem(h, "two-sum", "Two Sum")
        insert_attempt(h, pid, labels=("missed_edge_case",))
        insert_attempt(h, pid, status="active", context="mixed")
        for response in (
            h.get("/patterns"),
            h.get(f"/patterns/{PATTERN}"),
            h.patch(f"/patterns/{PATTERN}/notebook", {"version": 1, "notes": "x"}),
            h.get("/mistakes"),
        ):
            with self.subTest(url=str(response.url)):
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (403, "HIDDEN_ASSESSMENT"),
                )


if __name__ == "__main__":
    unittest.main()
