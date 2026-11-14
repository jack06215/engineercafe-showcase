import json
import threading
import unittest
from datetime import timedelta

from packages.algo_tutor.catalogue.testing import NOW, complete_attempt, temp_db
from packages.algo_tutor.config import TaskConfig, TutorConfig
from packages.algo_tutor.domain.enums import (
    PlanItemStatus,
    ReportStatus,
    TutorErrorKind,
)
from packages.algo_tutor.store.models import Attempt, DailyPlan, PlanItem, Problem
from packages.algo_tutor.store.timeutil import iso_utc, new_id
from packages.algo_tutor.tutor import worker
from packages.algo_tutor.tutor.fake_models import ScriptedChat

REPORT = {
    "summary": "Solved it.",
    "strengths": "Tidy.",
    "improvements": "Edge cases.",
    "complexity": "O(n).",
    "practice": "More hashing.",
}


def problem(slug: str, title: str) -> Problem:
    return Problem(
        id=new_id(),
        source="leetcode",
        external_id=slug,
        title=title,
        url=f"https://leetcode.com/problems/{slug}/",
        difficulty_label="Easy",
        created_at=iso_utc(NOW),
    )


class WorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()
        self.addCleanup(self.db.close)
        self.chats: list[ScriptedChat] = []
        self.script: list[object] = []

    def factory(self, task: TaskConfig) -> ScriptedChat:
        chat = ScriptedChat(script=self.script)
        self.chats.append(chat)
        return chat

    def worker(self) -> worker.ReportWorker:
        return worker.ReportWorker(
            self.db.sessions, TutorConfig(), chat_factory=self.factory
        )

    def finished(
        self,
        title: str = "Two Sum",
        review_of: Problem | None = None,
        kind: str | None = None,
    ) -> str:
        with self.db.sessions() as session, session.begin():
            p = problem(title.lower().replace(" ", "-"), title)
            session.add(p)
            session.flush()
            for days in (3, 2):  # two earlier attempts at the same problem
                complete_attempt(session, p, NOW - timedelta(days=days))
            a = complete_attempt(session, p, NOW)
            a.code = "print(1)"
            a.notes = "ハッシュで解いた"
            if review_of is not None:
                session.add(review_of)
                plan = DailyPlan(id=new_id(), date="2026-11-08", timezone="Asia/Tokyo")
                session.add(plan)
                session.flush()
                item = PlanItem(
                    id=new_id(),
                    plan_id=plan.id,
                    lane="leetcode",
                    position=0,
                    problem_id=p.id,
                    status=PlanItemStatus.COMPLETED.value,
                    kind=kind,
                    review_of=review_of.id,
                )
                session.add(item)
                session.flush()
                a.plan_item_id = item.id
            self.assertTrue(worker.request_report(session, a, tutor_enabled=True))
            return a.id

    def attempt(self, attempt_id: str) -> Attempt:
        with self.db.sessions() as session:
            return session.get_one(Attempt, attempt_id)

    def test_report_is_written(self) -> None:
        attempt_id = self.finished()
        self.script.append(json.dumps(REPORT))
        w = self.worker()
        self.assertTrue(w.run_once())
        self.assertFalse(w.run_once())
        done = self.attempt(attempt_id)
        self.assertEqual(done.report_status, ReportStatus.DONE)
        self.assertEqual(done.report, REPORT)
        self.assertEqual(done.report_model, "ollama:qwen3.6:35b")
        sent = json.loads(self.chats[0].calls[0][1].text)
        self.assertEqual(len(sent["history"]), 2)
        self.assertNotIn("check_of", sent)
        self.assertTrue(self.chats[0].calls[0][0].text.endswith("Japanese."))

    def test_transfer_check_names_the_original(self) -> None:
        original = problem("contains-duplicate", "Contains Duplicate")
        self.finished(review_of=original, kind=None)
        self.script.append(json.dumps(REPORT))
        self.worker().run_once()
        sent = json.loads(self.chats[0].calls[0][1].text)
        self.assertEqual(
            sent["check_of"], {"title": "Contains Duplicate", "kind": "transfer"}
        )

    def test_failure_keeps_kind_and_message(self) -> None:
        attempt_id = self.finished()
        self.script.append(ConnectionError("refused"))
        self.worker().run_once()
        failed = self.attempt(attempt_id)
        self.assertEqual(
            (failed.report_status, failed.report_error),
            (ReportStatus.FAILED, TutorErrorKind.UNAVAILABLE),
        )
        self.assertIn("ollama", failed.report_error_message or "")
        # "Try again" queues it once more.
        with self.db.sessions() as session, session.begin():
            self.assertTrue(
                worker.request_report(
                    session, session.get_one(Attempt, attempt_id), tutor_enabled=True
                )
            )

    def test_not_repeated_once_done_and_never_when_off(self) -> None:
        attempt_id = self.finished()
        self.script.append(json.dumps(REPORT))
        self.worker().run_once()
        with self.db.sessions() as session, session.begin():
            a = session.get_one(Attempt, attempt_id)
            self.assertFalse(worker.request_report(session, a, tutor_enabled=True))
            a.report_status = ReportStatus.NONE.value
            self.assertFalse(worker.request_report(session, a, tutor_enabled=False))

    def test_generating_goes_back_to_pending_at_startup(self) -> None:
        attempt_id = self.finished()
        with self.db.sessions() as session, session.begin():
            self.assertIsNotNone(worker.claim(session))
        self.assertEqual(
            self.attempt(attempt_id).report_status, ReportStatus.GENERATING
        )
        with self.db.sessions() as session, session.begin():
            self.assertEqual(worker.recover(session), 1)
            self.assertEqual(worker.pending_count(session), 1)

    def test_thread_drains_the_queue(self) -> None:
        ids = [self.finished("Two Sum"), self.finished("Valid Anagram")]
        self.script.extend([json.dumps(REPORT), json.dumps(REPORT)])
        idle = threading.Event()
        w = worker.ReportWorker(
            self.db.sessions, TutorConfig(), chat_factory=self.factory, on_idle=idle.set
        )
        w.start()
        self.addCleanup(w.stop)
        self.assertTrue(idle.wait(10))
        self.assertEqual(
            [self.attempt(i).report_status for i in ids],
            [ReportStatus.DONE, ReportStatus.DONE],
        )


if __name__ == "__main__":
    unittest.main()
