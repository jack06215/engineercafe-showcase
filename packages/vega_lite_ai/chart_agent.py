"""An agent that turns a question about Fukuoka City's open data into one chart that passed a check.

`sample_code.py` is the baseline this improves on: there the agent decided for itself when it was done.
Here `submit_chart` has to pass before it can stop, and code rather than the model records what happened.
"""

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    Message,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from packages.vega_lite_ai.chart_tools import (
    SERVER_NAME,
    TOOL_NAMES,
    RunState,
    chart_hooks,
    chart_server,
    stop_problem,
)
from packages.vega_lite_ai.runs import (
    MAX_BUDGET_USD,
    append_event,
    new_run_dir,
    output_root,
    write_pid,
    write_report,
)

MODEL = "claude-opus-5-5"
FINDER_MODEL = "claude-haiku-5-5"
MAX_TURNS = 40
_DETAIL_LENGTH = 200
_TEXT_LENGTH = 500

SYSTEM_PROMPT = """\
あなたは福岡市のオープンデータから、質問に答えるグラフを 1 枚作るエージェントです。

手順:
1. データ探しは finder サブエージェントに任せます。あなたは WebFetch を使えません。
2. finder が見つけたファイルを download_file で取得します。ファイルは raw/ に保存されます。
3. raw/ のファイルを読み、整然形式の data.csv（UTF-8、1 行目が見出し）を出力する extract.py を
   Write で作業ディレクトリに書きます。実行は `$CHART_PYTHON extract.py` です。pandas と openpyxl が
   使えます。Python はコマンドに直接書かず、ファイルに書いて実行します。Bash からネットワークには
   接続できません。
4. data.csv を検算します（例: 男 + 女 = 人口、各区の合計 = 市の合計）。
5. submit_chart を呼びます。失敗したら、メッセージの指示どおりに直して、もう一度呼びます。

決まり:
- グラフは 1 枚だけです。区ごとに分けたいときは column か row を使います。
- 絞り込みはすべて extract.py で行います。data.csv の全行がグラフに描かれます。
- グラフの題名と軸の名前は日本語にします。
- 合うデータがないときは、無理に作らず report_no_chart を呼びます。
- 最後の報告は日本語で書きます。確かめていないことは、確かめていないと書きます。
"""

FINDER_PROMPT = """\
福岡市のオープンデータから、依頼に合うデータを探します。

BODIK の CKAN API から始めます。
https://data.bodik.jp/api/3/action/package_search?fq=organization:401307&rows=50&q=キーワード
リンク切れのときは www.city.fukuoka.lg.jp の該当ページをたどります。

候補ごとに、ファイルの URL、データ名、対象期間、選んだ理由を返します。より新しいファイルがあれば、
そちらを先に挙げます。ファイルの中身は読まなくて構いません。
"""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "dataset": {"type": "string", "description": "使ったデータの名前"},
        "why_this_dataset": {"type": "string", "description": "選んだ理由"},
        "columns_plotted": {"type": "array", "items": {"type": "string"}},
        "data_checks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "行った検算とその結果",
        },
        "caveats": {
            "type": "array",
            "items": {"type": "string"},
            "description": "読み手が知っておくべき注意点",
        },
        "not_verified": {
            "type": "array",
            "items": {"type": "string"},
            "description": "確かめていないこと",
        },
    },
    "required": [
        "dataset",
        "why_this_dataset",
        "columns_plotted",
        "data_checks",
        "caveats",
        "not_verified",
    ],
    "additionalProperties": False,
}

# What the gate does not prove, recorded with every run so a passed chart isn't read as more than it is.
NOT_CHECKED = (
    "data.csv が extract.py から作られたことは確認していません",
    "数値が正しいことは確認していません（data_checks はエージェントの自己申告です）",
    "グラフが質問に答えているかは確認していません",
)


def build_options(state: RunState) -> ClaudeAgentOptions:
    """Isolated from the user's Claude setup, so everything the agent may do is listed here."""
    return ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        setting_sources=[],
        cwd=state.run_dir,
        env={
            "CHART_PYTHON": sys.executable,
            # The CLI starts subagents in the background by default. The main agent's turn would then
            # end while it waits for finder, and the Stop hook would send it back with nothing to do.
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        },
        tools=["Agent", "Bash", "Edit", "Read", "WebFetch", "Write"],
        # Leaves out Read, Edit and Write: inside the run folder they need no approval, outside it they
        # get a refusal. Bash is listed because the sandbox is what contains it, not per-command approval.
        allowed_tools=["Agent", "Bash", "WebFetch", *TOOL_NAMES],
        permission_mode="acceptEdits",
        sandbox={
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
        },
        agents={
            "finder": AgentDefinition(
                description="福岡市のオープンデータを探す係。データ探しは必ずこの係に任せる",
                prompt=FINDER_PROMPT,
                tools=["WebFetch"],
                model=FINDER_MODEL,
            )
        },
        mcp_servers={SERVER_NAME: chart_server(state)},
        hooks=chart_hooks(state),
        output_format={"type": "json_schema", "schema": REPORT_SCHEMA},
        max_budget_usd=MAX_BUDGET_USD,
        max_turns=MAX_TURNS,
    )


def _detail(tool_input: dict[str, Any]) -> str:
    """The one argument that says what a tool call is doing."""
    for name in ("description", "command", "url", "file_path", "prompt"):
        if name in tool_input:
            return str(tool_input[name])[:_DETAIL_LENGTH]
    return ""


def record_message(run_dir: Path, message: Message) -> None:
    """Put what the agent is doing into the event log. The custom tools log their own results."""
    if not isinstance(message, AssistantMessage):
        return
    who = "finder" if message.parent_tool_use_id else "main"
    for block in message.content:
        if isinstance(block, ToolUseBlock):
            append_event(
                run_dir,
                "tool",
                who=who,
                name=block.name.removeprefix(f"mcp__{SERVER_NAME}__"),
                detail=_detail(block.input),
            )
        elif isinstance(block, TextBlock) and block.text.strip():
            append_event(
                run_dir, "text", who=who, text=block.text.strip()[:_TEXT_LENGTH]
            )


def run_status(state: RunState, *, stopped: bool) -> str:
    if state.gave_up is not None:
        return "no_chart"
    if state.passed is not None and stop_problem(state) is None:
        return "chart"
    return "stopped" if stopped else "failed"


def build_report(
    state: RunState,
    topic: str,
    result: ResultMessage | None,
    *,
    stopped: bool,
    error: str | None,
) -> dict[str, Any]:
    """`recorded` comes from code. `agent` is the model's own account, which is kept apart from it."""
    return {
        "status": run_status(state, stopped=stopped),
        "topic": topic,
        "no_chart_reason": state.gave_up,
        "error": error,
        "recorded": {
            "sources": state.downloads,
            "gate_failures": state.gate_failures,
            "files": state.passed,
            "not_checked": list(NOT_CHECKED),
            "permission_denials": result.permission_denials if result else None,
            "result": result.subtype if result else None,
            "cost_usd": result.total_cost_usd if result else None,
            "turns": result.num_turns if result else None,
            "duration_ms": result.duration_ms if result else None,
            "models": sorted(result.model_usage or {}) if result else [],
        },
        "agent": result.structured_output if result else None,
    }


async def run_agent(topic: str, run_dir: Path) -> int:
    """Run the agent and write its report, however it ends. Returns the process's exit code."""
    state = RunState(run_dir)
    # So Stop in the app, and Ctrl-C, still leave a report behind.
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None  # we are running inside asyncio.run
    for stop_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop_signal, task.cancel)

    result: ResultMessage | None = None
    error: str | None = None
    stopped = False
    try:
        async for message in query(
            prompt=f"テーマ: {topic}", options=build_options(state)
        ):
            record_message(run_dir, message)
            if isinstance(message, ResultMessage):
                result = message
    except ClaudeSDKError as failure:
        error = str(failure)
    except asyncio.CancelledError:
        stopped = True

    report = build_report(state, topic, result, stopped=stopped, error=error)
    write_report(run_dir, report)
    append_event(run_dir, "finished", status=report["status"])
    return 0 if report["status"] == "chart" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", help="what to chart, e.g. 人口の推移")
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="an existing folder for this run (default: a new one under output/)",
    )
    return parser


def run_cli(namespace: argparse.Namespace) -> None:
    run_dir: Path = namespace.run_dir or new_run_dir(output_root())
    write_pid(run_dir, os.getpid())
    if namespace.run_dir is None:  # the app logs this itself before starting us
        append_event(run_dir, "started", topic=namespace.topic)
    sys.exit(asyncio.run(run_agent(namespace.topic, run_dir)))


if __name__ == "__main__":
    run_cli(build_parser().parse_args())
