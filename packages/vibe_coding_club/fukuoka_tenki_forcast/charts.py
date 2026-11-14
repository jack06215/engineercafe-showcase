"""Charts drawn with characters, for both the TUI and plain text. Pure: data in, Text out.

Colour carries extra meaning in the TUI but never the only meaning: printed as
plain text, every chart still reads by the shape of its blocks.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

from rich.text import Text

from packages.vibe_coding_club.fukuoka_tenki_forcast.formatting import (
    center,
    clock,
    display_width,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    Hourly,
    Normals,
    RadarFrame,
    RadarProduct,
    RainPoint,
    WeeklyDay,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.weather_codes import (
    word_kanji,
)

BAR = "█"
BAND = "░"
NORMAL = "┊"
# Eighths of a cell, from empty to full, for bars that grow upwards.
LEVELS = " ▁▂▃▄▅▆▇█"
CATEGORY_COLORS = {
    "100": "orange1",
    "200": "grey70",
    "300": "dodger_blue1",
    "400": "white",
}
# Temperature (℃) to colour: blue when cold, through green and yellow, to red.
_TEMP_STOPS = (
    (0.0, (90, 130, 255)),
    (10.0, (80, 200, 255)),
    (18.0, (110, 215, 140)),
    (24.0, (250, 215, 70)),
    (30.0, (255, 130, 40)),
    (35.0, (235, 45, 60)),
)


def temp_color(temp: float) -> str:
    """Return the colour for `temp` as "#rrggbb", blending between the stops."""
    if temp <= _TEMP_STOPS[0][0]:
        return _hex(_TEMP_STOPS[0][1])
    for (t0, c0), (t1, c1) in itertools.pairwise(_TEMP_STOPS):
        if temp <= t1:
            f = (temp - t0) / (t1 - t0)
            return _hex(
                tuple(round(a + (b - a) * f) for a, b in zip(c0, c1, strict=True))
            )
    return _hex(_TEMP_STOPS[-1][1])


@dataclass(frozen=True)
class TempScale:
    """Maps temperatures from `low` to `high` ℃ onto a bar `width` cells wide."""

    low: int
    high: int
    width: int

    def cell(self, temp: float) -> int:
        position = (temp - self.low) / max(self.high - self.low, 1) * (self.width - 1)
        return min(max(round(position), 0), self.width - 1)

    def temp(self, cell: int) -> float:
        return self.low + cell / max(self.width - 1, 1) * (self.high - self.low)


def week_scale(
    days: Sequence[WeeklyDay], normals: Normals | None, width: int = 24
) -> TempScale:
    """One scale for the whole week, wide enough for its every temperature and range."""
    temps: list[float] = []
    for day in days:
        temps += [t for t in (day.temp_min, day.temp_max) if t is not None]
        for likely in (day.temp_min_range, day.temp_max_range):
            if likely is not None:
                temps += [likely.lower, likely.upper]
    if normals is not None:
        temps += [normals.temp_min, normals.temp_max]
    if not temps:
        return TempScale(0, 30, width)
    return TempScale(math.floor(min(temps)) - 1, math.ceil(max(temps)) + 1, width)


def temp_bar(day: WeeklyDay, scale: TempScale, normals: Normals | None = None) -> Text:
    """The day's temperatures on `scale`.

    █ runs from the forecast minimum to the maximum, ░ out to the likely range
    of each (予想の幅), and ┊ marks the normal minimum and maximum.
    """
    cells = [Text(" ")] * scale.width
    if normals is not None:
        for normal in (normals.temp_min, normals.temp_max):
            cells[scale.cell(normal)] = Text(NORMAL, style="grey50")
    known = [t for t in (day.temp_min, day.temp_max) if t is not None]
    if known:
        low = min(known + ([day.temp_min_range.lower] if day.temp_min_range else []))
        high = max(known + ([day.temp_max_range.upper] if day.temp_max_range else []))
        for cell in range(scale.cell(low), scale.cell(high) + 1):
            cells[cell] = Text(BAND, style="grey42")
        for cell in range(scale.cell(min(known)), scale.cell(max(known)) + 1):
            cells[cell] = Text(BAR, style=temp_color(scale.temp(cell)))
    return Text.assemble(*cells)


def hourly_chart(hours: Sequence[Hourly], column: int = 6, bar_rows: int = 3) -> Text:
    """The 3-hourly forecast as columns: time, weather, temperature and a bar, wind.

    Midnight is labelled with the date instead of "0時".
    """
    temps = [hour.temp for hour in hours if hour.temp is not None]
    low, high = (min(temps), max(temps)) if temps else (0, 0)
    rows = [Text() for _ in range(5 + bar_rows)]
    for hour in hours:
        midnight = hour.at.hour == 0
        label = f"{hour.at.month}/{hour.at.day}" if midnight else f"{hour.at.hour}時"
        rows[0].append(center(label, column), style="bold" if midnight else "")
        kanji, category = word_kanji(hour.weather) if hour.weather else ("", "")
        rows[1].append(center(kanji, column), style=CATEGORY_COLORS.get(category, ""))
        if hour.temp is None:
            rows[2].append(center("-", column), style="dim")
        else:
            rows[2].append(center(f"{hour.temp}℃", column), style=temp_color(hour.temp))
        for row, cell in enumerate(_column_bar(hour.temp, low, high, bar_rows)):
            style = temp_color(hour.temp) if hour.temp is not None else ""
            rows[3 + row].append(center(cell * (column - 2), column), style=style)
        rows[3 + bar_rows].append(center(hour.wind_direction or "", column))
        speed = f"{hour.wind_speed[0]}-{hour.wind_speed[1]}m" if hour.wind_speed else ""
        rows[4 + bar_rows].append(center(speed, column), style="dim")
    return Text("\n").join(rows)


def rain_strip(
    frames: Sequence[RadarFrame],
    rain: Sequence[RainPoint] | None,
    cursor: int | None = None,
    cell: int = 2,
) -> Text:
    """The rain at the station, one `cell`-wide column per frame, over a time ruler.

    A column's height and colour follow JMA's legend: ▁ is under 1 mm/h and █
    80 mm/h or more; · is dry, and blank not known yet. Forecast columns sit on
    a darker ground than observed ones. With a `cursor`, ▼ marks that frame.
    """
    levels = {point.at: point for point in rain or ()}
    marker = Text()
    strip = Text()
    for i, frame in enumerate(frames):
        marker.append(center("▼", cell) if i == cursor else " " * cell, style="bold")
        ground = "" if frame.observed else " on grey15"
        point = levels.get(frame.at)
        if point is None or not point.known:
            strip.append(" " * cell, style=ground.strip())
        elif point.level is None:
            strip.append(center("·", cell), style="grey42" + ground)
        else:
            height = LEVELS[1 + RAIN_LEVELS.index(point.level)]
            strip.append(height * cell, style=_hex(point.level.color) + ground)
    rows = [strip, _ruler(frames, cell)]
    if cursor is not None:
        rows.insert(0, marker)
    return Text("\n").join(rows)


def _ruler(frames: Sequence[RadarFrame], cell: int) -> Text:
    """Times under the frames that fall on the half hour (nowcast) or on every
    third hour (15-hour forecast), where they fit without overlapping."""
    ruler = ""
    today = frames[0].at.date() if frames else None
    for i, frame in enumerate(frames):
        at = frame.at
        if frame.product is RadarProduct.NOWCAST:
            wanted = at.minute in (0, 30)
        else:
            wanted = at.minute == 0 and at.hour % 3 == 0
        used = display_width(ruler)
        if wanted and used <= i * cell:
            ruler += " " * (i * cell - used) + clock(at, today) + " "
    return Text(ruler.rstrip(), style="grey62")


def _column_bar(temp: int | None, low: int, high: int, rows: int) -> list[str]:
    """A bar `rows` cells tall, top row first, as high as `temp` sits in low..high."""
    if temp is None:
        return [" "] * rows
    fraction = (temp - low) / (high - low) if high > low else 0.5
    eighths = 1 + round(fraction * (rows * 8 - 1))
    return [
        LEVELS[min(max(eighths - (rows - 1 - row) * 8, 0), 8)] for row in range(rows)
    ]


def _hex(rgb: tuple[int, ...]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)
