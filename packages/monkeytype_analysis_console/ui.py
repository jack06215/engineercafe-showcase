"""The Streamlit app: a sidebar that loads results, and the pages that show them.

`render_app` runs on every page. It draws the sidebar, loads the uploaded
files and the results folder into session state, then runs the page. The page
files only call one `render_*_page` function, so all the code is here, where
the lint targets check it.
"""

import math
import os
from collections.abc import Collection
from pathlib import Path
from typing import Any

import anthropic
import pandas
import streamlit

from packages.monkeytype_analysis_console import charts, practice
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
from packages.monkeytype_analysis_console.progress import (
    TREND_FIELDS,
    Trend,
    by_word_list,
    common_tests,
    counted,
    latest_results,
    recurring_problems,
    repeated_confusions,
    trend_groups,
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
PROGRESS_PAGE = "app_pages/progress.py"
PRACTICE_PAGE = "app_pages/practice.py"
KEY_ENV = "ANTHROPIC_API_KEY"

# st.session_state keys. A test types into the folder box through FOLDER_KEY.
UPLOAD_KEY = "uploaded_files"
FOLDER_KEY = "results_folder"
PICK_KEY = "picked_result"
LOADED_KEY = "loaded_results"
THRESHOLD_KEY = "slow_threshold"
GOAL_KEY = "accuracy_goal"
TEST_KEY = "progress_test"
GROUPS_KEY = "practice_groups"
TEXT_KEY = "practice_text"
WORD_LISTS_KEY = "practice_word_lists"
MODEL_KEY = "practice_model"
GROUP_EFFORT_KEY = "practice_group_effort"
TEXT_EFFORT_KEY = "practice_text_effort"
TIMEOUT_KEY = "practice_timeout"
FOCUS_KEY = "practice_focus"
LENGTH_KEY = "practice_length"
GROUP_BUTTON_KEY = "practice_group_button"
TEXT_BUTTON_KEY = "practice_text_button"
RESET_BUTTON_KEY = "practice_reset_settings"
# A widget on another page is another widget to Streamlit, even with the same
# key. So the picked result, the goal and the Practice inputs are also kept
# under keys of their own: a callback copies each change there, and each run
# loads it back into the widget before drawing it. The Practice inputs use
# `_kept`, `_load` and `_keep` for this.
_PICK_KEPT_KEY = "picked_result_kept"
_GOAL_KEPT_KEY = "accuracy_goal_kept"
TOP_CONFUSIONS = 10
ALL_PROBLEMS = "All problems"
DEFAULT_LENGTH = 50

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
NEED_TWO = "Progress needs at least 2 results that are not aborted."
NO_RECURRING = "No word was slow or mistyped in more than one result."
PRACTICE_INTRO = """\
Find the words you keep getting wrong, let Claude group them by cause, and \
get a practice text for Monkeytype's custom mode.

1. Check the problems below, and choose the word lists they come from.
1. Optional: press **Group by cause**, then pick a group as the focus.
1. Press **Write practice text**, copy the text, and type it in Monkeytype's \
custom mode.
1. Copy that result with `yr`. It counts here like any other result, and \
Progress shows it under the word list "custom".

Claude sees only what is under "What Claude gets", and only when you press a \
button."""
PRACTICE_NEEDS_TWO = "Practice needs at least 2 results."
NO_WORD_LISTS = "Choose at least one word list."
PROBLEM_RULE = (
    "A problem is a word that was slow or mistyped in at least 2 of these "
    "results, or a key confusion seen at least twice."
)
MODEL_HELP = (
    "Claude Opus 5.5 is the default. Sonnet 5.5 and Haiku 5.5 answer faster and "
    "cost less; Fable 5.2 is the most capable and costs the most. When Claude "
    "declines a request, the API tries another model, except for Haiku 5.5."
)
EFFORT_HELP = (
    "How much Claude thinks before it answers. Higher effort takes longer and "
    "uses more tokens, so raise the timeout with it."
)
TIMEOUT_HELP = (
    "How long to wait for one attempt. A request that times out or finds Claude "
    "busy is tried up to 3 times."
)
NOTHING_TO_PRACTISE = (
    "No word was slow or mistyped in 2 of your last 20 results, so there is "
    "nothing to practise yet."
)
NO_KEY = f"Set {KEY_ENV} to let Claude group these problems and write a practice text."
EARLIER_PROBLEMS = (
    "Made from an earlier set of problems. Press the button again to update it."
)
NO_GROUPS = "Claude found no shared causes."
GROUPS_BY_CLAUDE = "Groups and causes by Claude. The counts above are the console's."
TEXT_BY_CLAUDE = "Written by Claude. Paste it into Monkeytype's custom mode."


def render_app() -> None:
    """Draws the sidebar, loads the results, and runs the current page."""
    page = streamlit.navigation(
        [
            streamlit.Page(REPLAY_PAGE, title="Result replay", default=True),
            streamlit.Page(ANALYSIS_PAGE, title="Result analysis"),
            streamlit.Page(PROGRESS_PAGE, title="Progress"),
            streamlit.Page(PRACTICE_PAGE, title="Practice"),
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


def render_progress_page() -> None:
    """The Progress page: results over time, per word list and test type."""
    streamlit.header("Progress")
    goal = _goal_input()
    loaded = _loaded()
    if not loaded.results:
        streamlit.info(NO_RESULTS)
        return
    results = counted(loaded.results)
    if len(results) < 2:
        streamlit.info(NEED_TWO)
        return
    tests = common_tests(results)
    if streamlit.session_state.get(TEST_KEY) not in tests:
        streamlit.session_state.pop(TEST_KEY, None)
    test = streamlit.selectbox("Test type", tests, key=TEST_KEY)
    for word_list, group in by_word_list(
        [result for result in results if result.test == test]
    ).items():
        streamlit.subheader(word_list)
        wpm_column, acc_column = streamlit.columns(2)
        wpm_column.altair_chart(charts.progress_chart(group, "wpm"), width="stretch")
        acc_column.altair_chart(
            charts.progress_chart(group, "acc", goal), width="stretch"
        )
    _render_trends([trend for trend in trend_groups(results) if trend.test == test])
    _render_recurring(results)


def render_practice_page() -> None:
    """The Practice page: Claude groups the problems and writes a practice text.

    Nothing is sent to the API until a button is pressed.
    """
    streamlit.header("Practice")
    streamlit.markdown(PRACTICE_INTRO)
    loaded = _loaded()
    if not loaded.results:
        streamlit.info(NO_RESULTS)
        return
    results = counted(loaded.results)
    if len(results) < 2:
        streamlit.info(PRACTICE_NEEDS_TWO)
        return
    streamlit.subheader("Problems")
    results = _word_list_filter(results)
    if not results:
        streamlit.info(NO_WORD_LISTS)
        return
    if len(results) < 2:
        streamlit.info(PRACTICE_NEEDS_TWO)
        return
    _render_basis(results)
    found = practice.problems(results)
    if found.empty:
        streamlit.info(NOTHING_TO_PRACTISE)
        return
    _render_problems(found)
    if not os.environ.get(KEY_ENV):
        streamlit.info(NO_KEY)
        return
    settings = _claude_settings()
    _render_cause_groups(found, settings)
    _render_practice_text(found, settings)


def claude_client() -> anthropic.Anthropic:
    """The client that the Practice page sends its requests through."""
    return anthropic.Anthropic()


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


def _render_trends(trends: list[Trend]) -> None:
    streamlit.subheader("Latest vs average")
    rows = []
    for trend in trends:
        latest = trend.latest
        row: dict[str, Any] = {
            "word list": trend.word_list,
            "test": trend.test,
            "results": len(trend.results),
            "latest": f"{latest.copied_at:%Y-%m-%d %H:%M}",
            "wpm": latest.wpm,
            "acc": latest.acc,
            "consistency": latest.consistency,
            "compared with": (
                f"mean of {_plural(len(trend.earlier), 'earlier result')}"
                if trend.earlier
                else "no earlier results"
            ),
        }
        for field in TREND_FIELDS:
            row[f"change in {field}"] = _signed(trend.change(field))
        rows.append(row)
    streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)


def _render_recurring(results: list[Result]) -> None:
    streamlit.subheader("Recurring problems")
    window = latest_results(results)
    streamlit.caption(
        "Words slow or mistyped in at least 2 of the last "
        f"{_plural(len(window), 'result')}, across every word list and test type."
    )
    recurring = recurring_problems(results)
    if recurring:
        rows = [
            {
                "word": item.word,
                "results": item.results,
                "slow in": item.slow,
                "mistyped in": item.mistyped,
            }
            for item in recurring
        ]
        streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)
    else:
        streamlit.info(NO_RECURRING)
    confusions = repeated_confusions(results)
    listed = ", ".join(f"{pair} ×{count}" for pair, count in confusions)
    streamlit.caption(f"Key confusions seen at least twice: {listed or 'none'}")


def _word_list_filter(results: list[Result]) -> list[Result]:
    lists = sorted({result.word_list_name for result in results})
    kept = streamlit.session_state.get(_kept(WORD_LISTS_KEY))
    # Until the box is changed, it holds every word list, new ones included.
    chosen = lists if kept is None else [name for name in kept if name in lists]
    if kept and not chosen:
        chosen = lists
    streamlit.session_state[WORD_LISTS_KEY] = chosen
    chosen = streamlit.multiselect(
        "Word lists",
        lists,
        help="The problems come from results of these word lists. Results of "
        'practice texts are under "custom".',
        **_keep(WORD_LISTS_KEY),
    )
    return [result for result in results if result.word_list_name in chosen]


def _render_basis(results: list[Result]) -> None:
    window = latest_results(results)
    streamlit.caption(
        f"Based on the newest {_plural(len(window), 'result')} of {len(results)} "
        f"in these word lists, from {window[0].copied_at:%Y-%m-%d} to "
        f"{window[-1].copied_at:%Y-%m-%d}, of every test type. Aborted results "
        "don't count."
    )
    with streamlit.expander("Which results"):
        rows = [
            {
                "copied": f"{result.copied_at:%Y-%m-%d %H:%M}",
                "test": result.test or "–",
                "word list": result.word_list_name,
                "wpm": result.wpm,
                "acc": result.acc,
            }
            for result in reversed(window)
        ]
        streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)


def _render_problems(found: practice.Problems) -> None:
    streamlit.caption(PROBLEM_RULE)
    if found.words:
        rows = [
            {
                "word": word.word,
                "results": word.results,
                "slow in": word.slow,
                "mistyped in": word.mistyped,
                "typos": "; ".join(
                    f"{typo.detail} ×{typo.count}" for typo in word.typos
                ),
            }
            for word in found.words
        ]
        streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)
    else:
        streamlit.info(NO_RECURRING)
    listed = ", ".join(
        f"{item.pair} ×{item.count} ({item.category})" for item in found.confusions
    )
    streamlit.caption(f"Key confusions seen at least twice: {listed or 'none'}")


def _claude_settings() -> practice.Settings:
    defaults = practice.Settings()
    with streamlit.expander("Claude settings"):
        _load(MODEL_KEY, defaults.model, practice.MODELS)
        model = streamlit.selectbox(
            "Model",
            practice.MODELS,
            format_func=_model_label,
            help=MODEL_HELP,
            **_keep(MODEL_KEY),
        )
        group_column, text_column = streamlit.columns(2)
        _load(GROUP_EFFORT_KEY, defaults.group_effort, practice.EFFORTS)
        group_effort = group_column.select_slider(
            "Effort for cause groups",
            practice.EFFORTS,
            help=EFFORT_HELP,
            **_keep(GROUP_EFFORT_KEY),
        )
        _load(TEXT_EFFORT_KEY, defaults.text_effort, practice.EFFORTS)
        text_effort = text_column.select_slider(
            "Effort for practice text",
            practice.EFFORTS,
            help=EFFORT_HELP,
            **_keep(TEXT_EFFORT_KEY),
        )
        _load(TIMEOUT_KEY, defaults.timeout)
        timeout = streamlit.number_input(
            "Timeout per attempt (seconds)",
            min_value=practice.MIN_TIMEOUT,
            max_value=practice.MAX_TIMEOUT,
            step=30.0,
            format="%.0f",
            help=TIMEOUT_HELP,
            **_keep(TIMEOUT_KEY),
        )
        streamlit.button(
            "Reset to defaults", key=RESET_BUTTON_KEY, on_click=_reset_settings
        )
    settings = practice.Settings(
        model,
        practice.EFFORTS[practice.EFFORTS.index(group_effort)],
        practice.EFFORTS[practice.EFFORTS.index(text_effort)],
        float(timeout),
    )
    for key in (MODEL_KEY, GROUP_EFFORT_KEY, TEXT_EFFORT_KEY, TIMEOUT_KEY):
        streamlit.session_state[_kept(key)] = streamlit.session_state[key]
    streamlit.caption(
        f"{_model_label(settings.model)} · effort {settings.group_effort} for "
        f"cause groups, {settings.text_effort} for practice text · "
        f"{settings.timeout:.0f} s per attempt"
    )
    return settings


def _reset_settings() -> None:
    defaults = practice.Settings()
    state = streamlit.session_state
    state[_kept(MODEL_KEY)] = defaults.model
    state[_kept(GROUP_EFFORT_KEY)] = defaults.group_effort
    state[_kept(TEXT_EFFORT_KEY)] = defaults.text_effort
    state[_kept(TIMEOUT_KEY)] = defaults.timeout


def _model_label(model: str) -> str:
    return f"{practice.MODEL_NAMES[model]} ({model})"


def _render_cause_groups(found: practice.Problems, settings: practice.Settings) -> None:
    streamlit.subheader("Cause groups")
    pressed = streamlit.button("Group by cause", key=GROUP_BUTTON_KEY)
    _render_request(
        settings,
        settings.group_effort,
        practice.GROUP_INSTRUCTIONS,
        practice.group_content(found),
    )
    if pressed:
        with streamlit.spinner("Claude is grouping your problems…"):
            try:
                streamlit.session_state[GROUPS_KEY] = practice.group_by_cause(
                    claude_client(), found, settings
                )
            except practice.ClaudeError as e:
                streamlit.error(str(e))
    grouping = _grouping()
    if grouping is None:
        return
    _render_earlier(grouping.problems, found)
    if grouping.groups:
        rows = [
            {
                "group": group.name,
                "cause": group.cause,
                "words": ", ".join(group.words),
                "confusions": ", ".join(group.confusions),
            }
            for group in grouping.groups
        ]
        streamlit.dataframe(pandas.DataFrame(rows), hide_index=True)
        left = [*grouping.ungrouped_words, *grouping.ungrouped_confusions]
        if left:
            streamlit.caption("Not in a group: " + ", ".join(left))
        streamlit.caption(GROUPS_BY_CLAUDE)
    else:
        streamlit.info(NO_GROUPS)
    _render_usage(grouping.usage)


def _render_practice_text(
    found: practice.Problems, settings: practice.Settings
) -> None:
    streamlit.subheader("Practice text")
    grouping = _grouping()
    groups = grouping.groups if grouping is not None else ()
    names = [ALL_PROBLEMS, *(group.name for group in groups)]
    # After the groups are made again, the focused group may be gone.
    _load(FOCUS_KEY, ALL_PROBLEMS, names)
    name = streamlit.selectbox("Focus", names, **_keep(FOCUS_KEY))
    _load(LENGTH_KEY, DEFAULT_LENGTH)
    length = streamlit.slider(
        "Length (words)", min_value=20, max_value=100, step=10, **_keep(LENGTH_KEY)
    )
    state = streamlit.session_state
    state[_kept(FOCUS_KEY)] = name
    state[_kept(LENGTH_KEY)] = length
    focus = next((group for group in groups if group.name == name), None)
    pressed = streamlit.button("Write practice text", key=TEXT_BUTTON_KEY)
    _render_request(
        settings,
        settings.text_effort,
        practice.TEXT_INSTRUCTIONS,
        practice.text_content(found, length, focus),
    )
    if pressed:
        with streamlit.spinner("Claude is writing your practice text…"):
            try:
                state[TEXT_KEY] = practice.write_practice_text(
                    claude_client(), found, length, focus, settings
                )
            except practice.ClaudeError as e:
                streamlit.error(str(e))
    text = state.get(TEXT_KEY)
    if not isinstance(text, practice.PracticeText):
        return
    _render_earlier(text.problems, found)
    if text.unusual:
        streamlit.warning(
            "The text has characters you can't type on a US keyboard: "
            + " ".join(text.unusual)
        )
    streamlit.code(text.text, language=None, wrap_lines=True)
    streamlit.caption(TEXT_BY_CLAUDE)
    streamlit.markdown(_plural(text.word_count, "word"))
    if text.coverage:
        streamlit.dataframe(
            pandas.DataFrame(text.coverage, columns=["word", "times in text"]),
            hide_index=True,
        )
    if text.unused:
        streamlit.caption("Not used: " + ", ".join(text.unused))
    _render_usage(text.usage)


def _grouping() -> practice.Grouping | None:
    grouping = streamlit.session_state.get(GROUPS_KEY)
    return grouping if isinstance(grouping, practice.Grouping) else None


def _render_request(
    settings: practice.Settings,
    effort: practice.Effort,
    instructions: str,
    content: dict[str, Any],
) -> None:
    with streamlit.expander("What Claude gets"):
        fallback = "on" if settings.fallback else "none for this model"
        streamlit.caption(
            f"{settings.model} · effort {effort} · fallback model if Claude "
            f"declines: {fallback} · {settings.timeout:.0f} s per attempt"
        )
        streamlit.caption("Instructions")
        streamlit.code(instructions, language=None, wrap_lines=True)
        streamlit.caption("Data")
        streamlit.code(practice.request_text(content), language="json")


def _render_earlier(made_from: practice.Problems, found: practice.Problems) -> None:
    if made_from != found:
        streamlit.caption(EARLIER_PROBLEMS)


def _render_usage(usage: practice.Usage) -> None:
    streamlit.caption(
        f"{usage.model} used {usage.input_tokens:,} input and "
        f"{usage.output_tokens:,} output tokens."
    )


def _kept(key: str) -> str:
    """The session state key that keeps a widget's value across pages."""
    return f"{key}_kept"


def _load(key: str, default: object, allowed: Collection[object] | None = None) -> None:
    """Loads a widget's kept value, or `default`, before the widget is drawn."""
    kept = streamlit.session_state.get(_kept(key), default)
    usable = allowed is None or kept in allowed
    streamlit.session_state[key] = kept if usable else default


def _keep(key: str) -> dict[str, Any]:
    """Widget arguments that copy each change of the widget to its kept key."""
    return {"key": key, "on_change": _copy_state, "args": (key, _kept(key))}


def _signed(value: float | None) -> str:
    return "–" if value is None else f"{value:+.2f}"


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
