"""The web app: ask for a chart, watch the agent work, then read what it made and how far to trust it.

The page only touches run folders. The agent runs in its own process, so a click or a reload can't cut
a run short, and the tests can drive the page with folders written by hand.
"""

import datetime
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas
import streamlit

from packages.vega_lite_ai.runs import (
    CHART,
    DATA,
    LOG,
    MAX_BUDGET_USD,
    RunError,
    active_run,
    is_running,
    list_runs,
    output_root,
    read_events,
    read_report,
    run_topic,
    start_run,
    stop_run,
)

TITLE = "福岡市オープンデータのグラフ"

# st.session_state keys. A test puts a temporary folder and a fake starter in the first two.
OUTPUT_KEY = "output_root"
START_KEY = "start_run"
STOP_KEY = "stop_run"

POLL = datetime.timedelta(seconds=2)
LOG_LINES = 300
LOG_TAIL_CHARACTERS = 4000
_STATUS_MARKS = {"chart": "✅", "no_chart": "⚠️", "stopped": "⏹", "failed": "❌"}
_SILENT_TOOLS = frozenset({"download_file", "submit_chart", "report_no_chart"})


def describe_event(event: dict[str, Any]) -> str | None:
    """One line for the live log, or None for an event that adds nothing to it."""
    kind = event.get("kind")
    if kind == "tool":
        return _describe_tool(event)
    if kind == "text":
        return f"💬 {event['text']}"
    if kind == "download":
        return f"⬇️ 取得しました: {event['file']}"
    if kind == "download_failed":
        return f"⚠️ 取得できませんでした: {event['message']}"
    if kind == "gate_failed":
        return "❌ チェック不合格: " + " / ".join(event["errors"])
    if kind == "gate_passed":
        return "✅ チェック合格"
    if kind == "stop_blocked":
        return f"🚧 まだ終われません: {event['reason']}"
    if kind == "denied":
        return f"🚫 拒否しました: {event['reason']}"
    if kind == "no_chart":
        return f"⚠️ グラフなしで終了: {event['reason']}"
    return None


def _describe_tool(event: dict[str, Any]) -> str | None:
    name, detail = event["name"], event.get("detail", "")
    if name in _SILENT_TOOLS:  # these log their own results, which say more
        return None
    if name == "Agent":
        return f"🔎 finder に依頼: {detail}"
    if name == "StructuredOutput":
        return "📝 報告を書いています"
    if event.get("who") == "finder":
        return f"🔎 finder: {detail}"
    return f"🔧 {name}: {detail}"


def _render_log(run_dir: Path) -> None:
    lines = [line for event in read_events(run_dir) if (line := describe_event(event))]
    streamlit.code(
        "\n".join(lines[-LOG_LINES:]) or "開始しています…",
        language=None,
        wrap_lines=True,
    )


@streamlit.fragment(run_every=POLL)
def _watch_run(run_dir: Path) -> None:
    """Follows a run from the folder alone. The whole page reruns once to show the result."""
    if not is_running(run_dir):
        streamlit.rerun()
    streamlit.info(f"実行中: {run_topic(run_dir)}")
    if streamlit.button("停止", key=STOP_KEY):
        stop_run(run_dir)
    _render_log(run_dir)


def _render_form(root: Path, *, running: bool) -> None:
    with streamlit.form("topic"):
        topic = streamlit.text_input("何をグラフにしますか", placeholder="人口の推移")
        submitted = streamlit.form_submit_button("グラフを作る", disabled=running)
    streamlit.caption(f"1 回の実行で最大 ${MAX_BUDGET_USD:.2f} かかります。")
    if not submitted:
        return
    if not topic.strip():
        streamlit.warning("テーマを入力してください。")
        return
    start: Callable[[Path, str], Path] = streamlit.session_state.get(
        START_KEY, start_run
    )
    try:
        start(root, topic.strip())
    except RunError as error:
        streamlit.error(str(error))
        return
    streamlit.rerun()


def _run_label(run_dir: Path) -> str:
    report = read_report(run_dir)
    mark = "⏳" if report is None and is_running(run_dir) else "❌"
    if report is not None:
        mark = _STATUS_MARKS.get(report["status"], "❌")
    return f"{mark} {run_topic(run_dir)} ({run_dir.name})"


def _render_sidebar(root: Path) -> Path | None:
    names = [run_dir.name for run_dir in list_runs(root)]
    if not names:
        return None
    name = streamlit.sidebar.radio(
        "これまでの実行", names, format_func=lambda item: _run_label(root / item)
    )
    return root / name


def _render_chart(run_dir: Path) -> None:
    spec = json.loads((run_dir / CHART).read_text(encoding="utf-8"))
    streamlit.vega_lite_chart(spec=spec, width="stretch")
    with streamlit.expander("データ"):
        streamlit.dataframe(pandas.read_csv(run_dir / DATA), hide_index=True)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "（なし）"


def _render_agent_account(agent: dict[str, Any]) -> None:
    streamlit.subheader("エージェントの説明")
    streamlit.caption("モデル自身の説明です。チェックを通ったものではありません。")
    streamlit.markdown(f"**データ:** {agent['dataset']}")
    streamlit.markdown(f"**選んだ理由:** {agent['why_this_dataset']}")
    streamlit.markdown(f"**描いた列:** {', '.join(agent['columns_plotted'])}")
    streamlit.markdown(f"**行った検算**\n\n{_bullets(agent['data_checks'])}")
    streamlit.markdown(f"**注意点**\n\n{_bullets(agent['caveats'])}")
    streamlit.markdown(f"**確かめていないこと**\n\n{_bullets(agent['not_verified'])}")


def _metric_text(value: float | None, template: str) -> str:
    return "—" if value is None else template.format(value)


def _render_record(recorded: dict[str, Any]) -> None:
    streamlit.subheader("実行の記録")
    streamlit.caption("モデルではなくコードが記録したものです。")
    minutes = recorded["duration_ms"] and recorded["duration_ms"] / 60_000
    cost, turns, duration, failures = streamlit.columns(4)
    cost.metric("費用", _metric_text(recorded["cost_usd"], "${:.2f}"))
    turns.metric("ターン", _metric_text(recorded["turns"], "{}"))
    duration.metric("時間", _metric_text(minutes, "{:.1f} 分"))
    failures.metric("チェック不合格", str(recorded["gate_failures"]))
    sources = [
        f"[{source['file']}]({source['final_url']}) `sha256:{source['sha256'][:12]}`"
        for source in recorded["sources"]
    ]
    streamlit.markdown(f"**取得元**\n\n{_bullets(sources)}")
    denials = Counter(
        denial.get("tool_name", "?") for denial in recorded["permission_denials"] or []
    )
    if denials:
        streamlit.markdown(
            "**拒否された操作:** "
            + ", ".join(f"{name} × {count}" for name, count in denials.items())
        )
    streamlit.warning(
        f"**チェックで確認していないこと**\n\n{_bullets(recorded['not_checked'])}"
    )


def _render_run(run_dir: Path) -> None:
    streamlit.header(run_topic(run_dir))
    report = read_report(run_dir)
    if report is None:
        streamlit.error("報告がありません。エージェントが途中で止まりました。")
        log = run_dir / LOG
        if log.exists():
            streamlit.code(
                log.read_text(encoding="utf-8", errors="replace")[
                    -LOG_TAIL_CHARACTERS:
                ],
                language=None,
            )
        return
    status = report["status"]
    if status == "chart":
        _render_chart(run_dir)
    elif status == "no_chart":
        streamlit.warning(f"グラフは作られませんでした: {report['no_chart_reason']}")
    elif status == "stopped":
        streamlit.info("途中で停止しました。")
    else:
        detail = report["error"] or report["recorded"]["result"] or "原因は不明です"
        streamlit.error(f"チェックを通ったグラフはありません: {detail}")
    if report["agent"]:
        _render_agent_account(report["agent"])
    _render_record(report["recorded"])
    with streamlit.expander("実行ログ"):
        _render_log(run_dir)


def render_app() -> None:
    """Render the Streamlit app page."""
    streamlit.title(TITLE)
    try:
        root: Path = streamlit.session_state.get(OUTPUT_KEY) or output_root()
    except RunError as error:
        streamlit.error(str(error))
        return
    active = active_run(root)
    selected = _render_sidebar(root)
    _render_form(root, running=active is not None)
    if active is not None:
        _watch_run(active)
    elif selected is not None:
        _render_run(selected)
