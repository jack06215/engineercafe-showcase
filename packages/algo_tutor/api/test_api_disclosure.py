"""Transfer checks and the hidden assessment (SPEC §8.3–§8.4, §9).

Ports the engine side of upstream's disclosure tests: an exposed problem is
never unseen evidence and never a transfer check, and nothing that could
name a check's idea is served while it runs.
"""

import unittest
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from packages.algo_tutor.api.testing import (
    NOW,
    Harness,
    finish_body,
    make_harness,
    seed_problem,
)
from packages.algo_tutor.store.models import Problem, ProblemPattern, ReviewTarget


class TransferCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h: Harness = make_harness()
        self.addCleanup(self.h.close)
        self.idea = seed_problem(
            self.h, "Pair Sum", topic="two-pointers", rating=1300, popularity=50
        )
        self.sibling = seed_problem(
            self.h, "Triplets", topic="two-pointers", rating=1320, popularity=40
        )
        # Closer in rating, but already seen: never a fair check.
        self.seen = seed_problem(
            self.h, "Seen Before", topic="two-pointers", rating=1300, popularity=99
        )
        with self.h.session() as session, session.begin():
            session.get_one(Problem, self.seen).exposed = True
            session.add(
                ProblemPattern(problem_id=self.sibling, pattern_id="01_sliding_window")
            )

    def practise(
        self, problem_id: str, item_id: str | None = None, **finish: object
    ) -> dict[str, Any]:
        started = self.h.post(
            "/attempts", {"problem_id": problem_id, "plan_item_id": item_id}
        )
        self.assertEqual(started.status_code, 201, started.text)
        attempt = started.json()
        if not finish.pop("leave_open", False):
            done = self.h.post(
                f"/attempts/{attempt['id']}/finish",
                finish_body(attempt["version"], **finish),
                headers={"Idempotency-Key": f"f-{attempt['id']}"},
            )
            self.assertEqual(done.status_code, 200, done.text)
            result: dict[str, Any] = done.json()["attempt"]
            return result
        return dict(attempt)

    def target(self, problem_id: str) -> tuple[str, str, str | None]:
        with self.h.session() as session:
            row = session.scalars(
                select(ReviewTarget).where(ReviewTarget.problem_id == problem_id)
            ).one()
            return row.stage, row.action, row.effective_date

    def check_item(self) -> dict[str, Any]:
        items = self.h.post("/plans/today/ensure").json()["items"]
        checks = [i for i in items if i["is_check"]]
        self.assertEqual(len(checks), 1, items)
        return checks[0]

    def test_transfer_check_runs_hidden_and_retires_the_idea(self) -> None:
        first = self.practise(self.idea)
        self.h.patch(
            f"/attempts/{first['id']}/reflection",
            {
                "version": first["version"],
                "mistake_labels": ["wrong_approach"],
                "takeaway": "Two pointers from both ends",
            },
        )
        self.assertEqual(self.target(self.idea), ("mixed", "recommended", "2026-11-22"))

        self.h.clock.now = NOW + timedelta(days=14)
        item = self.check_item()
        self.assertEqual(
            (item["problem"]["id"], item["kind"], item["reason"]),
            (self.sibling, None, "Transfer check — spot the approach yourself"),
        )
        self.assertNotIn("review_of", item)

        check = self.practise(self.sibling, item["id"], leave_open=True)
        self.assertEqual((check["context"], check["evidence"]), ("mixed", "unseen"))
        self.assertIsNone(check["patterns"])

        locked = [
            self.h.get("/topics"),
            self.h.get("/topics/two-pointers"),
            self.h.patch("/topics/two-pointers/notebook", {"version": 1, "notes": "x"}),
            self.h.patch(f"/reviews/{self.idea}", {"version": 2, "action": "none"}),
            self.h.post("/plans/today/ensure"),
        ]
        for response in locked:
            with self.subTest(url=str(response.url)):
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (403, "HIDDEN_ASSESSMENT"),
                )
        desk = self.h.get("/desk").json()
        self.assertTrue(desk["hidden_assessment"])
        self.assertIsNone(desk["plan"])
        self.assertEqual(
            (desk["active_attempt"]["id"], desk["active_attempt"]["problem_title"]),
            (check["id"], None),
        )
        earlier = self.h.get(f"/attempts/{first['id']}").json()
        self.assertEqual(
            (
                earlier["takeaway"],
                earlier["mistake_labels"],
                earlier["report"],
                earlier["signals"],
                earlier["patterns"],
            ),
            (None, None, None, None, None),
        )

        done = self.h.post(
            f"/attempts/{check['id']}/finish",
            finish_body(check["version"]),
            headers={"Idempotency-Key": "check"},
        ).json()
        # Two solo solves at the 14-day stage: the idea retires.
        self.assertEqual(
            (done["review_stage"], done["next_review_date"]), ("retired", None)
        )
        self.assertEqual(self.target(self.idea), ("retired", "none", None))
        self.assertEqual(self.target(self.sibling), ("covered", "none", None))
        self.assertEqual(self.h.get("/topics").status_code, 200)
        self.assertEqual(
            self.h.get(f"/attempts/{first['id']}").json()["takeaway"],
            "Two pointers from both ends",
        )

    def test_struggle_brings_an_easier_repair(self) -> None:
        self.practise(self.sibling, help="major")
        self.assertEqual(self.target(self.sibling)[0], "repair")
        self.h.clock.now = NOW + timedelta(days=1)
        item = self.check_item()
        self.assertEqual(item["kind"], "topic")
        self.assertEqual(
            item["reason"], "Two Pointers · easier practice after Triplets"
        )
        repair = self.practise(item["problem"]["id"], item["id"], leave_open=True)
        self.assertEqual(repair["context"], "targeted")
        self.assertEqual(self.h.get("/topics").status_code, 200)

    def test_no_fair_sibling_means_visible_practice(self) -> None:
        self.practise(self.idea)
        self.practise(self.sibling)
        self.h.clock.now = NOW + timedelta(days=14)
        items = self.h.post("/plans/today/ensure").json()["items"]
        reasons = [i["reason"] for i in items]
        self.assertNotIn("Transfer check — spot the approach yourself", reasons)
        self.assertTrue(
            any(r.startswith("Two Pointers · practice after") for r in reasons), reasons
        )

    def test_exposed_problem_starts_as_retention(self) -> None:
        attempt = self.practise(self.seen, leave_open=True)
        self.assertEqual(attempt["evidence"], "retention")


if __name__ == "__main__":
    unittest.main()
