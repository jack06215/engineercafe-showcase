"""The run folder, which is the whole interface between the agent process and the app."""

import os
import signal
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from packages.vega_lite_ai import runs
from packages.vega_lite_ai.runs import (
    EVENTS,
    PID,
    REPORT,
    RunError,
    active_run,
    append_event,
    is_running,
    list_runs,
    new_run_dir,
    output_root,
    read_events,
    read_report,
    run_topic,
    start_run,
    stop_run,
    write_pid,
    write_report,
)

# A process that can't be running: pid_max on macOS and Linux is far below this.
DEAD_PID = 2**31 - 1


class RunFolderTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def make_run(self, name: str, *, pid: int | None = None) -> Path:
        run_dir = self.root / name
        run_dir.mkdir()
        append_event(run_dir, "started", topic=name)
        if pid is not None:
            write_pid(run_dir, pid)
        return run_dir


class EventsTest(RunFolderTest):
    def test_events_come_back_in_order(self) -> None:
        run_dir = self.make_run("a")
        append_event(run_dir, "tool", name="Bash", detail="日本語")
        events = read_events(run_dir)
        self.assertEqual([event["kind"] for event in events], ["started", "tool"])
        self.assertEqual(events[1]["detail"], "日本語")
        self.assertIn("at", events[1])

    def test_a_half_written_line_is_skipped(self) -> None:
        run_dir = self.make_run("a")
        with (run_dir / EVENTS).open("a", encoding="utf-8") as file:
            file.write('{"kind": "to')
        self.assertEqual([event["kind"] for event in read_events(run_dir)], ["started"])

    def test_a_folder_with_no_events_reads_as_empty(self) -> None:
        self.assertEqual(read_events(self.root), [])

    def test_the_topic_comes_from_the_start_event(self) -> None:
        self.assertEqual(run_topic(self.make_run("人口の推移")), "人口の推移")
        self.assertEqual(run_topic(self.root), "")


class ReportTest(RunFolderTest):
    def test_round_trip(self) -> None:
        self.assertIsNone(read_report(self.root))
        write_report(self.root, {"status": "chart", "topic": "人口"})
        self.assertEqual(read_report(self.root), {"status": "chart", "topic": "人口"})
        self.assertEqual(
            [path.name for path in self.root.iterdir()], [REPORT], "no temporary file"
        )


class RunningTest(RunFolderTest):
    def test_a_live_process_with_no_report_is_running(self) -> None:
        self.assertTrue(is_running(self.make_run("a", pid=os.getpid())))

    def test_a_report_means_it_ended_even_if_the_pid_is_alive(self) -> None:
        run_dir = self.make_run("a", pid=os.getpid())
        write_report(run_dir, {"status": "chart"})
        self.assertFalse(is_running(run_dir))

    def test_a_dead_process_is_not_running(self) -> None:
        self.assertFalse(is_running(self.make_run("a", pid=DEAD_PID)))

    def test_a_folder_with_no_pid_is_not_running(self) -> None:
        self.assertFalse(is_running(self.make_run("a")))

    def test_a_damaged_pid_file_is_not_running(self) -> None:
        run_dir = self.make_run("a")
        (run_dir / PID).write_text("not a number", encoding="utf-8")
        self.assertFalse(is_running(run_dir))


class ListingTest(RunFolderTest):
    def test_lists_only_run_folders_newest_first(self) -> None:
        older = self.make_run("20261101-100000")
        newer = self.make_run("20261101-110000")
        (self.root / "fukuoka_population.html").write_text("old", encoding="utf-8")
        (self.root / "not_a_run").mkdir()
        self.assertEqual(list_runs(self.root), [newer, older])

    def test_a_missing_output_folder_is_just_no_runs(self) -> None:
        self.assertEqual(list_runs(self.root / "nowhere"), [])

    def test_finds_the_run_in_progress(self) -> None:
        self.make_run("20261101-100000", pid=DEAD_PID)
        running = self.make_run("20261101-110000", pid=os.getpid())
        self.assertEqual(active_run(self.root), running)

    def test_no_active_run_when_all_have_ended(self) -> None:
        self.make_run("20261101-100000", pid=DEAD_PID)
        self.assertIsNone(active_run(self.root))


class StartTest(RunFolderTest):
    def test_starts_the_agent_and_records_it(self) -> None:
        with mock.patch.object(runs.subprocess, "Popen") as popen:
            popen.return_value.pid = os.getpid()
            popen.return_value.wait.return_value = 0
            run_dir = start_run(self.root, "人口の推移")
        command = popen.call_args.args[0]
        self.assertEqual(command[1:3], ["-m", runs.AGENT_MODULE])
        self.assertEqual(command[3:], ["--run-dir", str(run_dir), "人口の推移"])
        self.assertEqual(run_topic(run_dir), "人口の推移")
        self.assertTrue(is_running(run_dir))

    def test_refuses_a_second_run_at_the_same_time(self) -> None:
        self.make_run("20261101-100000", pid=os.getpid())
        with (
            mock.patch.object(runs.subprocess, "Popen") as popen,
            self.assertRaises(RunError),
        ):
            start_run(self.root, "人口の推移")
        popen.assert_not_called()

    def test_stop_signals_the_agent(self) -> None:
        run_dir = self.make_run("a", pid=12345)
        with mock.patch.object(runs.os, "kill") as kill:
            stop_run(run_dir)
        kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_stopping_a_run_that_already_ended_is_harmless(self) -> None:
        stop_run(self.make_run("a", pid=DEAD_PID))
        stop_run(self.make_run("b"))


class PathsTest(unittest.TestCase):
    def test_output_goes_in_the_source_tree_not_runfiles(self) -> None:
        with mock.patch.dict(os.environ, {"BUILD_WORKSPACE_DIRECTORY": "/repo"}):
            self.assertEqual(
                output_root(),
                Path("/repo/packages/vega_lite_ai/output"),
            )

    def test_outside_bazel_run_it_says_what_to_do(self) -> None:
        with (
            mock.patch.dict(os.environ, clear=True),
            self.assertRaisesRegex(RunError, "bazel run"),
        ):
            output_root()

    def test_new_run_dir_makes_the_output_folder_too(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            run_dir = new_run_dir(Path(folder) / "output")
            self.assertTrue(run_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
