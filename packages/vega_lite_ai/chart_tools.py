"""The chart agent's tools and guards: what it can reach, and what has to pass before it can stop.

Nothing here needs a model, so the tests call these functions directly. The tools run in this process,
outside the agent's Bash sandbox, so none of them executes anything the agent wrote.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
import pandas
import pydantic
from claude_agent_sdk import (
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    McpSdkServerConfig,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk.types import HookEvent

from packages.vega_lite_ai.runs import (
    CHART,
    DATA,
    EXTRACT,
    RAW,
    append_event,
)
from packages.vega_lite_chat.chart_spec import ChartSpec
from packages.vega_lite_chat.checks import check_chart
from packages.vega_lite_chat.compiler import (
    compile_chart,
    vega_lite_errors,
    with_inline_data,
)
from packages.vega_lite_chat.csv_loader import (
    InputError,
    load_csv,
)
from packages.vega_lite_chat.profile import profile_frame

# Subdomains count. The one list decides both what `finder` can read and what can be downloaded.
ALLOWED_HOSTS = ("bodik.jp", "city.fukuoka.lg.jp")
SERVER_NAME = "chart"
TOOL_NAMES = tuple(
    f"mcp__{SERVER_NAME}__{name}"
    for name in ("download_file", "submit_chart", "report_no_chart")
)
# The tool the CLI adds for `output_format`.
STRUCTURED_OUTPUT_TOOL = "StructuredOutput"

CHART_HEIGHT = 400
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_REDIRECTS = 5
DOWNLOAD_TIMEOUT_SECONDS = 60.0
# A percent-decoded name can hold anything; it only has to be recognisable and stay inside raw/.
_UNSAFE_NAME = re.compile(r"[^\w.-]+")
# Rules out what URL parsers disagree on: `http://evil.example\.city.fukuoka.lg.jp` ends in an allowed
# name for urlsplit, and a client may well connect to evil.example.
_HOST_NAME = re.compile(r"[a-z0-9.-]+")


class DownloadError(RuntimeError):
    """A file couldn't be downloaded. The message goes back to the model."""


@dataclass
class RunState:
    """What this run has done, kept in code so that neither the gate nor the report takes the model's word."""

    run_dir: Path
    downloads: list[dict[str, Any]] = field(default_factory=list)
    passed: dict[str, str] | None = None  # the checked files' hashes
    gave_up: str | None = None
    gate_failures: int = 0
    reported: bool = False  # the gate let the agent's final report through


def url_problem(url: str) -> str | None:
    """Why this URL is off limits, or None when it may be used."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return f"{url} is not a valid URL"
    host = (parts.hostname or "").lower()
    allowed = _HOST_NAME.fullmatch(host) is not None and any(
        host == name or host.endswith(f".{name}") for name in ALLOWED_HOSTS
    )
    if parts.scheme not in ("http", "https") or not allowed:
        return f"{url} is off limits; only {', '.join(ALLOWED_HOSTS)} can be reached"
    return None


def web_denial(
    tool_name: str, tool_input: dict[str, Any], agent_id: str | None
) -> str | None:
    """Why this web tool call must be refused: only `finder` browses, and only the allowed hosts."""
    if agent_id is None:
        return f"{tool_name} is only for the finder subagent; delegate the search to it"
    return url_problem(str(tool_input.get("url", "")))


def _file_name(url: str, index: int) -> str:
    name = _UNSAFE_NAME.sub("_", Path(unquote(urlsplit(url).path)).name).strip("._")
    return f"{index:02d}_{name or 'download'}"


async def download_file(
    state: RunState, url: str, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    """Save `url` under raw/ and record where it came from. Every redirect has to stay on the allowlist."""
    current = url
    try:
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS, transport=transport
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                problem = url_problem(current)
                if problem is not None:
                    raise DownloadError(problem)
                async with client.stream("GET", current) as response:
                    if response.is_redirect:
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code != httpx.codes.OK:
                        raise DownloadError(
                            f"{current} answered {response.status_code}"
                        )
                    return await _save(state, url, current, response)
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise DownloadError(f"{current} could not be downloaded: {error}") from error
    raise DownloadError(f"{url} redirected more than {MAX_REDIRECTS} times")


async def _save(
    state: RunState, url: str, final_url: str, response: httpx.Response
) -> dict[str, Any]:
    raw = state.run_dir / RAW
    raw.mkdir(exist_ok=True)
    path = raw / _file_name(final_url, len(state.downloads) + 1)
    digest = hashlib.sha256()
    size = 0
    with path.open("wb") as file:
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                file.close()
                path.unlink()
                raise DownloadError(f"{url} is over {MAX_DOWNLOAD_BYTES} bytes")
            digest.update(chunk)
            file.write(chunk)
    record = {
        "url": url,
        "final_url": final_url,
        "file": path.relative_to(state.run_dir).as_posix(),
        "bytes": size,
        "sha256": digest.hexdigest(),
    }
    state.downloads.append(record)
    return record


def chart_input_schema() -> dict[str, Any]:
    """`ChartSpec`'s schema without the two fields `submit_chart` refuses, so the model isn't offered them."""
    schema = ChartSpec.model_json_schema()
    return {
        **schema,
        "properties": {
            name: value
            for name, value in schema["properties"].items()
            if name not in ("filters", "top_n")
        },
        "$defs": {
            name: value
            for name, value in schema["$defs"].items()
            if name not in ("Filter", "TopN")
        },
        "required": [name for name in schema["required"] if name != "filters"],
    }


def fingerprint(run_dir: Path) -> dict[str, str]:
    """A hash of every file a passed chart stands on, to notice one changing afterwards."""
    paths = [run_dir / name for name in (EXTRACT, DATA, CHART)]
    raw = run_dir / RAW
    if raw.exists():
        paths += sorted(raw.iterdir())
    return {
        path.relative_to(run_dir).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
        if path.exists()
    }


def _missing_files(run_dir: Path) -> list[str]:
    errors = []
    raw = run_dir / RAW
    if not raw.exists() or not any(raw.iterdir()):
        errors.append("raw/ is empty; fetch the source data with download_file first")
    for name in (EXTRACT, DATA):
        if not (run_dir / name).exists():
            errors.append(f"{name} is missing; write it in the working directory")
    return errors


def _empty_columns(spec: ChartSpec, df: pandas.DataFrame) -> list[str]:
    """A column with no values draws nothing, and every other check is happy with that."""
    names = {encoding.field for _, encoding in spec.encodings() if encoding.field}
    return [
        f"column `{name}` has no values, so the chart would be blank"
        for name in sorted(names)
        if df[name].notna().sum() == 0
    ]


def submit_chart(state: RunState, arguments: dict[str, Any]) -> list[str]:
    """Check the chart against data.csv and, if it passes, write it and record the hashes.

    Returns what has to be fixed; an empty list means the chart passed. The two refused fields are what
    keeps a blank chart out: `check_chart` looks at a filter's format, not at whether any row matches
    (a year of 2099 passes), so all filtering happens in extract.py and every row in data.csv gets drawn.
    """
    errors = _missing_files(state.run_dir)
    if errors:
        return errors
    try:
        spec = ChartSpec.model_validate(arguments)
    except pydantic.ValidationError as error:
        return [
            f"{'.'.join(str(part) for part in item['loc']) or '(root)'}: {item['msg']}"
            for item in error.errors()
        ]
    if spec.filters or spec.top_n is not None:
        return ["filters and top_n are not available; do that in extract.py instead"]
    try:
        df = load_csv((state.run_dir / DATA).read_bytes())
    except InputError as error:
        return [f"{DATA}: {error}"]
    profile = profile_frame(df, sample_rows=5, seed=0, max_listed_values=20)
    errors = check_chart(spec, profile) or _empty_columns(spec, df)
    if errors:
        return errors
    compiled = compile_chart(spec, profile, height=CHART_HEIGHT)
    errors = vega_lite_errors(compiled)
    if errors:
        return errors
    (state.run_dir / CHART).write_text(
        json.dumps(with_inline_data(compiled, df), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    state.passed = fingerprint(state.run_dir)
    return []


def stop_problem(state: RunState) -> str | None:
    """Why the agent may not stop yet, or None when it may."""
    if state.gave_up is not None:
        return None
    if state.passed is None:
        return (
            "No chart has passed yet. Call submit_chart, or report_no_chart if "
            "no suitable data exists."
        )
    if fingerprint(state.run_dir) != state.passed:
        return "Files changed after the chart passed. Call submit_chart again."
    return None


def finish_problem(state: RunState) -> str | None:
    """`stop_problem`, plus the report: the CLI asks for it only once, so ending the turn could skip it."""
    problem = stop_problem(state)
    if problem is None and not state.reported:
        return f"Finish by calling {STRUCTURED_OUTPUT_TOOL} with your report."
    return problem


def chart_server(state: RunState) -> McpSdkServerConfig:
    """The custom tools, bound to this run."""

    @tool(
        "download_file",
        "Save a file from BODIK or the Fukuoka City site under raw/. "
        "The only way to get a file: Bash has no network.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    )
    async def download(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            record = await download_file(state, str(arguments["url"]))
        except DownloadError as error:
            append_event(state.run_dir, "download_failed", message=str(error))
            return _text(str(error), is_error=True)
        append_event(state.run_dir, "download", url=record["url"], file=record["file"])
        return _text(json.dumps(record, ensure_ascii=False))

    @tool(
        "submit_chart",
        "Check the chart against data.csv. The run can't end until this passes. "
        "Any failure says what to fix; fix it and call again.",
        chart_input_schema(),
    )
    async def submit(arguments: dict[str, Any]) -> dict[str, Any]:
        errors = submit_chart(state, arguments)
        if errors:
            state.gate_failures += 1
            append_event(state.run_dir, "gate_failed", errors=errors)
            return _text("\n".join(errors), is_error=True)
        append_event(state.run_dir, "gate_passed")
        return _text("Passed. Now finish with the report.")

    @tool(
        "report_no_chart",
        "End the run without a chart, when no suitable data exists. Say why.",
        {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    )
    async def give_up(arguments: dict[str, Any]) -> dict[str, Any]:
        state.gave_up = str(arguments["reason"])
        append_event(state.run_dir, "no_chart", reason=state.gave_up)
        return _text("Recorded. Now finish with the report.")

    return create_sdk_mcp_server(SERVER_NAME, tools=[download, submit, give_up])


def _text(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": is_error}


def _deny(state: RunState, reason: str) -> HookJSONOutput:
    append_event(state.run_dir, "denied", reason=reason)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def chart_hooks(state: RunState) -> dict[HookEvent, list[HookMatcher]]:
    """The rules a prompt can't enforce: who may browse, and when the run may end.

    The gate sits in two places because the CLI gives a run two ways to end. A turn ending fires Stop,
    which can send the agent back to work. The `output_format` report ends the run outright, and a Stop
    block after it is ignored, so that report is refused until the gate is satisfied.
    """

    async def guard_web(
        hook_input: HookInput, _tool_use_id: str | None, _context: HookContext
    ) -> HookJSONOutput:
        if hook_input["hook_event_name"] != "PreToolUse":
            return {}
        reason = web_denial(
            hook_input["tool_name"],
            hook_input["tool_input"],
            hook_input.get("agent_id"),
        )
        return {} if reason is None else _deny(state, reason)

    async def gate_report(
        _hook_input: HookInput, _tool_use_id: str | None, _context: HookContext
    ) -> HookJSONOutput:
        reason = stop_problem(state)
        if reason is not None:
            return _deny(state, reason)
        state.reported = True
        return {}

    async def gate_stop(
        _hook_input: HookInput, _tool_use_id: str | None, _context: HookContext
    ) -> HookJSONOutput:
        reason = finish_problem(state)
        if reason is None:
            return {}
        append_event(state.run_dir, "stop_blocked", reason=reason)
        return {"decision": "block", "reason": reason}

    return {
        "PreToolUse": [
            HookMatcher(matcher="WebFetch|WebSearch", hooks=[guard_web]),
            HookMatcher(matcher=STRUCTURED_OUTPUT_TOOL, hooks=[gate_report]),
        ],
        "Stop": [HookMatcher(hooks=[gate_stop])],
    }
