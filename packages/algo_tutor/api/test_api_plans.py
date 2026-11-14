import unittest
from datetime import timedelta
from typing import Any

from packages.algo_tutor.api.testing import (
    NOW,
    Harness,
    finish_body,
    make_harness,
    seed_problem,
)
from packages.algo_tutor.store.models import ListEntry, Settings, StudyList
from packages.algo_tutor.store.timeutil import iso_utc, new_id


class PlanBase(unittest.TestCase):
    def setUp(self) -> None:
        self.h: Harness = make_harness()
        self.addCleanup(self.h.close)
        # Every topic starts at 1300; ties go in curriculum order: Hash Table
        # (3) before Two Pointers (4).
        self.hash = [
            seed_problem(
                self.h, f"Hash {n}", topic="hash-table", rating=1300 + n, popularity=50
            )
            for n in range(3)
        ]
        self.pointers = [
            seed_problem(
                self.h,
                f"Pointers {n}",
                topic="two-pointers",
                rating=1300 + n,
                popularity=50,
            )
            for n in range(3)
        ]

    def ensure(self) -> dict[str, Any]:
        response = self.h.post("/plans/today/ensure")
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, Any] = response.json()
        return result

    def settings(self, **values: object) -> None:
        with self.h.session() as session, session.begin():
            row = session.get_one(Settings, 1)
            for key, value in values.items():
                setattr(row, key, value)

    def start(self, problem_id: str, item_id: str | None = None) -> dict[str, Any]:
        response = self.h.post(
            "/attempts", {"problem_id": problem_id, "plan_item_id": item_id}
        )
        self.assertEqual(response.status_code, 201, response.text)
        result: dict[str, Any] = response.json()
        return result

    def finish(self, attempt: dict[str, Any], **overrides: object) -> dict[str, Any]:
        response = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(attempt["version"], **overrides),
            headers={"Idempotency-Key": f"finish-{attempt['id']}"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, Any] = response.json()
        return result


class EnsureTest(PlanBase):
    def test_ladder_picks_weakest_topics_first(self) -> None:
        plan = self.ensure()
        items = plan["items"]
        self.assertEqual(
            [i["reason"] for i in items],
            ["Hash Table · your level 1300", "Two Pointers · your level 1300"],
        )
        self.assertEqual([i["status"] for i in items], ["active", "queued"])
        self.assertEqual([i["kind"] for i in items], ["topic", "topic"])
        self.assertNotIn("review_of", items[0])
        self.assertEqual(
            (plan["plan_date"], plan["timezone"], plan["version"]),
            ("2026-11-08", "Asia/Tokyo", 1),
        )
        self.assertEqual(self.ensure(), plan)  # made once

    def test_desk(self) -> None:
        empty = self.h.get("/desk").json()
        self.assertIsNone(empty["plan"])
        self.assertTrue(empty["bank_empty"])
        plan = self.ensure()
        desk = self.h.get("/desk").json()
        self.assertEqual(
            (desk["left_today"], desk["total_today"], desk["checks_due"]), (2, 2, 0)
        )
        self.assertEqual(desk["plan"]["id"], plan["id"])
        self.assertFalse(desk["hidden_assessment"])

    def test_finishing_a_plan_item_promotes_the_next(self) -> None:
        plan = self.ensure()
        first = plan["items"][0]
        attempt = self.start(first["problem"]["id"], first["id"])
        self.assertEqual(attempt["plan_item_id"], first["id"])
        self.finish(attempt)
        after = self.ensure()
        self.assertEqual([i["status"] for i in after["items"]], ["completed", "active"])
        self.assertEqual(
            after["items"][0]["signals"],
            {"accepted_first_try": None, "difficulty": None},
        )
        self.assertGreater(after["version"], plan["version"])
        desk = self.h.get("/desk").json()
        self.assertEqual((desk["left_today"], desk["total_today"]), (1, 2))

    def test_unplanned_attempt_takes_slot_zero(self) -> None:
        attempt = self.start(self.pointers[2])
        plan = self.ensure()
        first = plan["items"][0]
        self.assertEqual(
            (first["reason"], first["attempt_id"], first["status"]),
            ("Current attempt", attempt["id"], "active"),
        )
        self.assertEqual(len(plan["items"]), 2)
        self.assertEqual(
            self.h.get(f"/attempts/{attempt['id']}").json()["plan_item_id"], first["id"]
        )
        self.finish(self.h.get(f"/attempts/{attempt['id']}").json())
        self.assertEqual(self.ensure()["items"][0]["status"], "completed")

    def test_study_list_comes_first(self) -> None:
        with self.h.session() as session, session.begin():
            row = StudyList(
                id=new_id(),
                name="Mine",
                source="leetcode",
                kind="own",
                created_at=iso_utc(NOW),
            )
            session.add(row)
            session.flush()
            for n, pid in enumerate([self.pointers[2], self.pointers[1]]):
                session.add(
                    ListEntry(
                        list_id=row.id,
                        problem_id=pid,
                        position=n,
                        added_at=iso_utc(NOW),
                    )
                )
            session.get_one(Settings, 1).active_list_leetcode = row.id
        items = self.ensure()["items"]
        self.assertEqual(
            [i["problem"]["id"] for i in items], [self.pointers[2], self.pointers[1]]
        )
        self.assertEqual({i["reason"] for i in items}, {"From your study list"})
        self.assertEqual({i["kind"] for i in items}, {"list"})

    def test_atcoder_review_comes_back(self) -> None:
        abc = seed_problem(
            self.h, "Logs", label=None, source="atcoder", contest="abc174"
        )
        attempt = self.start(abc)
        done = self.finish(attempt)
        self.assertEqual(done["next_review_date"], "2026-11-22")
        self.h.clock.now = NOW + timedelta(days=14)
        lane = [i for i in self.ensure()["items"] if i["lane"] == "atcoder"]
        self.assertEqual(
            [(i["problem"]["id"], i["reason"], i["is_check"]) for i in lane],
            [(abc, "Due for review — solve it again", True)],
        )


class ItemActionTest(PlanBase):
    def act(
        self, plan: dict[str, Any], item: dict[str, Any], body: dict[str, Any]
    ) -> Any:
        return self.h.post(
            f"/plans/{plan['id']}/items/{item['id']}/disposition",
            {"version": plan["version"]} | body,
        )

    def test_skip_promotes_and_bumps(self) -> None:
        plan = self.ensure()
        response = self.act(plan, plan["items"][0], {"action": "skip"})
        after = response.json()
        self.assertEqual(
            [(i["status"], i["disposition"]) for i in after["items"]],
            [("skipped", "skip"), ("active", None)],
        )
        stale = self.act(plan, plan["items"][1], {"action": "skip"})
        self.assertEqual(stale.json()["error"]["code"], "STALE")

    def test_swap(self) -> None:
        plan = self.ensure()
        after = self.act(plan, plan["items"][0], {"action": "swap"}).json()
        statuses = [(i["reason"], i["status"]) for i in after["items"]]
        self.assertEqual(statuses[0], ("Hash Table · your level 1300", "skipped"))
        self.assertEqual(len(statuses), 3)
        self.assertIn("active", [s for _, s in statuses[1:]])

    def test_swap_with_nothing_left(self) -> None:
        self.settings(questions_per_day=6)
        plan = self.ensure()
        self.assertEqual(len(plan["items"]), 6)
        refused = self.act(plan, plan["items"][0], {"action": "swap"})
        self.assertEqual(
            (refused.status_code, refused.json()["error"]["code"]),
            (409, "NO_REPLACEMENT"),
        )

    def test_snooze_needs_a_future_date_and_makes_the_problem_wait(self) -> None:
        plan = self.ensure()
        item = plan["items"][1]
        past = self.act(plan, item, {"action": "snooze", "snooze_until": "2026-11-08"})
        self.assertEqual(past.status_code, 422)
        after = self.act(
            plan, item, {"action": "snooze", "snooze_until": "2026-11-20"}
        ).json()
        self.assertEqual(after["items"][1]["disposition"], "snooze")
        rebuilt = self.h.post(
            f"/plans/{plan['id']}/rebuild",
            {"version": after["version"]},
            headers={"Idempotency-Key": "r1"},
        ).json()
        live = [
            i["problem"]["id"] for i in rebuilt["items"] if i["status"] != "skipped"
        ]
        self.assertNotIn(item["problem"]["id"], live)

    def test_started_items_cannot_be_changed(self) -> None:
        plan = self.ensure()
        self.start(plan["items"][0]["problem"]["id"], plan["items"][0]["id"])
        plan = self.ensure()
        refused = self.act(plan, plan["items"][0], {"action": "skip"})
        self.assertEqual(refused.json()["error"]["code"], "ACTIVE_ATTEMPT")

    def test_reorder_and_activate(self) -> None:
        plan = self.ensure()
        first, second = plan["items"]
        bad = self.h.post(
            f"/plans/{plan['id']}/reorder",
            {"version": 1, "lane": "leetcode", "item_ids": [first["id"]]},
        )
        self.assertEqual(bad.status_code, 422)
        moved = self.h.post(
            f"/plans/{plan['id']}/reorder",
            {"version": 1, "lane": "leetcode", "item_ids": [second["id"], first["id"]]},
        ).json()
        self.assertEqual([i["id"] for i in moved["items"]], [second["id"], first["id"]])
        activated = self.h.post(
            f"/plans/{plan['id']}/items/{second['id']}/activate",
            {"version": moved["version"]},
        ).json()
        self.assertEqual(
            [(i["id"], i["status"]) for i in activated["items"]],
            [(second["id"], "active"), (first["id"], "queued")],
        )

    def test_rebuild_keeps_started_work_and_replays(self) -> None:
        plan = self.ensure()
        attempt = self.start(plan["items"][0]["problem"]["id"], plan["items"][0]["id"])
        self.finish(attempt)
        plan = self.ensure()
        rebuilt = self.h.post(
            f"/plans/{plan['id']}/rebuild",
            {"version": plan["version"]},
            headers={"Idempotency-Key": "r"},
        )
        self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
        body = rebuilt.json()
        self.assertEqual(body["items"][0]["status"], "completed")
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["version"], plan["version"] + 1)
        replay = self.h.post(
            f"/plans/{plan['id']}/rebuild",
            {"version": plan["version"]},
            headers={"Idempotency-Key": "r"},
        )
        self.assertEqual(replay.json(), body)
        mismatch = self.h.post(
            f"/plans/{plan['id']}/rebuild",
            {"version": body["version"]},
            headers={"Idempotency-Key": "r"},
        )
        self.assertEqual(mismatch.json()["error"]["code"], "IDEMPOTENCY_MISMATCH")
        stale = self.h.post(
            f"/plans/{plan['id']}/rebuild",
            {"version": plan["version"]},
            headers={"Idempotency-Key": "r2"},
        )
        self.assertEqual(stale.json()["error"]["code"], "STALE")

    def test_yesterdays_plan_is_not_rebuilt(self) -> None:
        plan = self.ensure()
        self.h.clock.now = NOW + timedelta(days=1)
        response = self.h.post(
            f"/plans/{plan['id']}/rebuild",
            {"version": 1},
            headers={"Idempotency-Key": "y"},
        )
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
