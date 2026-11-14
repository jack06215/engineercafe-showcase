"""Render the forecast as plain text, for pipes, redirects and `--plain`."""

import datetime
from collections.abc import Sequence

from packages.vibe_coding_club.fukuoka_tenki_forcast.charts import (
    TempScale,
    hourly_chart,
    rain_strip,
    temp_bar,
    week_scale,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.formatting import (
    APP_TITLE,
    CITY_NAME,
    PRODUCT_NAMES,
    day_title,
    format_date,
    format_report,
    normals_text,
    pad,
    rain_summary,
    slot_label,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    DayForecast,
    Forecast,
    Hourly,
    Normals,
    RadarFrame,
    RadarProduct,
    RainPoint,
    WeeklyDay,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.weather_codes import (
    weather_emoji,
    weather_text,
)


def render_text(forecast: Forecast) -> str:
    """Render the detailed forecast and the week ahead as plain terminal text."""
    lines = [f"{APP_TITLE}（{format_report(forecast)}）", ""]
    for day in forecast.days:
        lines.extend(_render_day(day, forecast.reported.date()))
        lines.append("")
    lines.append("■ 7日間の予報（█ 最低〜最高  ░ 予想の幅  ┊ 平年値）")
    scale = week_scale(forecast.weekly, forecast.normals)
    lines.extend(
        _render_weekly_day(day, scale, forecast.normals) for day in forecast.weekly
    )
    if forecast.normals is not None:
        lines.append(f"  {normals_text(forecast.normals)}")
    return "\n".join(lines)


def render_hourly_text(hours: Sequence[Hourly]) -> str:
    lines = ["■ 3時間ごとの予報"]
    lines.extend("  " + line for line in hourly_chart(hours).plain.split("\n"))
    return "\n".join(lines)


def render_rain_text(
    product: RadarProduct, frames: Sequence[RadarFrame], rain: Sequence[RainPoint]
) -> str:
    """How it rains at the station now and ahead, with the strip of rain per frame."""
    lines = [
        f"■ {CITY_NAME}の雨（{PRODUCT_NAMES[product]}）",
        f"  {rain_summary(rain)}",
    ]
    lines.extend("  " + line for line in rain_strip(frames, rain).plain.split("\n"))
    return "\n".join(lines)


def render_unavailable(title: str, reason: str) -> str:
    """A section that could not be loaded: its title and why."""
    return f"■ {title}\n  （{reason}）"


def _render_day(day: DayForecast, today: datetime.date) -> list[str]:
    lines = [
        f"■ {day_title(day.date, today)}",
        f"  {weather_emoji(day.weather_code)} {day.weather}",
    ]
    temps = _format_temps(day.temp_min, day.temp_max)
    if temps:
        lines.append(f"  気温: {temps}")
    if day.pops:
        pops = " / ".join(f"{slot_label(slot)} {slot.pop}%" for slot in day.pops)
        lines.append(f"  降水確率: {pops}")
    wind = f"  風: {day.wind}"
    if day.wave:
        wind += f"  波: {day.wave}"
    lines.append(wind)
    return lines


def _render_weekly_day(
    day: WeeklyDay, scale: TempScale, normals: Normals | None
) -> str:
    code = day.weather_code
    bar = temp_bar(day, scale, normals).plain
    return (
        f"  {format_date(day.date)} {weather_emoji(code)} {pad(weather_text(code), 12)}"
        f" {_temp(day.temp_min):>4} {bar} {_temp(day.temp_max):<4}"
        f"  降水 {_dash(day.pop):>2}%  信頼度 {_dash(day.reliability)}"
    )


def _format_temps(temp_min: int | None, temp_max: int | None) -> str | None:
    parts = []
    if temp_min is not None:
        parts.append(f"最低 {temp_min}℃")
    if temp_max is not None:
        parts.append(f"最高 {temp_max}℃")
    return " / ".join(parts) or None


def _temp(value: int | None) -> str:
    return "-" if value is None else f"{value}℃"


def _dash(value: int | str | None) -> str:
    """Show a missing value as "-". Zero is a value: 0% and 0℃ are shown."""
    return "-" if value is None else str(value)
