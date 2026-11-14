import unittest
from typing import Any

from packages.algo_tutor.api.testing import insert_attempt, make_harness

PASTE = "\n".join(
    [
        "1. https://leetcode.com/problems/two-sum/",
        "2. contains-duplicate",
        "https://atcoder.jp/contests/abc174/tasks/abc174_e Logs",
        "not a thing",
    ]
)

PACK: dict[str, Any] = {
    "version": 2,
    "name": "Tessoku book, chapter 1",
    "source": "atcoder",
    "questions": [
        {
            "url": "https://atcoder.jp/contests/tessoku-book/tasks/tessoku_book_a",
            "title": "The First Problem",
        },
        {
            "url": "https://atcoder.jp/contests/tessoku-book/tasks/tessoku_book_b",
            "title": "The Second Problem",
        },
    ],
}


class OwnListTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_preview_splits_a_mixed_paste(self) -> None:
        preview = self.h.post("/lists/preview", {"name": "Mine", "text": PASTE}).json()
        groups = [
            (g["source"], g["name"], [e["title"] for e in g["entries"]])
            for g in preview["groups"]
        ]
        self.assertEqual(
            groups,
            [
                ("leetcode", "Mine (LeetCode)", ["Two Sum", "Contains Duplicate"]),
                ("atcoder", "Mine (AtCoder)", ["Logs"]),
            ],
        )
        self.assertEqual(preview["unresolved"], ["not a thing"])
        self.assertEqual(preview["unresolved_reasons"][0]["line"], "not a thing")
        self.assertEqual(self.h.get("/lists").json(), [])  # nothing written

    def test_create_edit_activate_delete(self) -> None:
        created = self.h.post("/lists", {"name": "Mine", "text": PASTE})
        self.assertEqual(created.status_code, 201, created.text)
        lists = {x["source"]: x for x in created.json()["lists"]}
        self.assertEqual(
            (
                lists["leetcode"]["name"],
                lists["leetcode"]["total"],
                lists["leetcode"]["kind"],
            ),
            ("Mine (LeetCode)", 2, "own"),
        )
        leetcode = lists["leetcode"]["id"]

        detail = self.h.get(f"/lists/{leetcode}").json()
        ids = [e["problem"]["id"] for e in detail["entries"]]
        self.assertEqual(
            [e["problem"]["title"] for e in detail["entries"]],
            ["Two Sum", "Contains Duplicate"],
        )

        edited = self.h.patch(
            f"/lists/{leetcode}",
            {
                "name": "Warm-up",
                "problem_ids": ids[::-1],
                "add_text": "valid-anagram\nhttps://atcoder.jp/contests/abc174/tasks/abc174_d",
            },
        ).json()
        self.assertEqual(edited["summary"]["name"], "Warm-up")
        self.assertEqual(
            [e["problem"]["title"] for e in edited["entries"]],
            ["Contains Duplicate", "Two Sum", "Valid Anagram"],
        )
        self.assertEqual(
            len(edited["unresolved"]), 1
        )  # the AtCoder task can't join a LeetCode list

        active = self.h.post(f"/lists/{leetcode}/activate").json()
        self.assertTrue(active["active"])
        self.assertEqual(
            self.h.get("/settings").json()["active_list_leetcode"], leetcode
        )
        self.assertFalse(self.h.post(f"/lists/{leetcode}/deactivate").json()["active"])
        self.assertIsNone(self.h.get("/settings").json()["active_list_leetcode"])

        self.assertEqual(self.h.delete(f"/lists/{leetcode}").status_code, 204)
        self.assertEqual(self.h.get(f"/lists/{leetcode}").status_code, 404)

    def test_progress_counts_attempts_started_after_adding(self) -> None:
        created = self.h.post(
            "/lists", {"name": "Mine", "text": "two-sum\ncontains-duplicate"}
        ).json()
        list_id = created["lists"][0]["id"]
        entry = self.h.get(f"/lists/{list_id}").json()["entries"][0]
        self.h.clock.now = self.h.clock.now.replace(hour=10)
        insert_attempt(self.h, entry["problem"]["id"], finished=self.h.clock.now)
        detail = self.h.get(f"/lists/{list_id}").json()
        self.assertEqual([e["done"] for e in detail["entries"]], [True, False])
        self.assertEqual(
            (detail["summary"]["done"], detail["summary"]["total"]), (1, 2)
        )

    def test_nothing_resolves(self) -> None:
        response = self.h.post("/lists", {"name": "Empty", "text": "nope nope"})
        self.assertEqual(
            (response.status_code, response.json()["error"]["code"]),
            (422, "VALIDATION"),
        )


class CourseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_follow_once_read_only(self) -> None:
        first = self.h.post("/lists/bundled/hello-interview")
        self.assertEqual(first.status_code, 201, first.text)
        body = first.json()
        self.assertEqual(
            (
                body["summary"]["name"],
                body["summary"]["kind"],
                body["summary"]["total"],
            ),
            ("Hello Interview", "bundled", 88),
        )
        self.assertEqual(body["entries"][0]["section"], "Sliding Window")
        again = self.h.post("/lists/bundled/hello-interview")
        self.assertEqual(
            (again.status_code, again.json()["summary"]["id"]),
            (200, body["summary"]["id"]),
        )
        locked = self.h.patch(f"/lists/{body['summary']['id']}", {"name": "Mine"})
        self.assertEqual(
            (locked.status_code, locked.json()["error"]["code"]), (409, "CONFLICT")
        )
        self.assertEqual(self.h.post("/lists/bundled/grind-169").status_code, 422)


class PackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def post_pack(self, body: Any, key: str, dry_run: bool = False) -> Any:
        query = "?dry_run=true" if dry_run else ""
        return self.h.post(f"/packs{query}", body, headers={"Idempotency-Key": key})

    def test_dry_run_apply_replay_and_repeat(self) -> None:
        dry = self.post_pack(PACK, "k1", dry_run=True)
        self.assertEqual(dry.status_code, 200, dry.text)
        self.assertEqual(
            (
                dry.json()["dry_run"],
                dry.json()["problems_created"],
                dry.json()["summary"],
            ),
            (True, 2, None),
        )
        self.assertEqual(self.h.get("/lists").json(), [])

        applied = self.post_pack(PACK, "k2")
        report = applied.json()
        self.assertEqual(
            (report["dry_run"], report["already_applied"], report["entries_added"]),
            (False, False, 2),
        )
        self.assertEqual(report["lists_created"], ["Tessoku book, chapter 1"])
        self.assertEqual(
            (report["summary"]["kind"], report["summary"]["source"]),
            ("pack", "atcoder"),
        )

        replay = self.post_pack(PACK, "k2")
        self.assertEqual(replay.json(), report)
        mismatch = self.post_pack(PACK | {"name": "Other"}, "k2")
        self.assertEqual(
            (mismatch.status_code, mismatch.json()["error"]["code"]),
            (409, "IDEMPOTENCY_MISMATCH"),
        )

        repeat = self.post_pack(PACK, "k3").json()
        self.assertTrue(repeat["already_applied"])
        self.assertEqual(len(self.h.get("/lists").json()), 1)

    def test_validation(self) -> None:
        bad = self.post_pack(PACK | {"version": 1}, "k4")
        self.assertEqual(
            (bad.status_code, bad.json()["error"]["code"]), (422, "VALIDATION")
        )
        unknown = self.post_pack(PACK | {"extra": True}, "k5")
        self.assertEqual(unknown.status_code, 422)
        no_key = self.h.post("/packs", PACK)
        self.assertEqual(
            (no_key.status_code, no_key.json()["error"]["code"]), (422, "VALIDATION")
        )


class HiddenAssessmentTest(unittest.TestCase):
    def test_list_leaves_out_the_assessment_problem(self) -> None:
        h = make_harness()
        self.addCleanup(h.close)
        body = h.post("/lists/bundled/blind-75").json()
        check = body["entries"][0]["problem"]["id"]
        insert_attempt(h, check, status="active", context="mixed")
        entries = h.get(f"/lists/{body['summary']['id']}").json()["entries"]
        self.assertEqual(len(entries), 74)
        self.assertNotIn(check, [e["problem"]["id"] for e in entries])


if __name__ == "__main__":
    unittest.main()
