import unittest
from datetime import timedelta

from packages.algo_tutor.api.testing import (
    NOW,
    insert_attempt,
    insert_problem,
    install_fake_bank,
    make_harness,
)
from packages.algo_tutor.store.models import Problem

HASH_TABLES = (
    "packages/programming_exercise/leetcode/src/01_data_structures/hash_tables"
)


class AddProblemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_add_leetcode_by_url_once(self) -> None:
        first = self.h.post(
            "/problems", {"url": "https://leetcode.com/problems/two-sum/description/"}
        )
        self.assertEqual(first.status_code, 201, first.text)
        body = first.json()
        self.assertEqual(
            (body["problem"]["title"], body["problem"]["number"]), ("Two Sum", 1)
        )
        self.assertEqual(
            body["problem"]["url"], "https://leetcode.com/problems/two-sum/"
        )
        again = self.h.post(
            "/problems", {"url": "https://leetcode.com/problems/two-sum"}
        )
        self.assertEqual(
            (again.status_code, again.json()["problem"]["id"]),
            (200, body["problem"]["id"]),
        )

    def test_atcoder_needs_a_title(self) -> None:
        url = "https://atcoder.jp/contests/abc174/tasks/abc174_e"
        missing = self.h.post("/problems", {"url": url})
        self.assertEqual(missing.status_code, 422, missing.text)
        added = self.h.post("/problems", {"url": url, "title": "Logs"}).json()
        self.assertEqual(
            (added["problem"]["source"], added["problem"]["contest"]),
            ("atcoder", "abc174"),
        )
        self.assertIsNone(added["problem"]["rating"])
        self.assertIsNone(added["topic_id"])

    def test_bad_url(self) -> None:
        response = self.h.post("/problems", {"url": "https://example.com/two-sum"})
        self.assertEqual(
            (response.status_code, response.json()["error"]["code"]),
            (422, "VALIDATION"),
        )


class LibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)
        h = self.h
        # Two Sum has an exact zerotrac rating? No: it's not a contest problem,
        # so its rating is the Easy median (≈1252).
        self.two_sum = insert_problem(
            h,
            "two-sum",
            "Two Sum",
            tags=("Array", "Hash Table"),
            topic_id="hash-table",
            number=1,
        )
        self.lru = insert_problem(
            h,
            "lru-cache",
            "LRU Cache",
            difficulty="Medium",
            tags=("Design",),
            topic_id="design",
        )
        self.trap = insert_problem(
            h,
            "trapping-rain-water",
            "Trapping Rain Water",
            difficulty="Hard",
            tags=("Stack",),
            topic_id="stack",
        )
        self.logs = insert_problem(
            h, "abc174_e", "Logs", source="atcoder", difficulty=None, contest="abc174"
        )
        insert_attempt(
            h,
            self.two_sum,
            outcome="solved",
            active_seconds=5 * 60,
            confidence=5,
            finished=NOW - timedelta(days=2),
        )
        insert_attempt(
            h,
            self.lru,
            outcome="not_solved",
            active_seconds=35 * 60,
            confidence=2,
            finished=NOW - timedelta(days=1),
        )
        insert_attempt(
            h,
            self.two_sum,
            outcome="stopped",
            active_seconds=12 * 60,
            confidence=3,
            finished=NOW,
        )

    def titles(self, query: str) -> list[str]:
        response = self.h.get(f"/problems?{query}")
        self.assertEqual(response.status_code, 200, response.text)
        return [row["problem"]["title"] for row in response.json()["items"]]

    def test_filters(self) -> None:
        self.assertEqual(self.titles("source=atcoder"), ["Logs"])
        self.assertEqual(self.titles("difficulty=Medium"), ["LRU Cache"])
        self.assertEqual(self.titles("topic=stack"), ["Trapping Rain Water"])
        self.assertEqual(self.titles("topic=none"), ["Logs"])
        self.assertEqual(self.titles("tag=Hash%20Table"), ["Two Sum"])
        self.assertEqual(self.titles("q=RAIN"), ["Trapping Rain Water"])
        self.assertEqual(self.titles("q=lru-cache"), ["LRU Cache"])  # URL substring
        self.assertEqual(
            self.titles("latest=stopped"), ["Two Sum"]
        )  # the newest attempt counts
        self.assertEqual(
            self.titles("latest=not_submitted"), ["Logs", "Trapping Rain Water"]
        )
        self.assertEqual(self.titles("time=10-20"), ["Two Sum"])
        self.assertEqual(self.titles("time=30-45"), ["LRU Cache"])
        self.assertEqual(self.titles("confidence=low"), ["LRU Cache"])
        self.assertEqual(self.titles("confidence=medium"), ["Two Sum"])

    def test_rows(self) -> None:
        row = next(
            r
            for r in self.h.get("/problems").json()["items"]
            if r["problem"]["title"] == "Two Sum"
        )
        self.assertEqual(row["problem"]["rating"], {"value": 1252, "estimated": True})
        self.assertEqual(
            (
                row["latest_outcome"],
                row["latest_active_seconds"],
                row["latest_confidence"],
            ),
            ("stopped", 720, 3),
        )
        self.assertEqual(row["topic_id"], "hash-table")

    def test_sorting_puts_missing_values_last(self) -> None:
        self.assertEqual(
            self.titles("sort=rating&order=desc"),
            ["Trapping Rain Water", "LRU Cache", "Two Sum", "Logs"],
        )
        self.assertEqual(
            self.titles("sort=rating"),
            ["Two Sum", "LRU Cache", "Trapping Rain Water", "Logs"],
        )
        self.assertEqual(
            self.titles("sort=difficulty&order=desc"),
            ["Trapping Rain Water", "LRU Cache", "Two Sum", "Logs"],
        )
        self.assertEqual(
            self.titles("sort=latest&order=desc")[:2], ["Two Sum", "LRU Cache"]
        )
        self.assertEqual(
            self.titles("sort=time"),
            ["Two Sum", "LRU Cache", "Logs", "Trapping Rain Water"],
        )

    def test_paging(self) -> None:
        page = self.h.get("/problems?page_size=3&page=2").json()
        self.assertEqual((page["total"], page["page"], page["page_size"]), (4, 2, 3))
        self.assertEqual([r["problem"]["title"] for r in page["items"]], ["Two Sum"])
        too_big = self.h.get("/problems?page_size=101")
        self.assertEqual(too_big.status_code, 422)
        unknown = self.h.get("/problems?colour=red")
        self.assertEqual(unknown.status_code, 422)


class ProblemPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)
        self.id = insert_problem(
            self.h,
            "two-sum",
            "Two Sum",
            tags=("Array", "Hash Table"),
            topic_id="hash-table",
            number=1,
        )

    def exposed(self) -> bool:
        with self.h.session() as session:
            return session.get_one(Problem, self.id).exposed

    def test_viewing_exposes(self) -> None:
        self.assertFalse(self.exposed())
        page = self.h.get(f"/problems/{self.id}").json()
        self.assertEqual(
            (
                page["external_id"],
                page["source_tags"],
                page["attempts"],
                page["review"],
            ),
            ("two-sum", ["Array", "Hash Table"], [], None),
        )
        self.assertTrue(self.exposed())
        self.assertEqual(self.h.get("/problems/nope").status_code, 404)

    def test_topic_override_and_reset(self) -> None:
        graph = self.h.patch(
            f"/problems/{self.id}", {"topic_id": "graph", "notes": "hmm"}
        ).json()
        self.assertEqual(
            (graph["topic_id"], graph["topic_overridden"], graph["notes"]),
            ("graph", True, "hmm"),
        )
        none = self.h.patch(f"/problems/{self.id}", {"topic_id": None}).json()
        self.assertEqual((none["topic_id"], none["topic_overridden"]), (None, True))
        reset = self.h.patch(f"/problems/{self.id}", {"reset_topic": True}).json()
        self.assertEqual(
            (reset["topic_id"], reset["topic_overridden"]), ("hash-table", False)
        )
        bad = self.h.patch(f"/problems/{self.id}", {"topic_id": "quantum"})
        self.assertEqual(bad.status_code, 422)
        both = self.h.patch(
            f"/problems/{self.id}", {"topic_id": "graph", "reset_topic": True}
        )
        self.assertEqual(both.status_code, 422)

    def test_patterns(self) -> None:
        tagged = self.h.patch(
            f"/problems/{self.id}", {"patterns": ["01_sliding_window"]}
        ).json()
        self.assertEqual(tagged["patterns"], ["01_sliding_window"])
        self.assertEqual(
            self.h.patch(f"/problems/{self.id}", {"patterns": []}).json()["patterns"],
            [],
        )
        self.assertEqual(
            self.h.patch(f"/problems/{self.id}", {"patterns": ["99_nope"]}).status_code,
            422,
        )

    def test_override_survives_a_bank_refresh(self) -> None:
        self.h.patch(f"/problems/{self.id}", {"topic_id": "graph"})
        service = install_fake_bank(self.h)
        self.h.post("/bank/refresh")
        service.join(30)
        self.assertEqual(self.h.get("/bank").json()["status"], "done")
        page = self.h.get(f"/problems/{self.id}").json()
        self.assertEqual((page["topic_id"], page["topic_overridden"]), ("graph", True))


class SuggestedPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness(
            repo_files={
                f"{HASH_TABLES}/0001_two_sum_easy.py": "",
                "packages/programming_exercise/leetcode/src/.claude/0001_two_sum_easy.py": "",
            }
        )
        self.addCleanup(self.h.close)
        self.two_sum = insert_problem(
            self.h, "two-sum", "Two Sum", topic_id="hash-table", number=1
        )

    def test_existing_file_then_new_path(self) -> None:
        found = self.h.get(
            f"/problems/{self.two_sum}/suggested-path?language=python"
        ).json()
        self.assertEqual(
            found, {"path": f"{HASH_TABLES}/0001_two_sum_easy.py", "exists": True}
        )
        fresh = self.h.get(
            f"/problems/{self.two_sum}/suggested-path?language=go"
        ).json()
        self.assertEqual(
            fresh, {"path": f"{HASH_TABLES}/0001_two_sum_easy.go", "exists": False}
        )

    def test_atcoder(self) -> None:
        logs = insert_problem(
            self.h,
            "abc174_e",
            "Logs",
            source="atcoder",
            difficulty=None,
            contest="abc174",
        )
        path = self.h.get(f"/problems/{logs}/suggested-path").json()
        self.assertEqual(
            path,
            {
                "path": "packages/programming_exercise/atcoder/src/abc174/e_logs.py",
                "exists": False,
            },
        )


class HiddenAssessmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)
        self.check = insert_problem(
            self.h, "two-sum", "Two Sum", topic_id="hash-table", number=1
        )
        self.other = insert_problem(self.h, "lru-cache", "LRU Cache", topic_id="design")
        insert_attempt(self.h, self.check, status="active", context="mixed")

    def test_library_and_pages_are_locked(self) -> None:
        for response in (
            self.h.get("/problems"),
            self.h.get(f"/problems/{self.other}"),
            self.h.get(f"/problems/{self.check}"),
            self.h.patch(f"/problems/{self.other}", {"notes": "x"}),
            self.h.post(
                "/problems", {"url": "https://leetcode.com/problems/valid-anagram/"}
            ),
            self.h.get(f"/problems/{self.other}/suggested-path"),
        ):
            with self.subTest(url=str(response.url)):
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (403, "HIDDEN_ASSESSMENT"),
                )

    def test_the_assessment_problem_still_gets_a_path(self) -> None:
        response = self.h.get(f"/problems/{self.check}/suggested-path")
        self.assertEqual(response.status_code, 200, response.text)

    def test_a_targeted_attempt_locks_nothing(self) -> None:
        h = make_harness()
        self.addCleanup(h.close)
        pid = insert_problem(h, "two-sum", "Two Sum")
        insert_attempt(h, pid, status="active", context="targeted")
        self.assertEqual(h.get("/problems").status_code, 200)


if __name__ == "__main__":
    unittest.main()
