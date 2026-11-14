"""Which language Algo-chan writes in (SPEC §12.2).

Text with any Hiragana or Katakana is Japanese; everything else, including
empty text, is English. Kanji alone doesn't count: it's shared with Chinese,
and Jack's English notes may quote a kanji term.
"""

from typing import Literal

OutputLanguage = Literal["English", "Japanese"]

# Hiragana, Katakana, Katakana Phonetic Extensions, half-width Katakana.
_KANA = ((0x3041, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F))


def has_kana(text: str) -> bool:
    """Return whether *text* contains hiragana or katakana."""
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in _KANA)


def detect(text: str) -> OutputLanguage:
    """Return Japanese if *text* contains kana, else English."""
    return "Japanese" if has_kana(text) else "English"


def for_report(notes: str, takeaway: str | None) -> OutputLanguage:
    """A report follows the attempt's notes and takeaway."""
    return detect(f"{notes}\n{takeaway or ''}")


def for_hint(latest_message: str, notes: str) -> OutputLanguage:
    """The language of a hint: that of the learner's latest message.

    A blank message falls back to the attempt's notes.
    """
    return detect(latest_message if latest_message.strip() else notes)


def pin(language: OutputLanguage) -> str:
    """The language line that every prompt carries.

    qwen3.6 switched language unprompted in an earlier test.
    """
    return f"Write every field in {language}."
