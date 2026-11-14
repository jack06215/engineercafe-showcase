import contextlib
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from packages.algo_tutor import serve
from packages.algo_tutor.cli import build_parser, run_cli
from packages.algo_tutor.store.backups import list_backups

HERE = Path(__file__).parent
PACK = {
    "version": 2,
    "name": "Tessoku",
    "source": "atcoder",
    "questions": [
        {
            "url": "https://atcoder.jp/contests/tessoku-book/tasks/tessoku_book_a",
            "title": "A",
        }
    ],
}


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "repo/packages/algo_tutor").mkdir(parents=True)
        shutil.copy(
            HERE / "config.yaml", self.root / "repo/packages/algo_tutor/config.yaml"
        )
        self.data = self.root / "data"
        self.pack = self.root / "pack.json"
        self.pack.write_text(json.dumps(PACK))

    def tearDown(self) -> None:
        self.folder.cleanup()

    def run_cli(self, *argv: str) -> str:
        args = build_parser().parse_args(
            [
                "--repo-root",
                str(self.root / "repo"),
                "--data-dir",
                str(self.data),
                *argv,
            ]
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run_cli(args)
        return out.getvalue()

    def test_import_pack_dry_run_then_apply_then_replay(self) -> None:
        self.assertIn(
            "Would add 1 problem(s)",
            self.run_cli("import-pack", "--dry-run", str(self.pack)),
        )
        self.assertIn("Added 1 problem(s)", self.run_cli("import-pack", str(self.pack)))
        self.assertIn("Already imported", self.run_cli("import-pack", str(self.pack)))
        with contextlib.closing(sqlite3.connect(self.data / "algo_tutor.sqlite")) as db:
            self.assertEqual(
                db.execute("SELECT name, kind FROM lists").fetchall(),
                [("Tessoku", "pack")],
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM topics").fetchone(), (34,)
            )

    def test_a_bad_pack_exits_before_opening_the_database(self) -> None:
        self.pack.write_text(json.dumps(PACK | {"version": 1}))
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("import-pack", str(self.pack))
        self.assertIn("version", str(caught.exception.code))
        self.assertFalse(self.data.exists())

    def test_backup(self) -> None:
        self.assertIn("Backed up to", self.run_cli("backup"))
        self.assertEqual(len(list_backups(self.data / "backups")), 1)

    def test_a_bad_config_exits_with_the_key(self) -> None:
        bad = self.root / "bad.yaml"
        bad.write_text("server:\n  port: 0\n")
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("--config", str(bad), "backup")
        self.assertIn("server.port", str(caught.exception.code))


class ServeTest(CliTest):
    def test_serve_backs_up_and_runs_the_app_on_loopback(self) -> None:
        with (
            mock.patch("uvicorn.run") as run,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            self.run_cli("serve", "--port", "4999")
        app = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs, {"host": "127.0.0.1", "port": 4999})
        # The local-only guard checks the port actually served.
        client = TestClient(app, base_url="http://127.0.0.1:4999")
        self.assertEqual(client.get("/api/health").json(), {"status": "ok"})
        self.assertIn("backed up to", err.getvalue())
        self.assertEqual(len(list_backups(self.data / "backups")), 1)

    def test_serve_refuses_a_public_host(self) -> None:
        with mock.patch("uvicorn.run") as run, self.assertRaises(SystemExit) as caught:
            self.run_cli("serve", "--host", "0.0.0.0")
        self.assertIn("loopback", str(caught.exception.code))
        run.assert_not_called()

    def test_serve_entry_point_takes_every_flag(self) -> None:
        argv = [
            "serve",
            "--repo-root",
            str(self.root / "repo"),
            "--data-dir",
            str(self.data),
            "--port",
            "4998",
        ]
        with (
            mock.patch("sys.argv", argv),
            mock.patch("uvicorn.run") as run,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            serve.main()
        self.assertEqual(run.call_args.kwargs["port"], 4998)


if __name__ == "__main__":
    unittest.main()
