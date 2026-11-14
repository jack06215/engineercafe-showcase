import unittest

from packages.algo_tutor.api.testing import install_fake_bank, make_harness


class SetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_setup_once_following_a_course(self) -> None:
        before = self.h.get("/setup").json()
        self.assertEqual(
            before,
            {
                "onboarding_complete": False,
                "timezone": "Asia/Tokyo",
                "questions_per_day": 2,
            },
        )
        done = self.h.post(
            "/setup",
            {"questions_per_day": 3, "download_bank": False, "follow": "blind-75"},
        )
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["questions_per_day"], 3)
        self.assertTrue(done.json()["onboarding_complete"])
        lists = self.h.get("/lists").json()
        self.assertEqual(
            [(x["name"], x["kind"], x["active"], x["total"]) for x in lists],
            [("Blind 75", "bundled", True, 75)],
        )
        again = self.h.post("/setup", {"questions_per_day": 2, "download_bank": False})
        self.assertEqual(
            (again.status_code, again.json()["error"]["code"]), (409, "CONFLICT")
        )

    def test_setup_starts_the_bank_download(self) -> None:
        service = install_fake_bank(self.h)
        self.h.post("/setup", {"questions_per_day": 2, "download_bank": True})
        service.join(30)
        bank = self.h.get("/bank").json()
        self.assertEqual(bank["status"], "done", bank)
        self.assertGreater(bank["problems"], 50)
        self.assertGreater(bank["estimated"], 0)
        self.assertTrue(bank["method"].startswith("ridge-v1"))
        self.assertIsNotNone(bank["fetched_at"])


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_defaults_and_changes(self) -> None:
        settings = self.h.get("/settings").json()
        self.assertEqual(
            {
                k: settings[k]
                for k in (
                    "questions_per_day",
                    "atcoder_per_day",
                    "target_rating",
                    "include_paid_only",
                )
            },
            {
                "questions_per_day": 2,
                "atcoder_per_day": 0,
                "target_rating": 1850,
                "include_paid_only": False,
            },
        )
        self.assertEqual(settings["bank"]["status"], "never")
        changed = self.h.patch(
            "/settings",
            {"target_rating": 1900, "atcoder_per_day": 2, "include_paid_only": True},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(
            (
                changed.json()["target_rating"],
                changed.json()["atcoder_per_day"],
                changed.json()["include_paid_only"],
            ),
            (1900, 2, True),
        )
        # null leaves a setting alone
        self.assertEqual(
            self.h.patch("/settings", {"target_rating": None}).json()["target_rating"],
            1900,
        )

    def test_ranges(self) -> None:
        for body in (
            {"target_rating": 1910},
            {"target_rating": 1150},
            {"questions_per_day": 0},
            {"questions_per_day": 21},
            {"atcoder_per_day": 11},
            {"timezone": "UTC"},
        ):
            with self.subTest(body=body):
                response = self.h.patch("/settings", body)
                self.assertEqual(
                    (response.status_code, response.json()["error"]["code"]),
                    (422, "VALIDATION"),
                )


class BankTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_refresh_in_the_background(self) -> None:
        service = install_fake_bank(self.h)
        started = self.h.post("/bank/refresh").json()
        self.assertIn(started["status"], ("running", "done"))
        service.join(30)
        done = self.h.get("/bank").json()
        self.assertEqual(done["status"], "done", done)
        self.assertIsInstance(done["unknown_tags"], list)
        self.assertEqual(self.h.get("/settings").json()["bank"]["status"], "done")


class BackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_backup_now(self) -> None:
        self.assertEqual(
            self.h.get("/backup").json(),
            {"last_backup_at": None, "path": None, "kept": 0},
        )
        taken = self.h.post("/backup").json()
        self.assertEqual(taken["kept"], 1)
        self.assertEqual(taken["last_backup_at"], "2026-11-08T09:00:00Z")
        self.assertTrue(taken["path"].endswith(".sqlite"))
        self.assertEqual(
            self.h.get("/settings").json()["last_backup_at"], "2026-11-08T09:00:00Z"
        )


class TutorTest(unittest.TestCase):
    def test_status_and_connection(self) -> None:
        h = make_harness()
        self.addCleanup(h.close)
        status = h.get("/tutor/status").json()
        self.assertEqual(
            status,
            {
                "enabled": True,
                "provider": "ollama",
                "model": "qwen3.6:35b",
                "leaves_machine": False,
                "pending_reports": 0,
            },
        )
        h.script.append('{"ok": "yes"}')
        ok = h.post("/tutor/test").json()
        self.assertTrue(ok["ok"], ok)
        self.assertIsNotNone(ok["latency_ms"])
        h.script.append(ConnectionError("refused"))
        down = h.post("/tutor/test").json()
        self.assertEqual((down["ok"], down["error_kind"]), (False, "unavailable"))

    def test_off(self) -> None:
        h = make_harness(config_yaml="tutor:\n  enabled: false\n")
        self.addCleanup(h.close)
        self.assertFalse(h.get("/tutor/status").json()["enabled"])
        off = h.post("/tutor/test").json()
        self.assertEqual((off["ok"], off["error_kind"]), (False, "disabled"))
        self.assertEqual(h.chats, [])

    def test_cloud_providers_leave_the_machine(self) -> None:
        h = make_harness(
            config_yaml="tutor:\n  default:\n    provider: openai\n    model: gpt-test\n"
        )
        self.addCleanup(h.close)
        self.assertTrue(h.get("/tutor/status").json()["leaves_machine"])


if __name__ == "__main__":
    unittest.main()
