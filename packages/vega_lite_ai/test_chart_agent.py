"""The agent's setup and bookkeeping, with `query` replaced: no model, no network, no money."""

import asyncio
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest import mock

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from packages.vega_lite_ai import chart_agent
from packages.vega_lite_ai.chart_agent import (
    NOT_CHECKED,
    build_options,
    build_report,
    record_message,
    run_agent,
    run_status,
)
from packages.vega_lite_ai.chart_tools import RunState, fingerprint
from packages.vega_lite_ai.runs import (
    CHART,
    DATA,
    EXTRACT,
    MAX_BUDGET_USD,
    RAW,
    read_events,
    read_report,
)


def result_message(**fields: Any) -> ResultMessage:
    values: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1000,
        "duration_api_ms": 900,
        "is_error": False,
        "num_turns": 3,
        "session_id": "s",
        "total_cost_usd": 0.5,
        "model_usage": {"claude-opus-5-5": {}},
        "structured_output": {"dataset": "推計人口"},
        **fields,
    }
    return ResultMessage(**values)


class AgentTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.run_dir = Path(folder.name)
        self.state = RunState(self.run_dir)

    def pass_gate(self) -> None:
        (self.run_dir / RAW).mkdir()
        for name in (DATA, EXTRACT, CHART):
            (self.run_dir / name).write_text("x", encoding="utf-8")
        self.state.passed = fingerprint(self.run_dir)


class OptionsTest(AgentTestCase):
    def test_takes_nothing_from_the_users_claude_setup(self) -> None:
        self.assertEqual(build_options(self.state).setting_sources, [])

    def test_bash_is_sandboxed_with_no_way_out(self) -> None:
        sandbox = build_options(self.state).sandbox or {}
        self.assertTrue(sandbox.get("enabled"))
        self.assertIs(sandbox.get("allowUnsandboxedCommands"), False)
        self.assertNotIn("network", sandbox)

    def test_there_is_no_web_search(self) -> None:
        tools = build_options(self.state).tools
        self.assertIsInstance(tools, list)
        self.assertNotIn("WebSearch", tools or [])

    def test_only_finder_gets_web_tools(self) -> None:
        agents = build_options(self.state).agents or {}
        self.assertEqual(agents["finder"].tools, ["WebFetch"])
        self.assertEqual(agents["finder"].model, chart_agent.FINDER_MODEL)

    def test_finder_runs_in_the_foreground(self) -> None:
        env = build_options(self.state).env
        self.assertEqual(env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"], "1")

    def test_works_in_the_run_folder_with_a_spending_limit(self) -> None:
        options = build_options(self.state)
        self.assertEqual(options.cwd, self.run_dir)
        self.assertEqual(options.max_budget_usd, MAX_BUDGET_USD)
        self.assertEqual(options.max_turns, chart_agent.MAX_TURNS)

    def test_the_gate_and_the_tools_are_wired_in(self) -> None:
        options = build_options(self.state)
        self.assertEqual(set(options.hooks or {}), {"PreToolUse", "Stop"})
        self.assertEqual(set(options.mcp_servers), {"chart"})  # type: ignore[arg-type]
        self.assertIn("mcp__chart__submit_chart", options.allowed_tools)


class RecordMessageTest(AgentTestCase):
    def test_logs_tool_calls_and_who_made_them(self) -> None:
        record_message(
            self.run_dir,
            AssistantMessage(
                content=[
                    TextBlock("探します"),
                    ToolUseBlock(
                        "1", "mcp__chart__download_file", {"url": "https://a/b"}
                    ),
                ],
                model="m",
                parent_tool_use_id="parent",
            ),
        )
        text, tool = read_events(self.run_dir)
        self.assertEqual((text["kind"], text["who"]), ("text", "finder"))
        self.assertEqual(tool["name"], "download_file")
        self.assertEqual(tool["detail"], "https://a/b")

    def test_the_main_agent_has_no_parent(self) -> None:
        record_message(
            self.run_dir,
            AssistantMessage(
                content=[ToolUseBlock("1", "Bash", {"command": "ls"})], model="m"
            ),
        )
        self.assertEqual(read_events(self.run_dir)[0]["who"], "main")

    def test_ignores_blank_text_and_other_messages(self) -> None:
        record_message(
            self.run_dir, AssistantMessage(content=[TextBlock("  ")], model="m")
        )
        record_message(self.run_dir, result_message())
        self.assertEqual(read_events(self.run_dir), [])


class StatusTest(AgentTestCase):
    def test_a_passed_chart_counts(self) -> None:
        self.pass_gate()
        self.assertEqual(run_status(self.state, stopped=False), "chart")

    def test_giving_up_wins_even_after_a_pass(self) -> None:
        self.pass_gate()
        self.state.gave_up = "reason"
        self.assertEqual(run_status(self.state, stopped=False), "no_chart")

    def test_a_chart_changed_after_passing_does_not_count(self) -> None:
        self.pass_gate()
        (self.run_dir / DATA).write_text("changed", encoding="utf-8")
        self.assertEqual(run_status(self.state, stopped=False), "failed")

    def test_no_chart_at_all(self) -> None:
        self.assertEqual(run_status(self.state, stopped=False), "failed")
        self.assertEqual(run_status(self.state, stopped=True), "stopped")


class ReportTest(AgentTestCase):
    def test_keeps_what_code_saw_apart_from_what_the_model_said(self) -> None:
        self.pass_gate()
        self.state.downloads.append({"url": "https://a/b", "sha256": "abc"})
        self.state.gate_failures = 2
        report = build_report(
            self.state,
            "人口",
            result_message(permission_denials=[{"tool_name": "Edit"}]),
            stopped=False,
            error=None,
        )
        recorded = report["recorded"]
        self.assertEqual(report["status"], "chart")
        self.assertEqual(recorded["sources"], self.state.downloads)
        self.assertEqual(recorded["gate_failures"], 2)
        self.assertEqual(recorded["permission_denials"], [{"tool_name": "Edit"}])
        self.assertEqual(recorded["cost_usd"], 0.5)
        self.assertEqual(recorded["models"], ["claude-opus-5-5"])
        self.assertEqual(report["agent"], {"dataset": "推計人口"})

    def test_always_says_what_the_gate_does_not_prove(self) -> None:
        report = build_report(self.state, "人口", None, stopped=False, error=None)
        self.assertEqual(report["recorded"]["not_checked"], list(NOT_CHECKED))

    def test_a_run_with_no_result_still_reports(self) -> None:
        report = build_report(self.state, "人口", None, stopped=False, error="boom")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error"], "boom")
        self.assertIsNone(report["agent"])
        self.assertIsNone(report["recorded"]["cost_usd"])


class RunAgentTest(AgentTestCase):
    async def run_with(self, messages: list[Any], failure: Exception | None) -> int:
        async def fake_query(**_kwargs: Any) -> AsyncIterator[Any]:
            for message in messages:
                yield message
            if failure is not None:
                raise failure

        with mock.patch.object(chart_agent, "query", fake_query):
            return await run_agent("人口", self.run_dir)

    async def test_a_run_with_no_chart_exits_non_zero_with_a_report(self) -> None:
        code = await self.run_with([result_message()], None)
        self.assertEqual(code, 1)
        report = read_report(self.run_dir)
        self.assertEqual(report and report["status"], "failed")
        self.assertEqual(read_events(self.run_dir)[-1]["kind"], "finished")

    async def test_hitting_a_limit_keeps_the_result_for_the_report(self) -> None:
        code = await self.run_with(
            [result_message(subtype="error_max_budget_usd", is_error=True)],
            ClaudeSDKError("over budget"),
        )
        self.assertEqual(code, 1)
        report = read_report(self.run_dir) or {}
        self.assertEqual(report["recorded"]["result"], "error_max_budget_usd")
        self.assertEqual(report["error"], "over budget")

    async def test_being_stopped_still_writes_a_report(self) -> None:
        started = asyncio.Event()

        async def fake_query(**_kwargs: Any) -> AsyncIterator[Any]:
            started.set()
            await asyncio.Event().wait()
            yield result_message()

        with mock.patch.object(chart_agent, "query", fake_query):
            task = asyncio.create_task(run_agent("人口", self.run_dir))
            await started.wait()
            task.cancel()
            self.assertEqual(await task, 1)
        report = read_report(self.run_dir)
        self.assertEqual(report and report["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
