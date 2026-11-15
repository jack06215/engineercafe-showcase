"""Turn JMA's 3-hourly regional forecast (地域時系列予報) into `Hourly` steps. Pure: no I/O."""

import datetime
from typing import Any

from packages.fukuoka_tenki_forcast.model import (
    ForecastError,
    Hourly,
)


def parse_hourly(data: dict[str, Any]) -> tuple[Hourly, ...]:
    """Pair the station's temperatures with the region's weather and wind, by time.

    The station has one more time than the region: its temperature at the end
    of the last 3-hour span. That step gets no weather or wind.
    """
    try:
        area_ts, point_ts = data["areaTimeSeries"], data["pointTimeSeries"]
        spans = {
            _parse_time(time["dateTime"]): (weather, wind)
            for time, weather, wind in zip(
                area_ts["timeDefines"], area_ts["weather"], area_ts["wind"], strict=True
            )
        }
        hours = []
        for time, temp in zip(
            point_ts["timeDefines"], point_ts["temperature"], strict=True
        ):
            at = _parse_time(time["dateTime"])
            weather, wind = spans.get(at, (None, None))
            hours.append(
                Hourly(
                    at=at,
                    temp=None if temp in ("", None) else int(temp),
                    weather=weather or None,
                    wind_direction=wind.get("direction") or None if wind else None,
                    wind_speed=_speed(wind.get("range")) if wind else None,
                )
            )
        return tuple(hours)
    except (LookupError, TypeError, ValueError, AttributeError) as e:
        raise ForecastError(f"3時間ごとの予報の形式が想定と違います: {e!r}") from e


def _parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def _speed(value: str | None) -> tuple[int, int] | None:
    """Turn JMA's "3 5" into (3, 5) m/s."""
    if not value:
        return None
    low, high = value.split()
    return int(low), int(high)
