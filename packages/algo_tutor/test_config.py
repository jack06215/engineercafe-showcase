import tempfile
import unittest
from pathlib import Path

from packages.algo_tutor.config import ConfigError, load_config, merge
from packages.algo_tutor.paths import PathsError, resolve_paths

COMMITTED = Path(__file__).parent / "config.yaml"


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.dir = Path(self.folder.name)

    def tearDown(self) -> None:
        self.folder.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text)
        return path

    def test_the_committed_defaults(self) -> None:
        config = load_config([COMMITTED])
        self.assertEqual((config.server.host, config.server.port), ("127.0.0.1", 4317))
        self.assertTrue(config.tutor.enabled)
        report = config.tutor.task("report")
        self.assertEqual(
            (report.provider, report.model, report.reasoning, report.timeout_s),
            ("ollama", "qwen3.6:35b", True, 180),
        )
        hint = config.tutor.task("hint")
        self.assertEqual(
            (hint.reasoning, hint.timeout_s, hint.temperature), (False, 90, 0)
        )

    def test_local_file_merges_key_by_key_and_may_be_missing(self) -> None:
        local = self.write(
            "local.yaml",
            "tutor:\n  default:\n    model: llama9\n  tasks:\n    hint: {provider: openai}\n",
        )
        config = load_config([COMMITTED, local])
        self.assertEqual(config.tutor.default.model, "llama9")
        self.assertEqual(config.tutor.default.provider, "ollama")
        self.assertEqual(config.tutor.task("hint").provider, "openai")
        self.assertEqual(
            config.tutor.task("hint").timeout_s, 90
        )  # kept from config.yaml
        self.assertEqual(
            load_config([COMMITTED, self.dir / "absent.yaml"]).server.port, 4317
        )

    def test_errors_name_the_key(self) -> None:
        cases = {
            "server:\n  hots: 1\n": "server.hots: unknown key",
            "tutor:\n  default:\n    provider: claude\n": "tutor.default.provider",
            "tutor:\n  tasks:\n    plan: {}\n": "tutor.tasks.plan",
            "server:\n  host: 0.0.0.0\n": "not a loopback address",
            "server:\n  port: 99999\n": "server.port",
            "- just a list\n": "top level must be a mapping",
            "server: [\n": "not valid YAML",
        }
        for text, fragment in cases.items():
            with self.subTest(text=text), self.assertRaisesRegex(ConfigError, fragment):
                load_config([self.write("bad.yaml", text)])
        with self.assertRaisesRegex(ConfigError, "can't read"):
            load_config([self.dir / "missing.yaml"])

    def test_localhost_and_ipv6_loopback_are_allowed(self) -> None:
        for host in ("localhost", "::1", "127.0.0.2"):
            with self.subTest(host=host):
                self.assertEqual(
                    load_config(
                        [self.write("c.yaml", f"server:\n  host: '{host}'\n")]
                    ).server.host,
                    host,
                )

    def test_merge(self) -> None:
        self.assertEqual(
            merge({"a": {"b": 1, "c": 2}, "d": 1}, {"a": {"c": 3}, "e": 4}),
            {"a": {"b": 1, "c": 3}, "d": 1, "e": 4},
        )


class PathsTest(unittest.TestCase):
    def test_repo_root_from_bazel_run(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            paths = resolve_paths(environ={"BUILD_WORKSPACE_DIRECTORY": str(root)})
            self.assertEqual(paths.repo_root, root)
            self.assertEqual(paths.data_dir, root / "packages/algo_tutor/.data")
            self.assertEqual(
                paths.database, root / "packages/algo_tutor/.data/algo_tutor.sqlite"
            )
            self.assertEqual(
                paths.bank_file,
                root / "packages/algo_tutor/.data/bank/leetcode-bank.json",
            )
            self.assertEqual(
                paths.config_files,
                (
                    root / "packages/algo_tutor/config.yaml",
                    root / "packages/algo_tutor/config.local.yaml",
                ),
            )

    def test_flags_override(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            paths = resolve_paths(root, root / "data", root / "c.yaml", environ={})
            self.assertEqual(
                (paths.data_dir, paths.config_files),
                (root / "data", (root / "c.yaml",)),
            )

    def test_no_repo_root_names_both_ways(self) -> None:
        with self.assertRaisesRegex(
            PathsError, r"--repo-root.*\$BUILD_WORKSPACE_DIRECTORY"
        ):
            resolve_paths(environ={})


if __name__ == "__main__":
    unittest.main()
