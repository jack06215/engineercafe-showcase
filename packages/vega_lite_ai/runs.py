"""A run folder: the only thing the agent process and the web app share.

`chart_agent` writes it and `ui` reads it, so the page can reload or restart without losing a run, and
the tests can check the app against folders that were written by hand.
"""

import datetime
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

EVENTS = "events.jsonl"
REPORT = "report.json"
CHART = "chart.vl.json"
DATA = "data.csv"
EXTRACT = "extract.py"
RAW = "raw"
PID = "pid"
LOG = "agent.log"

MAX_BUDGET_USD = 2.0  # here so the page can state it without importing the SDK
AGENT_MODULE = "packages.vega_lite_ai.chart_agent"
_OUTPUT = Path("packages/vega_lite_ai/output")
_RUN_NAME = "%Y%m%d-%H%M%S"


class RunError(RuntimeError):
    """A run can't start. The message is shown to the user as-is."""


def output_root() -> Path:
    """The source tree's output folder, which `bazel run` names; the working directory is runfiles."""
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        raise RunError("Start this with `bazel run`, or pass --run-dir.")
    return Path(workspace) / _OUTPUT


def new_run_dir(root: Path) -> Path:
    """Create and return a new timestamped run folder under *root*."""
    run_dir = root / datetime.datetime.now().strftime(_RUN_NAME)
    run_dir.mkdir(parents=True)
    return run_dir


def append_event(run_dir: Path, kind: str, **fields: Any) -> None:
    """Append one timestamped event to the run's event log."""
    event = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        **fields,
    }
    with (run_dir / EVENTS).open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    """Return the run's events, or an empty list if it has no event log."""
    path = run_dir / EVENTS
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:  # the agent is halfway through writing this line
            continue
    return events


def run_topic(run_dir: Path) -> str:
    """Return the topic recorded by the run's `started` event."""
    return next(
        (
            str(event.get("topic", ""))
            for event in read_events(run_dir)
            if event.get("kind") == "started"
        ),
        "",
    )


def write_report(run_dir: Path, report: dict[str, Any]) -> None:
    """Replace, not write in place: the app takes a report's existence to mean the run has ended."""
    temporary = run_dir / f"{REPORT}.tmp"
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(run_dir / REPORT)


def read_report(run_dir: Path) -> dict[str, Any] | None:
    """Return the run's report, or None if the run has not written one."""
    path = run_dir / REPORT
    if not path.exists():
        return None
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return report


def write_pid(run_dir: Path, pid: int) -> None:
    """Record the ID of the process that runs the agent for this run."""
    (run_dir / PID).write_text(str(pid), encoding="utf-8")


def is_running(run_dir: Path) -> bool:
    """Whether this run's agent process is still alive and hasn't reported."""
    if (run_dir / REPORT).exists():
        return False
    try:
        os.kill(int((run_dir / PID).read_text(encoding="utf-8")), 0)
    except FileNotFoundError, ValueError, ProcessLookupError:
        return False
    except PermissionError:  # alive, but owned by someone else
        return True
    return True


def list_runs(root: Path) -> list[Path]:
    """The run folders in `root`, newest first. The folder also holds files from older experiments."""
    if not root.exists():
        return []
    return sorted(
        (path for path in root.iterdir() if (path / EVENTS).exists()), reverse=True
    )


def active_run(root: Path) -> Path | None:
    """Return the first run under *root* whose process is still running."""
    return next((path for path in list_runs(root) if is_running(path)), None)


def start_run(root: Path, topic: str) -> Path:
    """Start the agent as a child process and return its run folder."""
    if active_run(root) is not None:
        raise RunError("実行中のものがあります。終わってから始めてください。")
    run_dir = new_run_dir(root)
    # Written here as well as by the agent, so the run counts as started before the child gets that far.
    append_event(run_dir, "started", topic=topic)
    with (run_dir / LOG).open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", AGENT_MODULE, "--run-dir", str(run_dir), topic],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    write_pid(run_dir, process.pid)
    # Reaps the child. An exited child nobody waits for stays a zombie, and looks alive to `is_running`.
    threading.Thread(target=process.wait, daemon=True).start()
    return run_dir


def stop_run(run_dir: Path) -> None:
    """Ask the agent to stop. It writes a `stopped` report on the way out."""
    try:
        os.kill(int((run_dir / PID).read_text(encoding="utf-8")), signal.SIGTERM)
    except FileNotFoundError, ValueError, ProcessLookupError:
        return
