"""Wording and alignment shared by the text and TUI views."""

import datetime
import unicodedata
from collections.abc import Sequence

from packages.fukuoka_tenki_forcast.model import (
    Forecast,
    Hourly,
    Normals,
    PopSlot,
    RadarFrame,
    RadarProduct,
    RainPoint,
)
from packages.fukuoka_tenki_forcast.rain_levels import (
    RainLevel,
)

CITY_NAME = "福岡市"
APP_TITLE = f"{CITY_NAME}の天気予報"
WEEKDAYS = "月火水木金土日"
DAY_NAMES = {0: "今日", 1: "明日", 2: "明後日"}
PRODUCT_NAMES = {
    RadarProduct.NOWCAST: "ナウキャスト（1時間先まで）",
    RadarProduct.SHORT_RANGE: "降水短時間予報（15時間先まで）",
}
SOURCE_CREDIT = "出典: 気象庁"


def format_date(date: datetime.date) -> str:
    """Return e.g. "9/12(土)"."""
    return f"{date.month}/{date.day}({WEEKDAYS[date.weekday()]})"


def day_title(date: datetime.date, today: datetime.date) -> str:
    """Return e.g. "9/12(土) 今日", naming the day when it is close to `today`."""
    title = format_date(date)
    day_name = DAY_NAMES.get((date - today).days)
    return f"{title} {day_name}" if day_name else title


def slot_label(slot: PopSlot) -> str:
    """Return e.g. "12-18時"."""
    return f"{slot.hour}-{slot.hour + 6}時"


def format_report(forecast: Forecast) -> str:
    """Return e.g. "福岡管区気象台 2026-09-12 11:00 発表"."""
    return f"{forecast.office} {forecast.reported:%Y-%m-%d %H:%M} 発表"


def normals_text(normals: Normals) -> str:
    """Return e.g. "平年値: 最低 21.6℃ / 最高 28.6℃、7日間の降水量 平年並 9.6〜40.1mm"."""
    return (
        f"平年値: 最低 {normals.temp_min:g}℃ / 最高 {normals.temp_max:g}℃、"
        f"7日間の降水量 平年並 {normals.precip_low:g}〜{normals.precip_high:g}mm"
    )


def clock(at: datetime.datetime, today: datetime.date | None = None) -> str:
    """Return e.g. "18:30", or "13日 3:00" when `at` is not on `today`."""
    time = f"{at.hour}:{at.minute:02}"
    return time if today is None or at.date() == today else f"{at.day}日 {time}"


def wind_text(hour: Hourly) -> str:
    """Return e.g. "南東 3〜5m/s"."""
    speed = f"{hour.wind_speed[0]}〜{hour.wind_speed[1]}m/s" if hour.wind_speed else ""
    return " ".join(part for part in (hour.wind_direction, speed) if part)


def frame_label(frame: RadarFrame, now: RadarFrame) -> str:
    """Return e.g. "18:30 実況" or "19:15 予測（+45分）", relative to the frame `now`."""
    time = clock(frame.at, now.at.date())
    if frame.observed:
        return f"{time} {'実況' if frame.product is RadarProduct.NOWCAST else '解析'}"
    hours, minutes = divmod(round((frame.at - now.at).total_seconds() / 60), 60)
    ahead = (f"{hours}時間" if hours else "") + (f"{minutes}分" if minutes else "")
    return f"{time} 予測（+{ahead or '0分'}）"


def rain_summary(points: Sequence[RainPoint]) -> str:
    """Say how it rains at the station now and what comes next.

    e.g. "いまは降っていません。18:40ごろから降り出す見込み。最も強いときで雨（1〜5mm/h）"
    """
    known = [point for point in points if point.known]
    now = next((point for point in reversed(known) if point.observed), None)
    if now is None:
        return "いまの雨のようすが分かりません"
    today = now.at.date()
    ahead = [point for point in known if not point.observed and point.at > now.at]
    parts = [f"いまは{rain_words(now.level)}" if now.level else "いまは降っていません"]
    if not ahead:
        return parts[0]
    if now.level:
        dry = next((point for point in ahead if point.level is None), None)
        parts.append(
            f"{clock(dry.at, today)}ごろ やむ見込み"
            if dry
            else f"{clock(ahead[-1].at, today)}まで降り続く見込み"
        )
    else:
        wet = next((point for point in ahead if point.level is not None), None)
        parts.append(
            f"{clock(wet.at, today)}ごろから降り出す見込み"
            if wet
            else f"{clock(ahead[-1].at, today)}まで雨の予想はありません"
        )
    heaviest = max(
        (point.level for point in ahead if point.level),
        key=lambda level: level.low,
        default=None,
    )
    if heaviest:
        parts.append(f"最も強いときで{rain_words(heaviest)}")
    return "。".join(parts)


def rain_words(level: RainLevel) -> str:
    """Return e.g. "やや強い雨（10〜20mm/h）"."""
    return f"{level.words}（{level.label}mm/h）"


def display_width(text: str) -> int:
    """Count terminal cells: wide and full-width characters take two."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, width: int) -> str:
    """Pad `text` with spaces to `width` terminal cells."""
    return text + " " * max(width - display_width(text), 0)


def center(text: str, width: int) -> str:
    """Centre `text` in `width` terminal cells."""
    left = max(width - display_width(text), 0) // 2
    return pad(" " * left + text, width)
