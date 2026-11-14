"""JMA weather codes: their wording, representative weather and emoji."""

# Subset of TELOPS in https://www.jma.go.jp/bosai/forecast/js/forecast_const.js:
# code -> (日本語, 代表天気).
TELOPS: dict[str, tuple[str, str]] = {
    "100": ("晴", "100"),
    "101": ("晴時々曇", "100"),
    "102": ("晴一時雨", "300"),
    "110": ("晴後時々曇", "100"),
    "111": ("晴後曇", "100"),
    "200": ("曇", "200"),
    "201": ("曇時々晴", "200"),
    "202": ("曇一時雨", "300"),
    "203": ("曇時々雨", "300"),
    "210": ("曇後時々晴", "200"),
    "211": ("曇後晴", "200"),
    "212": ("曇後一時雨", "300"),
    "213": ("曇後時々雨", "300"),
    "214": ("曇後雨", "300"),
    "300": ("雨", "300"),
    "301": ("雨時々晴", "300"),
    "302": ("雨時々止む", "300"),
    "311": ("雨後晴", "300"),
    "313": ("雨後曇", "300"),
    "400": ("雪", "400"),
}

EMOJI = {"100": "☀️", "200": "☁️", "300": "☔", "400": "⛄"}


def weather_category(code: str) -> str:
    """Return the representative weather: "100" sunny, "200" cloudy, and so on."""
    if code in TELOPS:
        return TELOPS[code][1]
    return code[:1] + "00"


def weather_emoji(code: str) -> str:
    return EMOJI.get(weather_category(code), "❓")


def weather_text(code: str) -> str:
    return TELOPS[code][0] if code in TELOPS else f"天気コード {code}"


def weather_label(code: str) -> str:
    """Return e.g. "☔ 曇時々雨" for a JMA weather code."""
    return f"{weather_emoji(code)} {weather_text(code)}"


def word_kanji(word: str) -> tuple[str, str]:
    """Shorten a word of the 3-hourly forecast, e.g. "くもり", to ("曇", "200").

    Those words are 晴れ, くもり, 雨, 雨または雪 and 雪. The second item is the
    representative weather, as for the codes above.
    """
    if "雪" in word:
        return ("雨雪", "400") if "雨" in word else ("雪", "400")
    if "雨" in word:
        return "雨", "300"
    if "くもり" in word or "曇" in word:
        return "曇", "200"
    if "晴" in word:
        return "晴", "100"
    return "?", ""
