import json
import os
import unittest
from datetime import timedelta

from packages.algo_tutor.api.testing import (
    NOW,
    Harness,
    finish_body,
    make_harness,
    seed_problem,
)
from packages.algo_tutor.store.models import Attempt
from packages.algo_tutor.tutor.worker import ReportWorker

SOLUTION = "packages/programming_exercise/leetcode/src/01_data_structures/hash_tables/0001_two_sum_easy.py"
REPORT = {
    "summary": "Solved with a hash map.",
    "strengths": "Clear.",
    "improvements": "Edge cases.",
    "complexity": "O(n).",
    "practice": "More hashing.",
}


class AttemptBase(unittest.TestCase):
    config = "tutor:\n  enabled: true\n"

    def setUp(self) -> None:
        self.h: Harness = make_harness(
            self.config, repo_files={SOLUTION: "class Solution:\n    pass\n"}
        )
        self.addCleanup(self.h.close)
        self.pid = seed_problem(self.h, "Two Sum", topic="hash-table", rating=1300)

    def start(self, **body: object) -> dict[str, object]:
        response = self.h.post("/attempts", {"problem_id": self.pid} | body)
        self.assertEqual(response.status_code, 201, response.text)
        result: dict[str, object] = response.json()
        return result

    def finish(
        self, attempt: dict[str, object], key: str = "finish-1", **overrides: object
    ) -> dict[str, object]:
        response = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(int(str(attempt["version"])), **overrides),
            headers={"Idempotency-Key": key},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, object] = response.json()
        return result


class StartTest(AttemptBase):
    def test_library_start_is_targeted_near_transfer(self) -> None:
        attempt = self.start(language="go")
        self.assertEqual(
            (attempt["context"], attempt["evidence"]), ("targeted", "near_transfer")
        )
        self.assertEqual(
            (attempt["status"], attempt["language"], attempt["version"]),
            ("active", "go", 1),
        )
        self.assertEqual(attempt["study_date"], "2026-11-08")  # 18:00 in Tokyo
        self.assertIsNone(attempt["report"])  # not completed
        with self.h.session() as session:
            self.assertTrue(
                session.get_one(Attempt, str(attempt["id"])).problem_id == self.pid
            )

    def test_one_unfinished_attempt(self) -> None:
        self.start()
        second = self.h.post("/attempts", {"problem_id": self.pid})
        self.assertEqual(
            (second.status_code, second.json()["error"]["code"]),
            (409, "ACTIVE_ATTEMPT"),
        )

    def test_exposed_problem_counts_as_retention(self) -> None:
        # Ported from upstream disclosure-mutations: once seen, never unseen evidence.
        first = self.start()
        self.finish(first)
        again = self.start()
        self.assertEqual(again["evidence"], "retention")

    def test_unknown_problem(self) -> None:
        response = self.h.post("/attempts", {"problem_id": "nope"})
        self.assertEqual(
            (response.status_code, response.json()["error"]["code"]), (404, "NOT_FOUND")
        )


class StopwatchTest(AttemptBase):
    def timer(
        self, attempt: dict[str, object], action: str, **extra: object
    ) -> dict[str, object]:
        response = self.h.post(
            f"/attempts/{attempt['id']}/timer",
            {"version": attempt["version"], "action": action} | extra,
        )
        self.assertEqual(response.status_code, 200, response.text)
        result: dict[str, object] = response.json()
        return result

    def test_heartbeats_count_short_gaps(self) -> None:
        attempt = self.start()
        self.h.clock.now = NOW + timedelta(seconds=30)
        attempt = self.timer(attempt, "heartbeat")
        self.h.clock.now += timedelta(seconds=45)
        attempt = self.timer(attempt, "heartbeat")
        self.assertEqual((attempt["active_seconds"], attempt["version"]), (75, 3))

    def test_long_gap_pauses_and_asks(self) -> None:
        attempt = self.start()
        self.h.clock.now = NOW + timedelta(seconds=60)
        attempt = self.timer(attempt, "heartbeat")
        self.h.clock.now += timedelta(minutes=10)  # the laptop slept
        attempt = self.timer(attempt, "heartbeat")
        self.assertEqual(
            (attempt["status"], attempt["needs_gap_decision"]), ("paused", True)
        )
        self.assertEqual((attempt["active_seconds"], attempt["gap_seconds"]), (60, 600))
        refused = self.h.post(
            f"/attempts/{attempt['id']}/timer",
            {"version": attempt["version"], "action": "resume"},
        )
        self.assertEqual(
            (refused.status_code, refused.json()["error"]["code"]),
            (409, "GAP_DECISION"),
        )
        resumed = self.timer(attempt, "resume", include_gap=True)
        self.assertEqual(
            (resumed["status"], resumed["active_seconds"]), ("active", 660)
        )

    def test_gap_not_counted(self) -> None:
        attempt = self.start()
        self.h.clock.now = NOW + timedelta(minutes=5)
        attempt = self.timer(attempt, "heartbeat")
        resumed = self.timer(attempt, "resume", include_gap=False)
        self.assertEqual(resumed["active_seconds"], 0)

    def test_stale_version(self) -> None:
        attempt = self.start()
        self.timer(attempt, "pause")
        stale = self.h.post(
            f"/attempts/{attempt['id']}/timer", {"version": 1, "action": "resume"}
        )
        self.assertEqual(
            (stale.status_code, stale.json()["error"]["code"]), (409, "STALE")
        )


class DraftTest(AttemptBase):
    def draft(self, attempt: dict[str, object], **body: object) -> object:
        return self.h.patch(
            f"/attempts/{attempt['id']}/draft", {"version": attempt["version"]} | body
        )

    def test_editor_draft_and_versions(self) -> None:
        attempt = self.start()
        saved = self.draft(attempt, code="x = 1", notes="idea")
        assert hasattr(saved, "json")
        body = saved.json()
        self.assertEqual(
            (body["code"], body["notes"], body["version"]), ("x = 1", "idea", 2)
        )
        stale = self.draft(attempt, notes="old tab")
        assert hasattr(stale, "json")
        self.assertEqual(stale.json()["error"]["code"], "STALE")

    def test_linked_file_is_copied(self) -> None:
        attempt = self.start()
        response = self.h.patch(
            f"/attempts/{attempt['id']}/draft",
            {"version": 1, "solution_path": f"./{SOLUTION}"},
        )
        body = response.json()
        self.assertEqual(body["solution_path"], SOLUTION)
        self.assertEqual(body["code"], "class Solution:\n    pass\n")
        self.assertIsNotNone(body["code_copied_at"])
        # Every later save copies again; typed code is ignored while linked.
        (self.h.repo_root / SOLUTION).write_text(
            "class Solution:\n    def f(self): ...\n"
        )
        later = self.h.patch(
            f"/attempts/{attempt['id']}/draft",
            {"version": 2, "notes": "n", "code": "ignored"},
        )
        self.assertIn("def f", later.json()["code"])
        editor = self.h.patch(
            f"/attempts/{attempt['id']}/draft", {"version": 3, "solution_path": None}
        )
        self.assertIsNone(editor.json()["solution_path"])

    def test_bad_paths(self) -> None:
        attempt = self.start()
        outside = self.h.repo_root.parent / "secret.py"
        outside.write_text("x")
        os.symlink(outside, self.h.repo_root / "link.py")
        (self.h.repo_root / "binary.py").write_bytes(b"\xff\xfe\x00")
        (self.h.repo_root / "folder").mkdir()
        cases = {
            "../secret.py": "SOLUTION_PATH_INVALID",
            "/etc/passwd": "SOLUTION_PATH_INVALID",
            "link.py": "SOLUTION_PATH_INVALID",
            "binary.py": "SOLUTION_PATH_INVALID",
            "folder": "SOLUTION_PATH_INVALID",
            "missing.py": "SOLUTION_FILE_MISSING",
        }
        for path, code in cases.items():
            with self.subTest(path=path):
                response = self.h.patch(
                    f"/attempts/{attempt['id']}/draft",
                    {"version": 1, "solution_path": path},
                )
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (400, code),
                )

    def test_finish_fails_when_the_linked_file_is_gone(self) -> None:
        attempt = self.start()
        self.h.patch(
            f"/attempts/{attempt['id']}/draft",
            {"version": 1, "solution_path": SOLUTION},
        )
        (self.h.repo_root / SOLUTION).unlink()
        response = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(2),
            headers={"Idempotency-Key": "k"},
        )
        self.assertEqual(
            (response.status_code, response.json()["error"]["code"]),
            (400, "SOLUTION_FILE_MISSING"),
        )
        self.assertEqual(
            self.h.get(f"/attempts/{attempt['id']}").json()["status"], "active"
        )


class FinishTest(AttemptBase):
    def test_finish_schedules_and_is_idempotent(self) -> None:
        attempt = self.start()
        done = self.finish(attempt, confidence=4)
        saved = done["attempt"]
        assert isinstance(saved, dict)
        self.assertEqual(
            (saved["status"], saved["outcome"], saved["active_seconds"]),
            ("completed", "solved", 600),
        )
        # Solved alone, near-transfer evidence: +14 days at stage mixed.
        self.assertEqual(
            (done["next_review_date"], done["review_stage"]), ("2026-11-22", "mixed")
        )
        replay = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(1, confidence=4),
            headers={"Idempotency-Key": "finish-1"},
        )
        self.assertEqual(replay.json(), done)
        other = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(1),
            headers={"Idempotency-Key": "finish-1"},
        )
        self.assertEqual(other.json()["error"]["code"], "IDEMPOTENCY_MISMATCH")
        again = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(2),
            headers={"Idempotency-Key": "k2"},
        )
        self.assertEqual(again.json()["error"]["code"], "COMPLETED")

    def test_repair_and_manual_and_no_review(self) -> None:
        attempt = self.start()
        done = self.finish(attempt, help="unknown")
        self.assertEqual(
            (done["next_review_date"], done["review_stage"]), ("2026-11-09", "repair")
        )
        second = self.start()
        manual = self.finish(
            second, key="k2", review_choice="manual", review_date="2026-12-01"
        )
        self.assertEqual(manual["next_review_date"], "2026-12-01")
        third = self.start()
        none = self.finish(third, key="k3", review_choice="none")
        self.assertIsNone(none["next_review_date"])

    def test_validation(self) -> None:
        attempt = self.start()
        empty = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(1, code="  "),
            headers={"Idempotency-Key": "a"},
        )
        self.assertEqual(empty.status_code, 422)
        no_date = self.h.post(
            f"/attempts/{attempt['id']}/finish",
            finish_body(1, review_choice="manual"),
            headers={"Idempotency-Key": "b"},
        )
        self.assertEqual(no_date.status_code, 422)
        no_key = self.h.post(f"/attempts/{attempt['id']}/finish", finish_body(1))
        self.assertEqual(no_key.json()["error"]["code"], "VALIDATION")

    def test_cancel(self) -> None:
        attempt = self.start()
        self.assertEqual(self.h.delete(f"/attempts/{attempt['id']}").status_code, 204)
        self.assertEqual(self.h.get(f"/attempts/{attempt['id']}").status_code, 404)
        done = self.finish(self.start())
        saved = done["attempt"]
        assert isinstance(saved, dict)
        refused = self.h.delete(f"/attempts/{saved['id']}")
        self.assertEqual(
            (refused.status_code, refused.json()["error"]["code"]), (409, "COMPLETED")
        )

    def test_reflection_and_signals(self) -> None:
        saved = self.finish(self.start())["attempt"]
        assert isinstance(saved, dict)
        early = self.h.patch(
            f"/attempts/{saved['id']}/reflection",
            {"version": 1, "mistake_labels": ["wrong_approach"], "takeaway": "t"},
        )
        self.assertEqual(early.json()["error"]["code"], "STALE")
        reflected = self.h.patch(
            f"/attempts/{saved['id']}/reflection",
            {
                "version": saved["version"],
                "mistake_labels": ["wrong_approach", "wrong_approach"],
                "takeaway": "Map first.",
            },
        ).json()
        self.assertEqual(
            (reflected["mistake_labels"], reflected["takeaway"]),
            (["wrong_approach"], "Map first."),
        )
        signals = self.h.patch(
            f"/attempts/{saved['id']}/signals", {"difficulty": "too_easy"}
        ).json()
        self.assertEqual(
            signals["signals"], {"accepted_first_try": None, "difficulty": "too_easy"}
        )
        cleared = self.h.patch(
            f"/attempts/{saved['id']}/signals",
            {"difficulty": None, "accepted_first_try": False},
        )
        self.assertEqual(
            cleared.json()["signals"], {"accepted_first_try": False, "difficulty": None}
        )
        self.assertEqual(
            cleared.json()["version"], reflected["version"]
        )  # signals aren't versioned

    def test_list_attempts(self) -> None:
        self.finish(self.start())
        self.start()
        rows = self.h.get("/attempts", params={"problem_id": self.pid}).json()
        self.assertEqual([r["status"] for r in rows], ["active", "completed"])


class ReportTest(AttemptBase):
    def test_finish_queues_a_report_the_worker_writes(self) -> None:
        saved = self.finish(self.start())["attempt"]
        assert isinstance(saved, dict)
        self.assertEqual(saved["report"]["status"], "pending")
        self.h.script.append(json.dumps(REPORT))
        work = ReportWorker(
            self.h.runtime.sessions,
            self.h.runtime.config.tutor,
            self.h.state.chat_factory,
        )
        self.assertTrue(work.run_once())
        report = self.h.get(f"/attempts/{saved['id']}").json()["report"]
        self.assertEqual(
            (report["status"], report["summary"]), ("done", "Solved with a hash map.")
        )
        again = self.h.post(f"/attempts/{saved['id']}/report")
        self.assertEqual(again.json()["status"], "done")  # not repeated

    def test_failed_report_can_be_retried(self) -> None:
        saved = self.finish(self.start())["attempt"]
        assert isinstance(saved, dict)
        self.h.script.append(ConnectionError("refused"))
        ReportWorker(
            self.h.runtime.sessions,
            self.h.runtime.config.tutor,
            self.h.state.chat_factory,
        ).run_once()
        failed = self.h.get(f"/attempts/{saved['id']}").json()["report"]
        self.assertEqual(
            (failed["status"], failed["error_kind"]), ("failed", "unavailable")
        )
        self.assertEqual(
            self.h.post(f"/attempts/{saved['id']}/report").json()["status"], "pending"
        )


class HintTest(AttemptBase):
    def test_hint_appends_to_notes(self) -> None:
        attempt = self.start()
        self.h.patch(
            f"/attempts/{attempt['id']}/draft",
            {"version": 1, "notes": "brute force first"},
        )
        self.h.clock.now = NOW + timedelta(seconds=90)
        self.h.post(
            f"/attempts/{attempt['id']}/timer", {"version": 2, "action": "heartbeat"}
        )
        self.h.script.append(
            json.dumps(
                {
                    "reply": "What if a value repeats?",
                    "hint": "Think about duplicates.",
                    "level": "small",
                    "analysis": "Nested loops.",
                }
            )
        )
        reply = self.h.post(f"/attempts/{attempt['id']}/hints", {"text": "I'm stuck"})
        self.assertEqual(reply.status_code, 200, reply.text)
        body = reply.json()
        self.assertEqual(body["attempt_version"], 4)
        self.assertEqual(
            body["notes"],
            "brute force first\n\n[Stuck at 01:30] Asked Algo-chan for help.\n"
            "Where I was: Nested loops.\nHint (small): Think about duplicates.",
        )
        self.assertEqual(body["strongest_level"], "small")
        sent = json.loads(self.h.chats[0].calls[0][1].text)
        self.assertNotIn("topic", json.dumps(sent))
        conversation = self.h.get(f"/attempts/{attempt['id']}/hints").json()
        self.assertEqual(
            [m["role"] for m in conversation["messages"]], ["learner", "tutor"]
        )
        self.assertEqual(
            self.h.get(f"/attempts/{attempt['id']}").json()["strongest_hint"], "small"
        )

    def test_tutor_failure_is_503_with_kind(self) -> None:
        attempt = self.start()
        self.h.script.append(ConnectionError("refused"))
        response = self.h.post(f"/attempts/{attempt['id']}/hints", {"text": "help"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"],
            response.json()["error"]
            | {"code": "TUTOR_UNAVAILABLE", "kind": "unavailable"},
        )
        self.assertEqual(
            self.h.get(f"/attempts/{attempt['id']}/hints").json()["messages"], []
        )


class TutorOffTest(AttemptBase):
    config = "tutor:\n  enabled: false\n"

    def test_no_report_and_no_hints(self) -> None:
        saved = self.finish(self.start())["attempt"]
        assert isinstance(saved, dict)
        self.assertEqual(saved["report"]["status"], "none")
        response = self.h.post(f"/attempts/{saved['id']}/report")
        self.assertEqual(
            (response.status_code, response.json()["error"]["kind"]), (503, "disabled")
        )
        attempt = self.start()
        hint = self.h.post(f"/attempts/{attempt['id']}/hints", {"text": "help"})
        self.assertEqual(hint.json()["error"]["kind"], "disabled")


if __name__ == "__main__":
    unittest.main()
