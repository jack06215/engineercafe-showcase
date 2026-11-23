import html.parser
import math
import unittest

from packages.monkeytype_analysis_console import fixtures, palette
from packages.monkeytype_analysis_console.history_html import (
    MARK_STYLES,
    SLOW_STYLE,
    band_legend_html,
    history_html,
    word_tooltip,
)
from packages.monkeytype_analysis_console.results import (
    Word,
)


class _Words(html.parser.HTMLParser):
    """Collects each word span of the history: its title, style and letters."""

    def __init__(self) -> None:
        super().__init__()
        self.words: list[dict[str, str]] = []
        self._depth = 0
        self._letters: list[tuple[str, str]] = []
        self._style = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "span":
            return
        self._depth += 1
        values = {name: value or "" for name, value in attrs}
        if self._depth == 1:
            self.words.append(
                {"title": values.get("title", ""), "style": values.get("style", "")}
            )
            self._letters = []
        else:
            self._style = values.get("style", "")

    def handle_endtag(self, tag: str) -> None:
        if tag != "span":
            return
        self._depth -= 1
        if self._depth == 0:
            self.words[-1]["letters"] = "".join(text for text, _ in self._letters)
            self.words[-1]["marked"] = "|".join(
                f"{text}:{style}" for text, style in self._letters if style
            )

    def handle_data(self, data: str) -> None:
        if self._depth == 1:
            self._letters.append((data, ""))
        elif self._depth == 2:
            self._letters.append((data, self._style))


def _words(text: str) -> list[dict[str, str]]:
    parser = _Words()
    parser.feed(text)
    return parser.words


class HistoryHtmlTest(unittest.TestCase):
    def setUp(self) -> None:
        result = fixtures.result(fixtures.TYPOS)
        self.words = _words(history_html(result.words, 40, "wpm"))

    def test_one_span_per_word_in_typed_order(self) -> None:
        self.assertEqual(
            [word["letters"] for word in self.words],
            [
                "on",
                "sneeing",
                "Vec<T>",
                "hello",
                "tests",
                "about",
                "null",
                "they",
                "Python",
                "the",
            ],
        )

    def test_band_colours(self) -> None:
        self.assertIn(f"color: {palette.BANDS[3]}", self.words[0]["style"])
        self.assertIn(f"color: {palette.BANDS[0]}", self.words[1]["style"])
        # "hello" was too fast to measure: no band, so the page's text colour.
        self.assertNotIn("color:", self.words[3]["style"])

    def test_letter_marks(self) -> None:
        self.assertEqual(self.words[1]["marked"], f"n:{MARK_STYLES['f']}")
        self.assertEqual(self.words[4]["marked"], f"s:{MARK_STYLES['+']}")
        self.assertEqual(
            self.words[5]["marked"], f"u:{MARK_STYLES['-']}|t:{MARK_STYLES['-']}"
        )
        self.assertEqual(self.words[7]["marked"], f"e:{MARK_STYLES['x']}")
        self.assertEqual(self.words[0]["marked"], "")

    def test_slow_words_get_an_outline(self) -> None:
        slow = [word["letters"] for word in self.words if SLOW_STYLE in word["style"]]
        self.assertEqual(slow, ["sneeing", "Vec<T>", "about"])

    def test_tooltips(self) -> None:
        self.assertEqual(self.words[1]["title"], "typed: seeeing · 17 wpm · fixed 1")
        self.assertEqual(self.words[3]["title"], "∞ wpm")
        self.assertEqual(self.words[5]["title"], "typed: abo_ · 30 wpm · left wrong")

    def test_text_from_the_file_is_escaped(self) -> None:
        word = Word(
            i=0,
            word="<script>",
            wpm=40,
            bucket=1,
            typed='"><img src=x>',
            marks="x.......",
        )
        text = history_html([word], 0, "wpm")
        self.assertNotIn("<script", text)
        self.assertNotIn("<img", text)
        parsed = _words(text)[0]
        self.assertEqual(parsed["letters"], "<script>")
        self.assertEqual(parsed["title"], 'typed: "><img src=x> · 40 wpm')


class WordTooltipTest(unittest.TestCase):
    def test_only_what_the_word_has(self) -> None:
        self.assertEqual(
            word_tooltip(Word(i=0, word="a", wpm=None, bucket=None), "wpm"), ""
        )
        word = Word(i=0, word="a", wpm=math.inf, bucket=None, fixed=2, error=True)
        self.assertEqual(word_tooltip(word, "cpm"), "∞ cpm · fixed 2 · left wrong")


class BandLegendTest(unittest.TestCase):
    def test_labels_and_colours(self) -> None:
        text = band_legend_html([0, 37, 70, 92, 127])
        for colour in palette.BANDS:
            self.assertIn(colour, text)
        self.assertIn("&lt;37", text)
        self.assertIn("127+", text)

    def test_empty_without_steps(self) -> None:
        self.assertEqual(band_legend_html([]), "")


if __name__ == "__main__":
    unittest.main()
