"""The forecast as the rest of the app sees it, independent of the JMA JSON."""

import datetime
import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    RainLevel,
)


class ForecastError(Exception):
    """The forecast could not be fetched or parsed; the message is user-facing."""


@dataclass(frozen=True)
class PopSlot:
    """Probability of precipitation for the six hours starting at `hour`."""

    hour: int
    pop: int


@dataclass(frozen=True)
class DayForecast:
    """One day of the detailed forecast, which covers today to the day after tomorrow."""

    date: datetime.date
    weather_code: str
    weather: str  # JMA's wording, e.g. "くもり 時々 雨"
    wind: str
    wave: str | None
    temp_min: int | None  # None for today: this morning's minimum is already past
    temp_max: int | None
    pops: tuple[PopSlot, ...]  # only the slots after the report time


@dataclass(frozen=True)
class TempRange:
    """How far JMA expects a weekly temperature may land from its forecast (予想の幅)."""

    lower: int
    upper: int


@dataclass(frozen=True)
class WeeklyDay:
    """One day of the weekly forecast, which runs from tomorrow for seven days."""

    date: datetime.date
    weather_code: str
    pop: int | None
    temp_min: int | None
    temp_max: int | None
    reliability: str | None  # "A", "B" or "C"
    temp_min_range: TempRange | None = None
    temp_max_range: TempRange | None = None


@dataclass(frozen=True)
class Normals:
    """Climate normals for the week at the station (平年値)."""

    temp_min: float
    temp_max: float
    precip_low: float  # the "near normal" range of the week's total rainfall, in mm
    precip_high: float


@dataclass(frozen=True)
class Forecast:
    """One report: three days in detail, then the week ahead."""

    office: str  # publishing office, e.g. "福岡管区気象台"
    reported: datetime.datetime
    days: tuple[DayForecast, ...]
    weekly: tuple[WeeklyDay, ...]
    normals: Normals | None = None


@dataclass(frozen=True)
class Hourly:
    """One step of the 3-hourly forecast for the region and its station."""

    at: datetime.datetime
    temp: int | None  # at the station, at `at`
    weather: str | None  # for the three hours from `at`, e.g. "くもり"
    wind_direction: str | None  # e.g. "南東"
    wind_speed: tuple[int, int] | None  # m/s, e.g. (3, 5)


class RadarProduct(enum.Enum):
    NOWCAST = "nowc"  # 高解像度降水ナウキャスト: every 5 minutes, up to an hour ahead
    SHORT_RANGE = "rasrf"  # 降水短時間予報: hourly, up to 15 hours ahead


@dataclass(frozen=True)
class RadarFrame:
    """One moment of a radar product, observed or forecast."""

    product: RadarProduct
    basetime: str  # JMA's UTC stamps, e.g. "20260912083000"; they name the tiles
    validtime: str
    member: str  # also in the tile's name: "none", or "immed" for a 速報 issue
    at: datetime.datetime  # `validtime` in JST
    observed: bool  # an observation or analysis (実況) rather than a forecast


@dataclass(frozen=True)
class RadarMap:
    """A frame drawn over the base map, centred on the station.

    Both layers are row-major, `width` × `height` pixels.
    """

    frame: RadarFrame
    zoom: int
    width: int
    height: int
    km_per_pixel: float
    outline: bytes  # one byte per pixel: how strongly a coast or border line covers it
    rain: bytes  # four bytes per pixel, RGBA: the legend colour, transparent if dry
    city: tuple[int, int]  # the station's pixel
    complete: bool  # False if JMA has not published every tile of the frame yet


@dataclass(frozen=True)
class RainPoint:
    """How hard it rains at the station at one frame."""

    at: datetime.datetime
    observed: bool
    level: RainLevel | None  # None when dry, or when not known
    known: bool = True  # False if the frame's tile is not published yet


def now_index(frames: Sequence[RadarFrame]) -> int:
    """Where the newest observation is: the frame forecasts count "+N分" from."""
    return max((i for i, frame in enumerate(frames) if frame.observed), default=0)


def from_now(frames: Sequence[RadarFrame]) -> tuple[RadarFrame, ...]:
    """The newest observation and the forecasts after it."""
    return tuple(frames[now_index(frames) :])


class WeatherSource(Protocol):
    """Everything the views ask for. Every method may raise ForecastError."""

    def forecast(self) -> Forecast: ...

    def hourly(self) -> tuple[Hourly, ...]: ...

    def radar_frames(self, product: RadarProduct) -> tuple[RadarFrame, ...]: ...

    def radar_map(
        self, frame: RadarFrame, zoom: int, width: int, height: int
    ) -> RadarMap: ...

    def rain_at_city(self, frames: Sequence[RadarFrame]) -> tuple[RainPoint, ...]: ...
