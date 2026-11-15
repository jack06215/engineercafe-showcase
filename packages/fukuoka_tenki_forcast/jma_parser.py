"""Turn the JMA forecast JSON into a `Forecast`. Pure: no I/O."""

import datetime
import unicodedata
from collections.abc import Sequence
from typing import Any

from packages.fukuoka_tenki_forcast.area import Area
from packages.fukuoka_tenki_forcast.model import (
    DayForecast,
    Forecast,
    ForecastError,
    Normals,
    PopSlot,
    TempRange,
    WeeklyDay,
)


def parse_forecast(data: list[dict[str, Any]], area: Area) -> Forecast:
    """Pick `area` out of the forecast JSON, raising ForecastError if it is malformed."""
    try:
        days = parse_short_term(data, area)
        return Forecast(
            office=data[0]["publishingOffice"],
            reported=_parse_time(data[0]["reportDatetime"]),
            days=days,
            weekly=parse_weekly(data, area, days),
            normals=parse_normals(data, area),
        )
    except (LookupError, TypeError, ValueError) as e:
        raise ForecastError(f"天気予報の形式が想定と違います: {e!r}") from e


def find_area(time_series: dict[str, Any], code: str) -> dict[str, Any]:
    """Return the entry of `time_series["areas"]` whose area code is `code`."""
    for area in time_series["areas"]:
        if area["area"]["code"] == code:
            result: dict[str, Any] = area
            return result
    raise LookupError(f"area code {code} not found in forecast")


def parse_short_term(data: list[dict[str, Any]], area: Area) -> tuple[DayForecast, ...]:
    """Collect the 3-day detailed forecast, one entry per day."""
    today = _parse_time(data[0]["reportDatetime"]).date()
    weather_ts, pop_ts, temp_ts = data[0]["timeSeries"][:3]

    pops: dict[datetime.date, list[PopSlot]] = {}
    pop_area = find_area(pop_ts, area.region)
    for time_define, pop in zip(pop_ts["timeDefines"], pop_area["pops"], strict=True):
        start = _parse_time(time_define)
        if pop:
            pops.setdefault(start.date(), []).append(PopSlot(start.hour, int(pop)))

    # Temperatures are keyed by time, not position: 00:00 is the minimum and
    # 09:00 the maximum, and the order of timeDefines varies by report time.
    temps: dict[tuple[datetime.date, int], int] = {}
    temp_area = find_area(temp_ts, area.station)
    for time_define, temp in zip(
        temp_ts["timeDefines"], temp_area["temps"], strict=True
    ):
        at = _parse_time(time_define)
        if temp:
            temps[(at.date(), at.hour)] = int(temp)

    weather_area = find_area(weather_ts, area.region)
    waves = weather_area.get("waves", [])
    days = []
    for i, time_define in enumerate(weather_ts["timeDefines"]):
        date = _parse_time(time_define).date()
        days.append(
            DayForecast(
                date=date,
                weather_code=weather_area["weatherCodes"][i],
                weather=_normalize(weather_area["weathers"][i]),
                wind=_normalize(weather_area["winds"][i]),
                wave=_normalize(waves[i]) if i < len(waves) else None,
                # This morning's minimum is already past (and often just a
                # copy of the maximum), so only show it from tomorrow on.
                temp_min=temps.get((date, 0)) if date != today else None,
                temp_max=temps.get((date, 9)),
                pops=tuple(pops.get(date, [])),
            )
        )
    return tuple(days)


# temp_min, temp_max and their likely ranges, for one day of the weekly forecast.
_WeeklyTemps = tuple[int | None, int | None, TempRange | None, TempRange | None]


def parse_weekly(
    data: list[dict[str, Any]], area: Area, details: Sequence[DayForecast] = ()
) -> tuple[WeeklyDay, ...]:
    """Collect the weekly forecast: weather for the region, temperatures for the station.

    JMA leaves the first day's temperatures blank because the detailed forecast
    covers that day; they are taken from `details` instead.
    """
    weather_ts, temp_ts = data[1]["timeSeries"][:2]
    weather_area = find_area(weather_ts, area.weekly_region)
    temp_area = find_area(temp_ts, area.station)

    temps: dict[datetime.date, _WeeklyTemps] = {}
    for i, time_define in enumerate(temp_ts["timeDefines"]):
        temps[_parse_time(time_define).date()] = (
            _int_or_none(temp_area["tempsMin"][i]),
            _int_or_none(temp_area["tempsMax"][i]),
            _temp_range(temp_area, "tempsMin", i),
            _temp_range(temp_area, "tempsMax", i),
        )
    detailed = {day.date: day for day in details}

    days = []
    for i, time_define in enumerate(weather_ts["timeDefines"]):
        date = _parse_time(time_define).date()
        temp_min, temp_max, min_range, max_range = temps.get(
            date, (None, None, None, None)
        )
        if (detail := detailed.get(date)) is not None:
            temp_min = detail.temp_min if temp_min is None else temp_min
            temp_max = detail.temp_max if temp_max is None else temp_max
        days.append(
            WeeklyDay(
                date=date,
                weather_code=weather_area["weatherCodes"][i],
                pop=_int_or_none(weather_area["pops"][i]),
                temp_min=temp_min,
                temp_max=temp_max,
                reliability=weather_area["reliabilities"][i] or None,
                temp_min_range=min_range,
                temp_max_range=max_range,
            )
        )
    return tuple(days)


def parse_normals(data: list[dict[str, Any]], area: Area) -> Normals | None:
    """Read the week's climate normals at the station, if the JSON has them."""
    weekly = data[1]
    if "tempAverage" not in weekly or "precipAverage" not in weekly:
        return None
    temp = find_area(weekly["tempAverage"], area.station)
    precip = find_area(weekly["precipAverage"], area.station)
    return Normals(
        temp_min=float(temp["min"]),
        temp_max=float(temp["max"]),
        precip_low=float(precip["min"]),
        precip_high=float(precip["max"]),
    )


def _temp_range(temp_area: dict[str, Any], key: str, i: int) -> TempRange | None:
    """Return the likely range of `key` ("tempsMin" or "tempsMax") on day `i`."""
    lowers, uppers = temp_area.get(key + "Lower"), temp_area.get(key + "Upper")
    if lowers is None or uppers is None:
        return None
    lower, upper = _int_or_none(lowers[i]), _int_or_none(uppers[i])
    if lower is None or upper is None:
        return None
    return TempRange(lower, upper)


def _normalize(text: str) -> str:
    """Turn full-width digits and spaces into half-width ones."""
    return unicodedata.normalize("NFKC", text)


def _parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def _int_or_none(value: str) -> int | None:
    """JMA leaves a blank "" where it has no value yet."""
    return int(value) if value else None
