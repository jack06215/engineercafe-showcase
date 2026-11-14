"""Test data shared by the test_*.py files: real JMA responses, fake tiles, a fake source."""

import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from packages.vibe_coding_club.fukuoka_tenki_forcast.area import FUKUOKA
from packages.vibe_coding_club.fukuoka_tenki_forcast.jma_parser import (
    parse_forecast,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.jma_radar import (
    parse_nowcast_frames,
    parse_short_range_frames,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.jma_timeseries import (
    parse_hourly,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    Forecast,
    ForecastError,
    Hourly,
    RadarFrame,
    RadarMap,
    RadarProduct,
    RainPoint,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)

TESTDATA = Path(__file__).resolve().parent / "testdata"
# The 2026-09-12 11:00 JMA response for 福岡県, trimmed to what the parser
# reads, with three days of the weekly forecast. It keeps one other region
# (北九州地方) to check that areas are found by code, and its last weekly
# weather code, 999, is made up to exercise the fallback for unknown codes.
FORECAST_JSON = TESTDATA / "forecast_400000.json"
# The 17:00 response of the same day, as served but for the other regions: a
# full week, with likely ranges and normals, and no temperatures for today.
FORECAST_1700_JSON = TESTDATA / "forecast_400000_1700.json"
# The 3-hourly forecast for 福岡地方 of 17:00 that day, as served.
HOURLY_JSON = TESTDATA / "vpfd_400010.json"
# Radar indexes from about 17:30 and 18:05 that day, trimmed to the newest
# entries: nowcast observations and forecasts, and the 15-hour forecast.
NOWCAST_OBSERVED_JSON = TESTDATA / "nowc_targetTimes_N1.json"
NOWCAST_FORECAST_JSON = TESTDATA / "nowc_targetTimes_N2.json"
SHORT_RANGE_JSON = TESTDATA / "rasrf_targetTimes.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_forecast() -> list[dict[str, Any]]:
    """A fresh copy of the 11:00 forecast, safe to modify."""
    data: list[dict[str, Any]] = _load(FORECAST_JSON)
    return data


def raw_forecast_1700() -> list[dict[str, Any]]:
    """A fresh copy of the 17:00 forecast, safe to modify."""
    data: list[dict[str, Any]] = _load(FORECAST_1700_JSON)
    return data


def sample_forecast() -> Forecast:
    """The 11:00 forecast, parsed."""
    return parse_forecast(raw_forecast(), FUKUOKA)


def week_forecast() -> Forecast:
    """The 17:00 forecast, parsed: seven days with ranges and normals."""
    return parse_forecast(raw_forecast_1700(), FUKUOKA)


def raw_hourly() -> dict[str, Any]:
    """Return the recorded JSON of the 3-hourly forecast."""
    data: dict[str, Any] = _load(HOURLY_JSON)
    return data


def sample_hourly() -> tuple[Hourly, ...]:
    """Return the recorded 3-hourly forecast, parsed."""
    return parse_hourly(raw_hourly())


def raw_nowcast_times() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the recorded observed and forecast nowcast time lists."""
    return _load(NOWCAST_OBSERVED_JSON), _load(NOWCAST_FORECAST_JSON)


def raw_short_range_times() -> list[dict[str, Any]]:
    """Return the recorded short-range forecast time list."""
    data: list[dict[str, Any]] = _load(SHORT_RANGE_JSON)
    return data


def nowcast_frames() -> tuple[RadarFrame, ...]:
    """Return the radar frames parsed from the recorded nowcast times."""
    return parse_nowcast_frames(*raw_nowcast_times())


def short_range_frames() -> tuple[RadarFrame, ...]:
    """Return the radar frames parsed from the recorded short-range times."""
    return parse_short_range_frames(raw_short_range_times())


def radar_tile(rain: Mapping[tuple[int, int], int] | None = None) -> bytes:
    """A radar tile as JMA draws them: 256×256, palette PNG, dry pixels transparent.

    `rain` maps pixels to the index of their level in RAIN_LEVELS.
    """
    image = Image.new("P", (256, 256), 0)
    # Palette entries 0 and 1 are transparent; the legend colours follow.
    image.putpalette([255] * 6 + [c for level in RAIN_LEVELS for c in level.color])
    for pixel, level in (rain or {}).items():
        image.putpixel(pixel, level + 2)
    out = io.BytesIO()
    image.save(out, "PNG", transparency=bytes([0, 0] + [255] * len(RAIN_LEVELS)))
    return out.getvalue()


def base_tile(lines: Sequence[tuple[int, int]] = ()) -> bytes:
    """A base map tile: black line pixels on transparency, with a white halo pixel at (0, 0)."""
    image = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
    image.putpixel((0, 0), (255, 255, 255, 255))
    for pixel in lines:
        image.putpixel(pixel, (0, 0, 0, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def radar_map(frame: RadarFrame, zoom: int, width: int, height: int) -> RadarMap:
    """A map with a coast line along the top row and rain of level 3 at the centre."""
    outline = bytearray(width * height)
    outline[:width] = b"\xff" * width
    rain = bytearray(4 * width * height)
    centre = (height // 2) * width + width // 2
    rain[4 * centre : 4 * centre + 4] = bytes([*RAIN_LEVELS[3].color, 255])
    return RadarMap(
        frame=frame,
        zoom=zoom,
        width=width,
        height=height,
        km_per_pixel=2.0,
        outline=bytes(outline),
        rain=bytes(rain),
        city=(width // 2, height // 2),
        complete=True,
    )


class FakeSource:
    """A `WeatherSource` of canned data, for tests.

    `fail` maps a method name to the ForecastError it raises; `calls` lists the
    methods called, in order.
    """

    def __init__(
        self,
        forecast: Forecast | None = None,
        fail: Mapping[str, ForecastError] | None = None,
    ) -> None:
        """Serve *forecast* or the sample; raise the errors in *fail* by call name."""
        self._forecast = forecast or sample_forecast()
        self.fail = dict(fail or {})
        self.calls: list[str] = []

    def forecast(self) -> Forecast:
        """Return the canned forecast."""
        self._call("forecast")
        return self._forecast

    def hourly(self) -> tuple[Hourly, ...]:
        """Return the recorded 3-hourly forecast."""
        self._call("hourly")
        return sample_hourly()

    def radar_frames(self, product: RadarProduct) -> tuple[RadarFrame, ...]:
        """Return the recorded frames for *product*."""
        self._call("radar_frames")
        if product is RadarProduct.NOWCAST:
            return nowcast_frames()
        return short_range_frames()

    def radar_map(
        self, frame: RadarFrame, zoom: int, width: int, height: int
    ) -> RadarMap:
        """Return a fake radar map of the requested size."""
        self._call("radar_map")
        return radar_map(frame, zoom, width, height)

    def rain_at_city(self, frames: Sequence[RadarFrame]) -> tuple[RainPoint, ...]:
        """Dry until the last three frames, which have rain of level 1."""
        self._call("rain_at_city")
        return tuple(
            RainPoint(
                frame.at,
                frame.observed,
                RAIN_LEVELS[1] if i >= len(frames) - 3 else None,
            )
            for i, frame in enumerate(frames)
        )

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]
