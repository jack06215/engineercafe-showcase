"""The guards, with no model and no network: if these hold, the agent can't stop on a bad chart or roam."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import httpx
from claude_agent_sdk import HookInput

from packages.vega_lite_ai import chart_tools
from packages.vega_lite_ai.chart_tools import (
    DownloadError,
    RunState,
    chart_hooks,
    chart_input_schema,
    download_file,
    fingerprint,
    stop_problem,
    submit_chart,
    url_problem,
    web_denial,
)
from packages.vega_lite_ai.runs import CHART, DATA, EXTRACT, RAW
from packages.vega_lite_core.chart_spec import ChartSpec

CITY = "https://www.city.fukuoka.lg.jp"
LINE_CHART: dict[str, Any] = {
    "mark": "line",
    "title": "人口の推移",
    "x": {"field": "年", "type": "ordinal"},
    "y": {"field": "人口", "type": "quantitative"},
}


class UrlTest(unittest.TestCase):
    def test_allows_the_listed_hosts_and_their_subdomains(self) -> None:
        for url in (
            "https://data.bodik.jp/api/3/action/package_search",
            f"{CITY}/data/a.xlsx",
            "http://city.fukuoka.lg.jp/",
            "https://WWW.CITY.FUKUOKA.LG.JP/a",
        ):
            self.assertIsNone(url_problem(url), url)

    def test_refuses_everything_else(self) -> None:
        for url in (
            "https://evil.example/a.csv",
            "https://evilbodik.jp/a.csv",  # ends in the name, but isn't a subdomain
            "https://city.fukuoka.lg.jp.evil.example/a",
            "https://city.fukuoka.lg.jp@evil.example/a",
            "https://evil.example#.city.fukuoka.lg.jp",
            "https://evil.example\\.city.fukuoka.lg.jp/a",
            "ftp://city.fukuoka.lg.jp/a.csv",
            "file:///etc/passwd",
            "http://[broken",
            "",
        ):
            self.assertIsNotNone(url_problem(url), url)


class WebDenialTest(unittest.TestCase):
    def test_the_main_agent_may_not_browse_at_all(self) -> None:
        reason = web_denial("WebFetch", {"url": f"{CITY}/a"}, None)
        self.assertIn("finder", reason or "")

    def test_finder_may_browse_the_allowed_hosts(self) -> None:
        self.assertIsNone(web_denial("WebFetch", {"url": f"{CITY}/a"}, "agent-1"))

    def test_finder_is_kept_to_the_allowlist_too(self) -> None:
        self.assertIsNotNone(
            web_denial("WebFetch", {"url": "https://evil.example/"}, "agent-1")
        )


class DownloadTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.state = RunState(Path(folder.name))

    async def test_saves_the_file_and_records_where_it_came_from(self) -> None:
        def answer(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"data")

        url = f"{CITY}/%E4%BA%BA%E5%8F%A3.xlsx"
        record = await download_file(self.state, url, httpx.MockTransport(answer))
        self.assertEqual(record["file"], f"{RAW}/01_人口.xlsx")
        self.assertEqual(record["sha256"], hashlib.sha256(b"data").hexdigest())
        self.assertEqual(record["bytes"], 4)
        self.assertEqual((self.state.run_dir / record["file"]).read_bytes(), b"data")
        self.assertEqual(self.state.downloads, [record])

    async def test_a_url_with_no_usable_name_still_stays_in_raw(self) -> None:
        def answer(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"data")

        record = await download_file(
            self.state, f"{CITY}/a/..%2F..%2F..%2Fetc", httpx.MockTransport(answer)
        )
        path = (self.state.run_dir / record["file"]).resolve()
        self.assertTrue(path.is_relative_to(self.state.run_dir.resolve() / RAW))

    async def test_refuses_a_host_off_the_list_without_requesting_it(self) -> None:
        requested = []

        def answer(request: httpx.Request) -> httpx.Response:
            requested.append(request.url)
            return httpx.Response(200)

        with self.assertRaises(DownloadError):
            await download_file(
                self.state, "https://evil.example/a", httpx.MockTransport(answer)
            )
        self.assertEqual(requested, [])

    async def test_follows_a_redirect_that_stays_on_the_list(self) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/old.xlsx":
                return httpx.Response(302, headers={"location": "/new.xlsx"})
            return httpx.Response(200, content=b"data")

        record = await download_file(
            self.state, f"{CITY}/old.xlsx", httpx.MockTransport(answer)
        )
        self.assertEqual(record["url"], f"{CITY}/old.xlsx")
        self.assertEqual(record["final_url"], f"{CITY}/new.xlsx")

    async def test_refuses_a_redirect_off_the_list(self) -> None:
        requested = []

        def answer(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(
                302, headers={"location": "https://evil.example/a.xlsx"}
            )

        with self.assertRaisesRegex(DownloadError, "off limits"):
            await download_file(
                self.state, f"{CITY}/a.xlsx", httpx.MockTransport(answer)
            )
        self.assertEqual(requested, [f"{CITY}/a.xlsx"])
        self.assertEqual(self.state.downloads, [])

    async def test_gives_up_on_a_redirect_loop(self) -> None:
        def answer(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "/again"})

        with self.assertRaisesRegex(DownloadError, "redirected more than"):
            await download_file(self.state, f"{CITY}/a", httpx.MockTransport(answer))

    async def test_reports_an_error_status(self) -> None:
        def answer(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        with self.assertRaisesRegex(DownloadError, "404"):
            await download_file(self.state, f"{CITY}/a", httpx.MockTransport(answer))
        self.assertEqual(self.state.downloads, [])

    async def test_reports_a_connection_failure(self) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        with self.assertRaisesRegex(DownloadError, "no route"):
            await download_file(self.state, f"{CITY}/a", httpx.MockTransport(answer))

    async def test_drops_a_file_over_the_size_limit(self) -> None:
        def answer(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"12345")

        with (
            mock.patch.object(chart_tools, "MAX_DOWNLOAD_BYTES", 4),
            self.assertRaisesRegex(DownloadError, "over 4 bytes"),
        ):
            await download_file(self.state, f"{CITY}/a", httpx.MockTransport(answer))
        self.assertEqual(list((self.state.run_dir / RAW).iterdir()), [])
        self.assertEqual(self.state.downloads, [])


class SubmitChartTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.run_dir = Path(folder.name)
        self.state = RunState(self.run_dir)
        (self.run_dir / RAW).mkdir()
        (self.run_dir / RAW / "01_source.xlsx").write_bytes(b"source")
        (self.run_dir / EXTRACT).write_text("print('extract')", encoding="utf-8")
        self.write_csv("年,人口\n2024,1000\n2025,1100\n")

    def write_csv(self, text: str) -> None:
        (self.run_dir / DATA).write_text(text, encoding="utf-8")

    def test_a_good_chart_passes_and_is_written_with_its_data(self) -> None:
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        chart = json.loads((self.run_dir / CHART).read_text(encoding="utf-8"))
        self.assertEqual(chart["mark"]["type"], "line")
        self.assertEqual(chart["title"], "人口の推移")
        self.assertEqual(
            chart["data"]["values"],
            [{"年": 2024, "人口": 1000}, {"年": 2025, "人口": 1100}],
        )
        self.assertEqual(self.state.passed, fingerprint(self.run_dir))

    def test_says_which_files_are_missing(self) -> None:
        (self.run_dir / EXTRACT).unlink()
        (self.run_dir / DATA).unlink()
        (self.run_dir / RAW / "01_source.xlsx").unlink()
        errors = "\n".join(submit_chart(self.state, LINE_CHART))
        for name in ("raw/", EXTRACT, DATA):
            self.assertIn(name, errors)
        self.assertIsNone(self.state.passed)

    def test_an_unknown_column_comes_back_with_the_real_ones(self) -> None:
        chart = {**LINE_CHART, "y": {"field": "人", "type": "quantitative"}}
        errors = submit_chart(self.state, chart)
        self.assertEqual(len(errors), 1)
        self.assertIn("did you mean `人口`", errors[0])
        self.assertIsNone(self.state.passed)
        self.assertFalse((self.run_dir / CHART).exists())

    def test_a_malformed_chart_says_where(self) -> None:
        errors = submit_chart(self.state, {**LINE_CHART, "mark": "sparkle"})
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("mark:"), errors[0])

    def test_refuses_a_filter_even_one_that_would_blank_the_chart(self) -> None:
        chart = {
            **LINE_CHART,
            "filters": [{"field": "年", "op": "gt", "value": 2099}],
        }
        self.assertIn("extract.py", submit_chart(self.state, chart)[0])
        self.assertIsNone(self.state.passed)

    def test_refuses_top_n(self) -> None:
        chart = {**LINE_CHART, "top_n": {"field": "年", "by": "人口", "n": 1}}
        self.assertIn("extract.py", submit_chart(self.state, chart)[0])

    def test_refuses_a_column_with_no_values(self) -> None:
        self.write_csv("年,人口\n2024,\n2025,\n")
        self.assertIn("blank", submit_chart(self.state, LINE_CHART)[0])
        self.assertIsNone(self.state.passed)

    def test_refuses_a_csv_with_no_rows(self) -> None:
        self.write_csv("年,人口\n")
        self.assertTrue(submit_chart(self.state, LINE_CHART)[0].startswith(DATA))

    def test_refuses_a_csv_that_is_not_utf8(self) -> None:
        (self.run_dir / DATA).write_bytes("年,人口\n".encode("shift_jis"))
        self.assertTrue(submit_chart(self.state, LINE_CHART)[0].startswith(DATA))


class ChartSchemaTest(unittest.TestCase):
    def test_does_not_offer_the_refused_fields(self) -> None:
        schema = chart_input_schema()
        self.assertNotIn("filters", schema["properties"])
        self.assertNotIn("top_n", schema["properties"])
        self.assertNotIn("filters", schema["required"])
        self.assertNotIn("Filter", schema["$defs"])

    def test_still_defines_what_the_channels_refer_to(self) -> None:
        schema = chart_input_schema()
        self.assertIn("Encoding", schema["$defs"])
        self.assertEqual(schema["required"], ["mark"])

    def test_what_it_allows_still_validates(self) -> None:
        self.assertEqual(ChartSpec.model_validate(LINE_CHART).filters, [])


class GateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.run_dir = Path(folder.name)
        self.state = RunState(self.run_dir)
        (self.run_dir / RAW).mkdir()
        (self.run_dir / RAW / "01_source.xlsx").write_bytes(b"source")
        (self.run_dir / EXTRACT).write_text("print('extract')", encoding="utf-8")
        (self.run_dir / DATA).write_text("年,人口\n2025,1\n", encoding="utf-8")

    def test_blocks_until_a_chart_has_passed(self) -> None:
        self.assertIn("No chart", stop_problem(self.state) or "")
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        self.assertIsNone(stop_problem(self.state))

    def test_blocks_again_when_a_checked_file_changes(self) -> None:
        for name in (DATA, EXTRACT, CHART, f"{RAW}/01_source.xlsx"):
            with self.subTest(name):
                self.assertEqual(submit_chart(self.state, LINE_CHART), [])
                path = self.run_dir / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                self.assertIn("changed", stop_problem(self.state) or "")
                path.write_bytes(original)

    def test_a_new_download_after_passing_also_blocks(self) -> None:
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        (self.run_dir / RAW / "02_other.csv").write_bytes(b"other")
        self.assertIn("changed", stop_problem(self.state) or "")

    def test_submitting_again_after_a_change_clears_the_block(self) -> None:
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        (self.run_dir / DATA).write_text("年,人口\n2025,2\n", encoding="utf-8")
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        self.assertIsNone(stop_problem(self.state))

    def test_giving_up_is_an_honest_way_to_stop(self) -> None:
        self.state.gave_up = "合うデータがありません"
        self.assertIsNone(stop_problem(self.state))

    async def test_the_stop_hook_blocks_with_the_reason(self) -> None:
        hook = chart_hooks(self.state)["Stop"][0].hooks[0]
        stop_input: HookInput = {
            "hook_event_name": "Stop",
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "c",
            "stop_hook_active": False,
        }
        output = await hook(stop_input, None, {"signal": None})
        self.assertEqual(output.get("decision"), "block")
        self.assertIn("No chart", str(output.get("reason")))
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        output = await hook(stop_input, None, {"signal": None})
        self.assertEqual(output.get("decision"), "block")
        self.assertIn("report", str(output.get("reason")))
        self.state.reported = True
        self.assertEqual(await hook(stop_input, None, {"signal": None}), {})

    async def test_the_final_report_is_refused_until_the_gate_is_satisfied(
        self,
    ) -> None:
        matcher = chart_hooks(self.state)["PreToolUse"][1]
        self.assertEqual(matcher.matcher, "StructuredOutput")
        report: HookInput = {
            "hook_event_name": "PreToolUse",
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "c",
            "tool_name": "StructuredOutput",
            "tool_input": {},
            "tool_use_id": "u",
        }
        denied = await matcher.hooks[0](report, None, {"signal": None})
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"],  # type: ignore[typeddict-item]
            "deny",
        )
        self.assertEqual(submit_chart(self.state, LINE_CHART), [])
        self.assertEqual(await matcher.hooks[0](report, None, {"signal": None}), {})
        (self.run_dir / DATA).write_text("年,人口\n2025,9\n", encoding="utf-8")
        denied = await matcher.hooks[0](report, None, {"signal": None})
        self.assertIn("hookSpecificOutput", denied)

    async def test_the_web_hook_tells_finder_from_the_main_agent(self) -> None:
        matcher = chart_hooks(self.state)["PreToolUse"][0]
        self.assertEqual(matcher.matcher, "WebFetch|WebSearch")
        hook = matcher.hooks[0]
        fetch: HookInput = {
            "hook_event_name": "PreToolUse",
            "session_id": "s",
            "transcript_path": "t",
            "cwd": "c",
            "tool_name": "WebFetch",
            "tool_input": {"url": f"{CITY}/a"},
            "tool_use_id": "u",
        }
        denied = await hook(fetch, None, {"signal": None})
        specific = denied.get("hookSpecificOutput")
        self.assertIsNotNone(specific)
        self.assertEqual(
            specific and specific.get("permissionDecision"),  # type: ignore[union-attr]
            "deny",
        )
        allowed = await hook(
            {**fetch, "agent_id": "a", "agent_type": "finder"},  # type: ignore[typeddict-item]
            None,
            {"signal": None},
        )
        self.assertEqual(allowed, {})


if __name__ == "__main__":
    unittest.main()
