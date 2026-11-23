"""The input history as HTML, coloured by heatmap band (SPEC.md §6.6).

Every word, letter and tooltip comes from a file, so all of it is escaped.
Styles are inline attributes, which `st.html` keeps; it runs no JavaScript.
"""

import html
from collections.abc import Sequence

from packages.monkeytype_analysis_console import palette
from packages.monkeytype_analysis_console.metrics import (
    band_labels,
    format_number,
    is_slow,
)
from packages.monkeytype_analysis_console.results import (
    Word,
)

MARK_STYLES = {
    "f": (
        f"text-decoration: underline {palette.ERROR} 2px; text-underline-offset: 3px"
    ),
    "x": f"color: {palette.ERROR}",
    "+": f"color: {palette.ERROR}; text-decoration: line-through",
    "-": "opacity: 0.4",
}
SLOW_STYLE = "outline: 1px dotted currentColor; outline-offset: 2px"

_CONTAINER_STYLE = (
    "display: flex; flex-wrap: wrap; gap: 0.3em 0.75em; "
    "font-family: monospace; font-size: 1.15rem; line-height: 1.7"
)
_LEGEND_STYLE = "display: flex; flex-wrap: wrap; gap: 0.25em 1.25em"


def history_html(words: Sequence[Word], threshold: float, unit: str) -> str:
    """The words in typed order, each in its band colour.

    A slow word (below `threshold`) gets a dotted outline, and hovering a word
    shows `word_tooltip`.
    """
    spans = "".join(_word_html(word, threshold, unit) for word in words)
    return f'<div style="{_CONTAINER_STYLE}">{spans}</div>'


def word_tooltip(word: Word, unit: str) -> str:
    """The text shown when hovering a word, before escaping."""
    parts = []
    if word.typed is not None:
        parts.append(f"typed: {word.typed}")
    if word.wpm is not None:
        parts.append(f"{format_number(word.wpm)} {unit}")
    if word.fixed:
        parts.append(f"fixed {word.fixed}")
    if word.error:
        parts.append("left wrong")
    return " · ".join(parts)


def band_legend_html(steps: Sequence[float]) -> str:
    """A swatch and the label of each heatmap band, or "" without bands."""
    items = [
        f'<span><span style="color: {colour}">■</span> {html.escape(label)}</span>'
        for colour, label in zip(palette.BANDS, band_labels(steps), strict=False)
    ]
    if not items:
        return ""
    return f'<div style="{_LEGEND_STYLE}">{"".join(items)}</div>'


def _word_html(word: Word, threshold: float, unit: str) -> str:
    styles = []
    if word.bucket is not None and 0 <= word.bucket < len(palette.BANDS):
        styles.append(f"color: {palette.BANDS[word.bucket]}")
    if is_slow(word, threshold):
        styles.append(SLOW_STYLE)
    shown = word.letters if word.letters is not None else word.word
    marks = word.marks or ""
    letters = "".join(
        _letter_html(letter, marks[i] if i < len(marks) else ".")
        for i, letter in enumerate(shown)
    )
    title = html.escape(word_tooltip(word, unit), quote=True)
    return f'<span title="{title}" style="{"; ".join(styles)}">{letters}</span>'


def _letter_html(letter: str, mark: str) -> str:
    text = html.escape(letter, quote=True)
    style = MARK_STYLES.get(mark)
    return f'<span style="{style}">{text}</span>' if style else text
