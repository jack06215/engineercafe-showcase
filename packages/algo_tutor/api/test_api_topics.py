import unittest

from packages.algo_tutor.api.testing import (
    Harness,
    finish_body,
    make_harness,
    seed_problem,
)


class TopicsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h: Harness = make_harness()
        self.addCleanup(self.h.close)
        self.solved = seed_problem(self.h, "Two Sum", topic="hash-table", rating=1300)
        self.unseen = seed_problem(
            self.h, "Group Anagrams", topic="hash-table", rating=1400
        )

    def solve(self, problem_id: str, **finish: object) -> None:
        attempt = self.h.post("/attempts", {"problem_id": problem_id}).json()
        done = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(1, **finish),
            headers={"Idempotency-Key": attempt["id"]},
        )
        self.assertEqual(done.status_code, 200, done.text)

    def test_levels_in_curriculum_order(self) -> None:
        before = self.h.get("/topics").json()
        self.assertEqual(before["target_rating"], 1850)
        self.assertEqual(len(before["topics"]), 34)
        self.assertEqual(
            [t["name"] for t in before["topics"][:3]], ["Array", "String", "Hash Table"]
        )
        self.assertEqual({t["level"] for t in before["topics"]}, {1300})
        # Strong at 1300 from 1300: expected 0.5, so +16.
        self.solve(self.solved)
        hash_table = next(
            t for t in self.h.get("/topics").json()["topics"] if t["id"] == "hash-table"
        )
        self.assertEqual(
            (hash_table["level"], hash_table["attempts"], hash_table["at_target"]),
            (1316, 1, False),
        )
        self.assertEqual(
            hash_table["last_change"],
            {
                "delta": 16,
                "attempt_id": hash_table["last_change"]["attempt_id"],
                "problem_title": "Two Sum",
                "rating": 1300,
                "estimated": True,
                "result": "strong",
                "study_date": "2026-11-08",
            },
        )

    def test_topic_page_lists_attempted_problems_only(self) -> None:
        self.solve(self.solved, help="small")
        page = self.h.get("/topics/hash-table").json()
        self.assertEqual(
            [row["problem"]["title"] for row in page["problems"]], ["Two Sum"]
        )
        self.assertEqual(
            (page["unseen_count"], page["problems"][0]["latest_outcome"]), (1, "solved")
        )
        self.assertEqual(page["level"]["level"], 1300)  # OK: 0.5 − 0.5
        self.assertEqual(self.h.get("/topics/nope").status_code, 404)

    def test_notebook_is_versioned(self) -> None:
        saved = self.h.patch(
            "/topics/hash-table/notebook", {"version": 1, "cues": "Lookups by value"}
        ).json()
        self.assertEqual(
            (saved["cues"], saved["pitfalls"], saved["version"]),
            ("Lookups by value", "", 2),
        )
        self.assertIsNotNone(saved["updated_at"])
        stale = self.h.patch(
            "/topics/hash-table/notebook", {"version": 1, "notes": "lost"}
        )
        self.assertEqual(
            (stale.status_code, stale.json()["error"]["code"]), (409, "STALE")
        )
        self.assertEqual(
            self.h.get("/topics/hash-table").json()["notebook"]["cues"],
            "Lookups by value",
        )


if __name__ == "__main__":
    unittest.main()
