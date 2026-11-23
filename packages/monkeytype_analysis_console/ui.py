"""The Streamlit app: a sidebar that loads results, and the pages that show them.

`render_app` runs on every page. It draws the sidebar, loads the uploaded
files and the results folder into session state, then runs the page. The page
files only call one `render_*_page` function, so all the code is here, where
the lint targets check it.
"""

import math
import os
from pathlib import Path

import streamlit

from packages.monkeytype_analysis_console import charts
from packages.monkeytype_analysis_console.history_html import (
    band_legend_html,
    history_html,
)
from packages.monkeytype_analysis_console.metrics import (
    default_threshold,
    fastest_speed,
    finite_speed,
    format_number,
    slow_words,
)
from packages.monkeytype_analysis_console.results import (
    Loaded,
    ParsedFile,
    Result,
    merge,
    parse_file,
    resolve_folder,
    result_files,
)

TITLE = "Monkeytype analysis console"
FOLDER_ENV = "MONKEYTYPE_RESULTS_DIR"
REPLAY_PAGE = "app_pages/replay.py"

# st.session_state keys. A test types into the folder box through FOLDER_KEY.
UPLOAD_KEY = "uploaded_files"
FOLDER_KEY = "results_folder"
PICK_KEY = "picked_result"
LOADED_KEY = "loaded_results"
THRESHOLD_KEY = "slow_threshold"

NO_RESULTS = (
    "No results loaded. Upload files that `yr` copied, or enter a results "
    "folder in the sidebar."
)
NO_HISTORY = (
    "No input history in this result. Open it on the result screen before "
    "pressing `yr`."
)
NO_CHART = "No chart in this result."


def render_app() -> None:
    """Draws the sidebar, loads the results, and runs the current page."""
    page = streamlit.navigation(
        [streamlit.Page(REPLAY_PAGE, title="Result replay", default=True)]
    )
    streamlit.session_state[LOADED_KEY] = _render_sources()
    page.run()


def render_replay_page() -> None:
    """The Result replay page: Monkeytype's result screen, rebuilt."""
    streamlit.header("Result replay")
    result = _pick_result(_loaded())
    if result is None:
        streamlit.info(NO_RESULTS)
        return
    _render_headline(result)
    _render_speed_chart(result)
    _render_other_stats(result)
    if result.words:
        threshold = _threshold_slider(result)
        _render_history(result, threshold)
    else:
        streamlit.info(NO_HISTORY)
        threshold = default_threshold(result)
    _render_word_lists(result, threshold)


def result_label(result: Result) -> str:
    """How the result picker names a result."""
    return " · ".join(
        [
            f"{result.copied_at:%Y-%m-%d %H:%M}",
            result.test or "–",
            result.word_list_name,
            f"{format_number(result.wpm)} wpm",
        ]
    )


def threshold_key(result: Result) -> str:
    """The session state key of a result's slow-word slider.

    Each result has its own, so picking another result starts from its own
    threshold.
    """
    return f"{THRESHOLD_KEY}:{result.identity!r}"


@streamlit.cache_data(show_spinner=False, max_entries=1000)
def _parse_upload(name: str, data: bytes) -> ParsedFile:
    return parse_file(name, data)


@streamlit.cache_data(show_spinner=False, max_entries=1000)
def _parse_folder_file(path: str, modified_ns: int, size: int) -> ParsedFile:
    # `modified_ns` and `size` are only part of the cache key, so that a file
    # that changed is read again on the next rerun.
    file = Path(path)
    try:
        data = file.read_bytes()
    except OSError as e:
        return ParsedFile(file.name, (), (f"{file.name}: {e.strerror}",))
    return parse_file(file.name, data)


def _render_sources() -> Loaded:
    sidebar = streamlit.sidebar
    uploads = sidebar.file_uploader(
        "Upload results",
        type=["yml", "yaml"],
        accept_multiple_files=True,
        key=UPLOAD_KEY,
        help="Files with results that the Surfingkeys `yr` mapping copied.",
    )
    if FOLDER_KEY not in streamlit.session_state:
        streamlit.session_state[FOLDER_KEY] = os.environ.get(FOLDER_ENV, "")
    folder = sidebar.text_input(
        "Results folder",
        key=FOLDER_KEY,
        help=(
            "Every .yml and .yaml file directly in this folder. The console "
            f"only reads it. `{FOLDER_ENV}` fills this box on start."
        ),
    )
    parsed = _read_folder(folder) if folder.strip() else []
    parsed += [_parse_upload(file.name, file.getvalue()) for file in uploads or []]
    loaded = merge(parsed)
    _render_load_summary(loaded)
    return loaded


def _read_folder(text: str) -> list[ParsedFile]:
    folder = resolve_folder(text)
    if not folder.is_dir():
        streamlit.sidebar.warning(f"Not a folder: {folder}")
        return []
    try:
        files = result_files(folder)
        stats = [(file, file.stat()) for file in files]
    except OSError as e:
        streamlit.sidebar.warning(f"Can't read {folder}: {e.strerror}")
        return []
    return [
        _parse_folder_file(str(file), stat.st_mtime_ns, stat.st_size)
        for file, stat in stats
    ]


def _render_load_summary(loaded: Loaded) -> None:
    if not loaded.files:
        return
    summary = (
        f"{_plural(len(loaded.results), 'result')} from {_plural(loaded.files, 'file')}"
    )
    if loaded.duplicates:
        summary += f", {_plural(loaded.duplicates, 'duplicate')} skipped"
    streamlit.sidebar.caption(summary)
    if loaded.errors:
        label = f"{_plural(loaded.files_with_errors, 'file')} had errors"
        with streamlit.sidebar.expander(label):
            for error in loaded.errors:
                streamlit.text(error)


def _loaded() -> Loaded:
    loaded = streamlit.session_state.get(LOADED_KEY)
    return loaded if isinstance(loaded, Loaded) else Loaded()


def _pick_result(loaded: Loaded) -> Result | None:
    if not loaded.results:
        return None
    by_identity = {result.identity: result for result in reversed(loaded.results)}
    if streamlit.session_state.get(PICK_KEY) not in by_identity:
        # The picked result is no longer loaded: go back to the newest.
        streamlit.session_state.pop(PICK_KEY, None)
    picked = streamlit.sidebar.selectbox(
        "Result",
        list(by_identity),
        format_func=lambda identity: result_label(by_identity[identity]),
        key=PICK_KEY,
    )
    return by_identity[picked]


def _render_headline(result: Result) -> None:
    wpm_column, acc_column, _ = streamlit.columns([1, 1, 3])
    wpm_column.metric("wpm", format_number(result.wpm))
    acc_column.metric("acc", _percent(result.acc))
    if result.pb:
        crown = result.crown.text if result.crown is not None else ""
        streamlit.badge(
            f"PB {crown}".strip(), icon=":material/emoji_events:", color="violet"
        )
    if result.unit != "wpm":
        streamlit.caption(f"The chart and the word speeds are in {result.unit}.")


def _render_speed_chart(result: Result) -> None:
    chart = charts.speed_chart(result)
    if chart is not None:
        streamlit.altair_chart(chart, width="stretch")
        return
    message = NO_CHART
    if result.chart_error:
        message += f" `yr` reported: {result.chart_error}"
    streamlit.info(message)


def _render_other_stats(result: Result) -> None:
    columns = streamlit.columns(6 if result.typed_time else 5)
    test_type, raw, characters, consistency, time = columns[:5]
    test_type.metric("test type", result.test or "–")
    test_type.caption(" · ".join([result.word_list_name, *result.options]))
    raw.metric("raw", format_number(result.raw))
    chars = result.chars
    characters.metric(
        "characters",
        "–"
        if chars is None
        else f"{chars.correct}/{chars.incorrect}/{chars.extra}/{chars.missed}",
        help="correct/incorrect/extra/missed",
    )
    consistency.metric("consistency", _percent(result.consistency))
    if result.key_consistency is not None:
        consistency.caption(f"key {_percent(result.key_consistency)}")
    time.metric("time", _seconds(result.time))
    if result.afk is not None or result.afk_pct is not None:
        time.caption(f"afk {_seconds(result.afk)} ({_percent(result.afk_pct)})")
    if result.typed_time:
        columns[5].metric(result.typed_time.label, _clock(result.typed_time.seconds))
    notes = [
        ("flags", ", ".join(result.flags)),
        ("tags", ", ".join(result.tags)),
        ("quote", result.quote_source or ""),
    ]
    for label, text in notes:
        if text:
            streamlit.caption(f"{label}: {text}")


def _threshold_slider(result: Result) -> float:
    start = default_threshold(result)
    top = math.ceil(max(fastest_speed(result.words) or 0.0, start)) or 1
    whole = top >= 20
    value = streamlit.slider(
        f"Slow below ({result.unit})",
        min_value=0.0,
        max_value=float(top),
        value=float(start),
        step=1.0 if whole else 0.1,
        format="%.0f" if whole else "%.1f",
        key=threshold_key(result),
        help="Words slower than this get a dotted outline. It starts at the "
        "threshold you gave `yr`.",
    )
    return float(value)


def _render_history(result: Result, threshold: float) -> None:
    streamlit.subheader("Input history")
    streamlit.html(history_html(result.words, threshold, result.unit))
    legend = band_legend_html(result.steps)
    if legend:
        streamlit.html(legend)
    chart = charts.word_speed_chart(result.words, result.steps, threshold, result.unit)
    if chart is not None:
        streamlit.altair_chart(chart, width="stretch")
    too_fast = sum(
        1
        for word in result.words
        if word.wpm is not None and finite_speed(word) is None
    )
    if too_fast:
        streamlit.caption(
            f"{_plural(too_fast, 'word')} too fast to measure "
            f"{'is' if too_fast == 1 else 'are'} not in the chart."
        )


def _render_word_lists(result: Result, threshold: float) -> None:
    slow = " ".join(word.word for word in slow_words(result.words, threshold))
    lists = [
        ("Words", " ".join(result.word_list)),
        ("Missed words", " ".join(result.missed_word_list)),
        (f"Slow words under {format_number(threshold)} {result.unit}", slow),
    ]
    for title, text in lists:
        streamlit.caption(title)
        if text:
            streamlit.code(text, language=None, wrap_lines=True)
        else:
            streamlit.text("None.")


def _percent(value: float | None) -> str:
    return "–" if value is None else f"{format_number(value)}%"


def _seconds(value: float | None) -> str:
    return "–" if value is None else f"{format_number(value)}s"


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02}:{whole // 60 % 60:02}:{whole % 60:02}"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")
