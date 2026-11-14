"""One learner's first days, through every layer at once: setup with the
bank and a course, the plan, a linked-file attempt with a hint, the report,
the reflection, and three days later the hidden transfer check.

The route modules have their own tests; this one checks that they agree
with each other (catalogue → plan → attempt → review → plan again).
"""

import json
import unittest
from datetime import timedelta
from typing import Any

from packages.algo_tutor.api.testing import (
    NOW,
    finish_body,
    install_fake_bank,
    make_harness,
    seed_problem,
)
from packages.algo_tutor.tutor.worker import ReportWorker

SOLUTION = "packages/programming_exercise/leetcode/src/01_data_structures/hash_tables/0217_contains_duplicate_easy.py"
CODE = "class Solution:\n    def containsDuplicate(self, nums):\n        return len(set(nums)) < len(nums)\n"
TRANSFER = "Transfer check — spot the approach yourself"
REPORT = {
    "summary": "Solved with a set.",
    "strengths": "Short and clear.",
    "improvements": "Say the complexity out loud.",
    "complexity": "O(n) time and space.",
    "practice": "Another hashing problem.",
}
HINT = {
    "reply": "What could remember what you've seen?",
    "hint": "Remember seen values.",
    "level": "small",
    "analysis": "Nested loops; too slow.",
}


def items_of(plan: dict[str, Any], lane: str = "leetcode") -> list[dict[str, Any]]:
    return sorted(
        (i for i in plan["items"] if i["lane"] == lane), key=lambda i: i["position"]
    )


class JourneyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness(repo_files={SOLUTION: CODE})
        self.addCleanup(self.h.close)

    def ok(self, response: Any) -> Any:
        self.assertLess(response.status_code, 300, response.text)
        return response.json() if response.content else None

    def test_first_days(self) -> None:
        h = self.h

        # Setup: the bank (recorded pages) and NeetCode 150.
        self.assertFalse(self.ok(h.get("/setup"))["onboarding_complete"])
        bank = install_fake_bank(h)
        self.ok(
            h.post(
                "/setup",
                {
                    "questions_per_day": 2,
                    "download_bank": True,
                    "follow": "neetcode-150",
                },
            )
        )
        bank.join(30)
        self.assertEqual(self.ok(h.get("/bank"))["status"], "done")
        lists = self.ok(h.get("/lists"))
        course = next(entry for entry in lists if entry["name"] == "NeetCode 150")
        if not course["active"]:
            self.ok(h.post(f"/lists/{course['id']}/activate"))
        # An unseen problem in the same topic, so the check below has a sibling.
        seed_problem(
            h,
            "Sibling Hash",
            topic="hash-table",
            label="Easy",
            rating=1260,
            popularity=99,
        )

        # Day 1: the plan follows the course.
        plan = self.ok(h.post("/plans/today/ensure"))
        first, second = items_of(plan)[:2]
        self.assertEqual(
            (first["reason"], first["kind"], first["status"]),
            ("From your study list", "list", "active"),
        )
        self.assertEqual(first["problem"]["title"], "Contains Duplicate")
        self.assertEqual(second["status"], "queued")
        problem_id = first["problem"]["id"]
        self.assertEqual(self.ok(h.get("/desk"))["total_today"], 2)

        path = self.ok(
            h.get(
                f"/problems/{problem_id}/suggested-path", params={"language": "python"}
            )
        )
        self.assertEqual(path, {"path": SOLUTION, "exists": True})

        attempt = self.ok(
            h.post(
                "/attempts",
                {
                    "problem_id": problem_id,
                    "plan_item_id": first["id"],
                    "language": "python",
                },
            )
        )
        self.assertEqual(
            (attempt["context"], attempt["evidence"]), ("targeted", "near_transfer")
        )
        attempt = self.ok(
            h.patch(
                f"/attempts/{attempt['id']}/draft",
                {"version": attempt["version"], "solution_path": SOLUTION},
            )
        )
        self.assertEqual(attempt["code"], CODE)

        h.clock.now = NOW + timedelta(seconds=60)
        attempt = self.ok(
            h.post(
                f"/attempts/{attempt['id']}/timer",
                {"version": attempt["version"], "action": "heartbeat"},
            )
        )
        self.assertEqual(attempt["active_seconds"], 60)

        h.script.append(json.dumps(HINT))
        reply = self.ok(
            h.post(f"/attempts/{attempt['id']}/hints", {"text": "Too slow, any idea?"})
        )
        self.assertIn("[Stuck at 01:00] Asked Algo-chan for help.", reply["notes"])
        self.assertEqual(reply["strongest_level"], "small")
        attempt = self.ok(h.get(f"/attempts/{attempt['id']}"))
        self.assertEqual(
            (attempt["version"], attempt["strongest_hint"]),
            (reply["attempt_version"], "small"),
        )

        body = finish_body(
            attempt["version"],
            help="small",
            time="12:30",
            code=None,
            notes=reply["notes"],
        )
        key = {"Idempotency-Key": "finish-day-1"}
        finished = self.ok(
            h.post(f"/attempts/{attempt['id']}/finish", body, headers=key)
        )
        self.assertEqual(
            (finished["review_stage"], finished["next_review_date"]),
            ("reconstruction", "2026-11-11"),
        )
        self.assertEqual(
            self.ok(h.post(f"/attempts/{attempt['id']}/finish", body, headers=key)),
            finished,
        )
        self.assertEqual(finished["attempt"]["report"]["status"], "pending")

        # The report, written by the queue.
        h.script.append(json.dumps(REPORT))
        worker = ReportWorker(
            h.runtime.sessions, h.runtime.config.tutor, h.state.chat_factory
        )
        self.assertTrue(worker.run_once())
        done = self.ok(h.get(f"/attempts/{attempt['id']}"))
        self.assertEqual(
            (done["report"]["status"], done["report"]["summary"]),
            ("done", "Solved with a set."),
        )

        self.ok(
            h.patch(
                f"/attempts/{attempt['id']}/reflection",
                {
                    "version": done["version"],
                    "mistake_labels": ["missed_edge_case"],
                    "takeaway": "Empty input.",
                },
            )
        )
        mistakes = self.ok(h.get("/mistakes"))["items"]
        self.assertEqual([m["takeaway"] for m in mistakes], ["Empty input."])
        topics = {t["id"]: t for t in self.ok(h.get("/topics"))["topics"]}
        self.assertEqual(topics["hash-table"]["attempts"], 1)
        self.assertNotEqual(topics["hash-table"]["level"], 1300)
        plan = self.ok(h.get("/desk"))["plan"]
        self.assertEqual(
            [i["status"] for i in items_of(plan)][:2], ["completed", "active"]
        )

        # Day 4: the idea comes back as a hidden transfer check.
        h.clock.now = NOW + timedelta(days=3)
        plan = self.ok(h.post("/plans/today/ensure"))
        checks = [i for i in items_of(plan) if i["is_check"]]
        self.assertEqual(len(checks), 1, plan)
        check = checks[0]
        self.assertEqual((check["reason"], check["kind"]), (TRANSFER, None))
        self.assertNotEqual(check["problem"]["id"], problem_id)

        hidden = self.ok(
            h.post(
                "/attempts",
                {
                    "problem_id": check["problem"]["id"],
                    "plan_item_id": check["id"],
                    "language": "python",
                },
            )
        )
        self.assertEqual((hidden["context"], hidden["evidence"]), ("mixed", "unseen"))
        for path in (
            "/topics",
            "/problems",
            "/mistakes",
            "/patterns",
            f"/problems/{problem_id}",
        ):
            with self.subTest(locked=path):
                response = h.get(path)
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (403, "HIDDEN_ASSESSMENT"),
                )
        desk = self.ok(h.get("/desk"))
        self.assertTrue(desk["hidden_assessment"])
        self.assertIsNone(desk["plan"])
        earlier = self.ok(h.get(f"/attempts/{attempt['id']}"))
        self.assertIsNone(earlier["takeaway"])
        self.assertIsNone(earlier["report"])

        solved = self.ok(
            h.post(
                f"/attempts/{hidden['id']}/finish",
                finish_body(hidden["version"]),
                headers={"Idempotency-Key": "finish-day-4"},
            )
        )
        self.assertEqual(solved["review_stage"], "mixed")
        self.ok(h.get("/topics"))  # unlocked again
        original = self.ok(h.get(f"/problems/{problem_id}"))
        self.assertEqual(
            (original["review"]["stage"], original["review"]["effective_date"]),
            ("mixed", "2026-11-25"),
        )
        sibling = self.ok(h.get(f"/problems/{check['problem']['id']}"))
        self.assertEqual(
            (sibling["review"]["stage"], sibling["review"]["action"]),
            ("covered", "none"),
        )


if __name__ == "__main__":
    unittest.main()
