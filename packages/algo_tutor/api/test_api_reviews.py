import unittest

from packages.algo_tutor.api.testing import (
    Harness,
    finish_body,
    make_harness,
    seed_problem,
)


class ReviewEditorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h: Harness = make_harness()
        self.addCleanup(self.h.close)
        self.pid = seed_problem(self.h, "Two Sum", topic="hash-table", rating=1300)

    def finish(self) -> None:
        attempt = self.h.post("/attempts", {"problem_id": self.pid}).json()
        done = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(1),
            headers={"Idempotency-Key": "f"},
        )
        self.assertEqual(done.status_code, 200, done.text)

    def test_editing_a_schedule(self) -> None:
        self.finish()
        manual = self.h.patch(
            f"/reviews/{self.pid}",
            {"version": 1, "action": "manual", "review_date": "2026-12-24"},
        )
        self.assertEqual(manual.status_code, 200, manual.text)
        body = manual.json()
        self.assertEqual(
            (
                body["action"],
                body["effective_date"],
                body["recommended_date"],
                body["stage"],
                body["version"],
            ),
            ("manual", "2026-12-24", "2026-11-22", "mixed", 2),
        )
        stale = self.h.patch(f"/reviews/{self.pid}", {"version": 1, "action": "none"})
        self.assertEqual(
            (stale.status_code, stale.json()["error"]["code"]), (409, "STALE")
        )
        none = self.h.patch(
            f"/reviews/{self.pid}", {"version": 2, "action": "none"}
        ).json()
        self.assertEqual((none["action"], none["effective_date"]), ("none", None))
        back = self.h.patch(
            f"/reviews/{self.pid}", {"version": 3, "action": "recommended"}
        ).json()
        self.assertEqual(
            (back["action"], back["effective_date"]), ("recommended", "2026-11-22")
        )

    def test_dates_are_required(self) -> None:
        self.finish()
        for action in ("manual", "snooze"):
            with self.subTest(action=action):
                response = self.h.patch(
                    f"/reviews/{self.pid}", {"version": 1, "action": action}
                )
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (422, "VALIDATION"),
                )

    def test_unattempted_problem_can_only_be_snoozed(self) -> None:
        missing = self.h.patch(
            f"/reviews/{self.pid}",
            {"version": 1, "action": "manual", "review_date": "2026-12-01"},
        )
        self.assertEqual(missing.status_code, 404)
        snoozed = self.h.patch(
            f"/reviews/{self.pid}",
            {"version": 1, "action": "snooze", "review_date": "2026-12-01"},
        )
        self.assertEqual(
            (
                snoozed.json()["stage"],
                snoozed.json()["action"],
                snoozed.json()["effective_date"],
            ),
            ("snoozed", "snooze", "2026-12-01"),
        )
        self.assertEqual(
            self.h.patch("/reviews/nope", {"version": 1, "action": "none"}).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
