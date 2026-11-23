"""The Streamlit app: a sidebar that loads results, and the pages that show them.

`render_app` runs on every page. It draws the sidebar, loads the uploaded
files and the results folder into session state, then runs the page. The page
files only call one `render_*_page` function, so all the code is here, where
the lint targets check it.
"""

import math
import os
from pathlib import Path
from typing import Any

import pandas
import streamlit

from packages.monkeytype_analysis_console import charts
from packages.monkeytype_analysis_console.history_html import (
    band_legend_html,
    history_html,
)
from packages.monkeytype_analysis_console.metrics import (
    DEFAULT_GOAL,
    WordGroup,
    band_groups,
    chars_left_wrong,
    default_threshold,
    fastest_speed,
    flags,
    format_number,
    goal_met,
    is_aborted,
    is_mistyped,
    position_groups,
    slow_words,
    time_lost,
    too_fast_count,
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
from packages.monkeytype_analysis_console.typos import (
    category_counts,
    classify_words,
    key_confusions,
    wrong_keys,
)

TITLE = "Monkeytype analysis console"
FOLDER_ENV = "MONKEYTYPE_RESULTS_DIR"
REPLAY_PAGE = "app_pages/replay.py"
ANALYSIS_PAGE = "app_pages/analysis.py"

# st.session_state keys. A test types into the folder box through FOLDER_KEY.
UPLOAD_KEY = "uploaded_files"
FOLDER_KEY = "results_folder"
PICK_KEY = "picked_result"
LOADED_KEY = "loaded_results"
THRESHOLD_KEY = "slow_threshold"
GOAL_KEY = "accuracy_goal"
# A widget on another page is another widget to Streamlit, even with the same
# key. So the picked result and the goal are also kept under keys of their own:
# a callback copies each change there, and each run loads it back into the
# widget before drawing it.
_PICK_KEPT_KEY = "picked_result_kept"
_GOAL_KEPT_KEY = "accuracy_goal_kept"
TOP_CONFUSIONS = 10

NO_RESULTS = (
    "No results loaded. Upload files that `yr` copied, or enter a results "
    "folder in the sidebar."
)
NO_HISTORY = (
    "No input history in this result. Open it on the result screen before "
    "pressing `yr`."
)
NO_CHART = "No chart in this result."
ABORTED = "Nothing else to analyse: fewer than 25 keypresses."
NO_MISTAKES = "No mistyped words."


def render_app() -> None:
    """Draws the sidebar, loads the results, and runs the current page."""
    page = streamlit.navigation(
        [
            streamlit.Page(REPLAY_PAGE, title="Result replay", default=True),
            streamlit.Page(ANALYSIS_PAGE, title="Result analysis"),
        ]
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


def render_analysis_page() -> None:
    """The Result analysis page: the numbers behind one result."""
    streamlit.header("Result analysis")
    result = _pick_result(_loaded())
    goal = _goal_input()
    if result is None:
        streamlit.info(NO_RESULTS)
        return
    _render_checks(result, goal)
    if is_aborted(result):
        streamlit.info(ABORTED)
        return
    if not result.words:
        streamlit.info(NO_HISTORY)
        return
    _render_word_speed(result)
    _render_typos(result)
    _render_position(result)


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
    state = streamlit.session_state
    if state.get(_PICK_KEPT_KEY) in by_identity:
        state[PICK_KEY] = state[_PICK_KEPT_KEY]
    elif state.get(PICK_KEY) not in by_identity:
        # The picked result is no longer loaded: go back to the newest.
        state.pop(PICK_KEY, None)
    picked = streamlit.sidebar.selectbox(
        "Result",
        list(by_identity),
        format_func=lambda identity: result_label(by_identity[identity]),
        key=PICK_KEY,
        on_change=_copy_state,
        args=(PICK_KEY, _PICK_KEPT_KEY),
    )
    state[_PICK_KEPT_KEY] = picked
    return by_identity[picked]


def _goal_input() -> float:
    state = streamlit.session_state
    state[GOAL_KEY] = state.get(_GOAL_KEPT_KEY, DEFAULT_GOAL)
    goal = streamlit.sidebar.number_input(
        "Accuracy goal (%)",
        min_value=0.0,
        max_value=100.0,
        step=0.5,
        format="%.1f",
        key=GOAL_KEY,
        on_change=_copy_state,
        args=(GOAL_KEY, _GOAL_KEPT_KEY),
        help="A result meets the goal when its accuracy is at least this.",
    )
    state[_GOAL_KEPT_KEY] = goal
    return float(goal)


def _copy_state(source: str, target: str) -> None:
    streamlit.session_state[target] = streamlit.session_state[source]


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
    _render_too_fast(result, "not in the chart")


def _render_too_fast(result: Result, place: str) -> None:
    too_fast = too_fast_count(result.words)
    if too_fast:
        verb = "is" if too_fast == 1 else "are"
        streamlit.caption(
            f"{_plural(too_fast, 'word')} too fast to measure {verb} {place}."
        )


def _render_checks(result: Result, goal: float) -> None:
    streamlit.subheader("Result checks")
    met = goal_met(result, goal)
    lost = time_lost(result)
    left = chars_left_wrong(result)
    goal_column, lost_column, left_column = streamlit.columns(3)
    goal_column.metric(
        "accuracy goal", "–" if met is None else ("met" if met else "missed")
    )
    goal_column.caption(f"acc {_percent(result.acc)} vs {format_number(goal)}%")
    lost_column.metric("time lost to mistakes", _seconds(lost))
    if lost is not None and result.time:
        share = format_number(100 * lost / result.time, 0)
        lost_column.caption(f"{share}% of the test")
    left_column.metric("characters left wrong", "–" if left is None else str(left))
    found = flags(result)
    streamlit.caption("flags: " + (", ".join(found) if found else "none"))


def _render_word_speed(result: Result) -> None:
    streamlit.subheader("Word speed by band")
    rows = [
        {
            "band": group.label,
            **_group_columns(group, result.unit),
            "mean length": _rounded(group.mean_length),
            "mean Shift presses": _rounded(group.mean_shift_presses),
            "mean symbols": _rounded(group.mean_symbols),
            "mistyped": group.mistyped,
        }
        for group in band_groups(result)
    ]
    streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)
    _render_too_fast(result, "only in the last row")


def _render_typos(result: Result) -> None:
    streamlit.subheader("Typos")
    mistyped = [word for word in result.words if is_mistyped(word)]
    if not mistyped:
        streamlit.info(NO_MISTAKES)
        return
    classified = classify_words(result.words)
    typo_count = sum(len(item.typos) for item in classified)
    streamlit.markdown(
        f"{len(mistyped)} of {_plural(len(result.words), 'word')} mistyped, "
        f"{_plural(typo_count, 'typo')}"
    )
    categories = [
        {"type": category, "count": count, "examples": ", ".join(examples)}
        for category, count, examples in category_counts(classified)
    ]
    if categories:
        streamlit.dataframe(pandas.DataFrame(categories), hide_index=True)
    streamlit.caption(
        "Each key's colour shows how often it was the key wanted when a wrong "
        "key was pressed."
    )
    streamlit.altair_chart(
        charts.keyboard_chart(wrong_keys(classified)), width="stretch"
    )
    confusions = key_confusions(classified).most_common(TOP_CONFUSIONS)
    if confusions:
        streamlit.caption("Key confusions (expected→typed)")
        streamlit.dataframe(
            pandas.DataFrame(confusions, columns=["confusion", "count"]),
            hide_index=True,
        )
    typos_by_word = {item.word: item.typos for item in classified}
    rows = []
    for word in mistyped:
        typos = typos_by_word.get(word, ())
        if word.typed is None:
            found = "no first attempt recorded"
        else:
            found = "; ".join(typo.detail for typo in typos)
        rows.append(
            {
                "word": word.word,
                "first attempt": word.typed or "",
                "typos": found,
                result.unit: format_number(word.wpm),
                "letters fixed": word.fixed,
                "left wrong": "yes" if word.error else "",
            }
        )
    streamlit.caption("Mistyped words")
    streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)


def _render_position(result: Result) -> None:
    streamlit.subheader("Position in test")
    rows = [
        {
            "part": group.label,
            **_group_columns(group, result.unit),
            "mistyped": group.mistyped,
        }
        for group in position_groups(result.words)
    ]
    streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)


def _group_columns(group: WordGroup, unit: str) -> dict[str, Any]:
    return {"words": group.words, f"mean {unit}": _rounded(group.mean_speed)}


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


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
