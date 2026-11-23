"""Altair charts of one result (SPEC.md §6.5).

The speed chart copies Monkeytype's: wpm, raw and burst share the left axis,
and errors have their own on the right. Clicking a legend entry adds that
series to the ones shown, and clicking it again removes it; with none picked,
every series shows.
"""

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

import altair
import pandas

from packages.monkeytype_analysis_console import palette
from packages.monkeytype_analysis_console.metrics import (
    band_labels,
    finite_speed,
    format_number,
    previous_pb,
)
from packages.monkeytype_analysis_console.results import (
    Result,
    Word,
)
from packages.monkeytype_analysis_console.typos import (
    KEY_POSITIONS,
    ROWS,
)

SERIES = ("wpm", "raw", "burst", "errors")
SERIES_COLOURS = (palette.MAIN, palette.MAIN, palette.SUB, palette.ERROR)
LEGEND_PARAM = "shown_series"
HOVER_PARAM = "hovered_second"
SPEED_HEIGHT = 320
WORD_HEIGHT = 220
KEYBOARD_HEIGHT = 200
# A key's size in key widths; the rest of each key width is the gap.
KEY_SIZE = 0.9
# Dark text reads on every key colour: they all have a mid luminance (§6.7).
KEY_LABEL_COLOUR = "#111111"

_TOOLTIP = [
    altair.Tooltip("t:Q", title="second"),
    *(altair.Tooltip(f"{name}:Q") for name in SERIES),
]


def speed_chart(result: Result) -> altair.LayerChart | None:
    """The per-second chart, or None when the result has no chart rows."""
    if not result.chart:
        return None
    wide = pandas.DataFrame([dataclasses.asdict(row) for row in result.chart])
    long = wide.melt(
        id_vars="t", value_vars=list(SERIES), var_name="series", value_name="value"
    ).dropna(subset=["value"])
    # Each legend click adds or removes a series. Vega-Lite's default (a click
    # replaces the selection, a double-click clears it) gave no way back to all
    # series in Streamlit's chart.
    shown = altair.selection_point(
        name=LEGEND_PARAM, fields=["series"], bind="legend", toggle="true"
    )
    hovered = altair.selection_point(
        name=HOVER_PARAM,
        fields=["t"],
        nearest=True,
        on="pointerover",
        clear="pointerout",
        empty=False,
    )
    x = altair.X("t:Q", title="seconds")
    colour = altair.Color(
        "series:N",
        scale=altair.Scale(domain=list(SERIES), range=list(SERIES_COLOURS)),
        legend=altair.Legend(title=None, orient="top"),
    )
    speed_y = altair.Y("value:Q", title=result.unit)
    series = altair.Chart(long).encode(x=x, color=colour)

    def one(name: str) -> altair.Chart:
        return series.transform_filter(altair.datum.series == name)

    # The legend belongs to the first view with a colour, so the legend-bound
    # param must be defined there: on any other view, clicks do nothing.
    speed_layers: list[altair.Chart | altair.LayerChart] = [
        one("burst")
        .mark_area(line=True, fillOpacity=0.15)
        .encode(y=speed_y, opacity=_shown_when(shown, 1))
        .add_params(shown),
        one("raw")
        .mark_line(strokeDash=[6, 4], strokeWidth=2)
        .encode(y=speed_y, opacity=_shown_when(shown, 0.6)),
        one("wpm")
        .mark_line(strokeWidth=3)
        .encode(y=speed_y, opacity=_shown_when(shown, 1)),
    ]
    pb = previous_pb(result)
    if pb is not None:
        speed_layers.append(_pb_line(pb, result.unit))
    # Invisible points in a row find the nearest second by x alone, and the
    # rule shows which second it is. Neither has a y field, so they add no
    # axis. They sit in the outer layer: Altair gives a param defined inside
    # the nested speed layer every named view of that layer.
    hover_points = (
        altair.Chart(wide)
        .mark_point()
        .encode(x=x, y=altair.value(0), opacity=altair.value(0), tooltip=_TOOLTIP)
        .add_params(hovered)
    )
    hover_rule = (
        altair.Chart(wide)
        .mark_rule(color=palette.SUB)
        .encode(
            x=x,
            opacity=altair.when(hovered)
            .then(altair.value(0.5))
            .otherwise(altair.value(0)),
            tooltip=_TOOLTIP,
        )
    )
    errors = (
        one("errors")
        .transform_filter(altair.datum.value > 0)
        .mark_point(filled=True, size=60)
        .encode(
            y=altair.Y(
                "value:Q",
                title="errors",
                axis=altair.Axis(orient="right", tickMinStep=1),
                scale=altair.Scale(domainMin=0),
            ),
            opacity=_shown_when(shown, 1),
        )
    )
    return altair.LayerChart(
        layer=[altair.LayerChart(layer=speed_layers), errors, hover_points, hover_rule],
        height=SPEED_HEIGHT,
    ).resolve_scale(y="independent")


def word_speed_chart(
    words: Sequence[Word], steps: Sequence[float], threshold: float, unit: str
) -> altair.LayerChart | None:
    """One bar per word with a finite speed, and a line at the threshold.

    Returns None when no word has a finite speed.
    """
    labels = band_labels(steps)
    rows = []
    for word in words:
        speed = finite_speed(word)
        if speed is None:
            continue
        band = word.bucket
        colour, label = palette.SUB, ""
        if band is not None and 0 <= band < len(palette.BANDS):
            colour = palette.BANDS[band]
            label = labels[band] if band < len(labels) else ""
        rows.append(
            {
                "i": word.i,
                "word": word.word,
                "speed": speed,
                "band": label,
                "colour": colour,
                "typed": word.typed or "",
                "fixed": word.fixed,
            }
        )
    if not rows:
        return None
    y_title = unit
    bars = (
        altair.Chart(pandas.DataFrame(rows))
        .mark_bar()
        .encode(
            x=altair.X(
                "i:O",
                title="word",
                axis=altair.Axis(labelAngle=0, labelOverlap="greedy"),
            ),
            y=altair.Y("speed:Q", title=y_title),
            color=altair.Color("colour:N", scale=None),
            tooltip=[
                altair.Tooltip("word:N"),
                altair.Tooltip("speed:Q", title=unit),
                altair.Tooltip("band:N"),
                altair.Tooltip("typed:N", title="first attempt"),
                altair.Tooltip("fixed:Q", title="letters fixed"),
            ],
        )
    )
    threshold_line = (
        altair.Chart(pandas.DataFrame({"threshold": [threshold]}))
        .mark_rule(strokeDash=[4, 4], color=palette.SUB)
        .encode(
            y=altair.Y("threshold:Q", title=y_title),
            tooltip=[altair.Tooltip("threshold:Q", title="slow below")],
        )
    )
    return altair.LayerChart(layer=[bars, threshold_line], height=WORD_HEIGHT)


def keyboard_chart(
    confusions_by_key: Mapping[str, Mapping[str, int]],
) -> altair.LayerChart:
    """The QWERTY keys, coloured by how often each was the wanted key of a wrong key.

    `confusions_by_key` maps a base key to its expected→typed pairs and their
    counts, as `typos.wrong_keys` returns them. Keys with no typos are grey.
    """
    rows = []
    for key, (x, row) in KEY_POSITIONS.items():
        confusions = confusions_by_key.get(key, {})
        ranked = sorted(confusions.items(), key=lambda item: (-item[1], item[0]))
        rows.append(
            {
                "key": key,
                "x": x,
                "x2": x + KEY_SIZE,
                "centre": x + KEY_SIZE / 2,
                "row": row,
                "row2": row + KEY_SIZE,
                "middle": row + KEY_SIZE / 2,
                "count": sum(confusions.values()),
                "confusions": ", ".join(f"{pair} ×{n}" for pair, n in ranked),
            }
        )
    data = pandas.DataFrame(rows)
    most = max(1, int(data["count"].max()))
    width = max(x + KEY_SIZE for x, _ in KEY_POSITIONS.values())
    x_scale = altair.Scale(domain=[0, width], nice=False)
    y_scale = altair.Scale(domain=[0, len(ROWS)], reverse=True, nice=False)
    tooltip = [
        altair.Tooltip("key:N"),
        altair.Tooltip("count:Q", title="wrong-key typos"),
        altair.Tooltip("confusions:N", title="expected→typed"),
    ]
    keys = (
        altair.Chart(data)
        .mark_rect(cornerRadius=4)
        .encode(
            x=altair.X("x:Q", axis=None, scale=x_scale),
            x2="x2:Q",
            y=altair.Y("row:Q", axis=None, scale=y_scale),
            y2="row2:Q",
            color=altair.Color(
                "count:Q",
                scale=altair.Scale(
                    domain=[0, most], range=[palette.SUB, palette.ERROR]
                ),
                legend=altair.Legend(title="wrong-key typos", tickMinStep=1),
            ),
            tooltip=tooltip,
        )
    )
    labels = (
        altair.Chart(data)
        .mark_text(color=KEY_LABEL_COLOUR, fontSize=14)
        .encode(
            x=altair.X("centre:Q", axis=None, scale=x_scale),
            y=altair.Y("middle:Q", axis=None, scale=y_scale),
            text="key:N",
            tooltip=tooltip,
        )
    )
    return altair.LayerChart(layer=[keys, labels], height=KEYBOARD_HEIGHT)


PROGRESS_HEIGHT = 240
PROGRESS_MEASURES = ("wpm", "acc")


def progress_chart(
    results: Sequence[Result], measure: str, goal: float | None = None
) -> altair.LayerChart:
    """One measure (`wpm` or `acc`) of results over time, PBs marked.

    With a goal, a dashed line shows it. The results should be one trend
    group, so the speeds are comparable.
    """
    if measure not in PROGRESS_MEASURES:
        raise ValueError(f"measure must be one of {PROGRESS_MEASURES}: {measure!r}")
    rows = [
        {
            "when": result.copied_at.isoformat(),
            "test": result.test,
            "wpm": result.wpm,
            "acc": result.acc,
            "consistency": result.consistency,
            "file": result.source,
            "kind": "PB" if result.pb else "result",
        }
        for result in results
    ]
    data = pandas.DataFrame(rows)
    x = altair.X("when:T", title=None)
    y = altair.Y(f"{measure}:Q", title=measure, scale=altair.Scale(zero=False))
    line = altair.Chart(data).mark_line(color=palette.MAIN).encode(x=x, y=y)
    points = (
        altair.Chart(data)
        .mark_point(filled=True, size=80, color=palette.MAIN, opacity=1)
        .encode(
            x=x,
            y=y,
            shape=altair.Shape(
                "kind:N",
                scale=altair.Scale(
                    domain=["result", "PB"], range=["circle", "diamond"]
                ),
                legend=altair.Legend(title=None, orient="top"),
            ),
            tooltip=[
                altair.Tooltip("when:T", title="copied", format="%Y-%m-%d %H:%M"),
                altair.Tooltip("test:N"),
                altair.Tooltip("wpm:Q"),
                altair.Tooltip("acc:Q"),
                altair.Tooltip("consistency:Q"),
                altair.Tooltip("file:N"),
            ],
        )
    )
    layers: list[altair.Chart] = [line, points]
    if goal is not None:
        layers.append(
            altair.Chart(pandas.DataFrame({"goal": [goal]}))
            .mark_rule(strokeDash=[4, 4], color=palette.SUB)
            .encode(
                y=altair.Y("goal:Q", title=measure),
                tooltip=[altair.Tooltip("goal:Q", title="goal")],
            )
        )
    return altair.LayerChart(layer=layers, height=PROGRESS_HEIGHT)


def _shown_when(shown: altair.Parameter, opacity: float) -> Any:
    return altair.when(shown).then(altair.value(opacity)).otherwise(altair.value(0))


def _pb_line(pb: float, unit: str) -> altair.LayerChart:
    data = pandas.DataFrame({"pb": [pb], "label": [f"previous PB {format_number(pb)}"]})
    rule = altair.Chart(data).mark_rule(strokeDash=[2, 4], color=palette.SUB)
    label = altair.Chart(data).mark_text(
        align="left", baseline="bottom", dx=4, dy=-2, color=palette.SUB
    )
    y = altair.Y("pb:Q", title=unit)
    return altair.LayerChart(
        layer=[
            rule.encode(y=y),
            label.encode(y=y, x=altair.value(0), text="label:N"),
        ]
    )
