"""JMA's radar and rain forecast maps: frame lists, tile maths and compositing.

Pure: tiles come in as PNG bytes that the client has already downloaded. Maps
use JMA's Web Mercator tiles, 256 pixels square. Radar tiles exist at the even
zoom levels, 4 to 10; the odd levels come back empty.
"""

import datetime
import io
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    ForecastError,
    RadarFrame,
    RadarMap,
    RadarProduct,
    RainPoint,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    rain_level,
)

TILE_SIZE = 256
# The zoom the rain at the station is read at: about 500 m per pixel.
CITY_ZOOM = 8
# Observations shown before the nowcast's forecast: an hour, every 5 minutes.
PAST_FRAMES = 12
JST = datetime.timezone(datetime.timedelta(hours=9), "JST")

TileKey = tuple[int, int]
# PNG bytes per tile; None for a tile JMA has not published (HTTP 404).
Tiles = Mapping[TileKey, bytes | None]


@dataclass(frozen=True)
class Window:
    """A `width` × `height` pixel window onto the world map at `zoom`."""

    zoom: int
    left: int  # world pixel of the left edge
    top: int
    width: int
    height: int
    km_per_pixel: float  # at the window's centre

    def tiles(self) -> list[TileKey]:
        """The tiles the window overlaps, row by row."""
        return [
            (x, y)
            for y in range(
                self.top // TILE_SIZE, (self.top + self.height - 1) // TILE_SIZE + 1
            )
            for x in range(
                self.left // TILE_SIZE, (self.left + self.width - 1) // TILE_SIZE + 1
            )
        ]


def world_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Where (lat, lon) lands on the Web Mercator world map, 256·2^zoom pixels wide."""
    size = TILE_SIZE << zoom
    lat_rad = math.radians(lat)
    y = math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad))
    return (lon + 180) / 360 * size, (1 - y / math.pi) / 2 * size


def window_around(lat: float, lon: float, zoom: int, width: int, height: int) -> Window:
    """A window with (lat, lon) at pixel (width // 2, height // 2)."""
    x, y = world_pixel(lat, lon, zoom)
    return Window(
        zoom=zoom,
        left=math.floor(x) - width // 2,
        top=math.floor(y) - height // 2,
        width=width,
        height=height,
        km_per_pixel=km_per_pixel(lat, zoom),
    )


def km_per_pixel(lat: float, zoom: int) -> float:
    """Ground distance of one map pixel at latitude `lat`."""
    return 40075.017 * math.cos(math.radians(lat)) / (TILE_SIZE << zoom)


def city_tile(
    lat: float, lon: float, zoom: int = CITY_ZOOM
) -> tuple[TileKey, tuple[int, int]]:
    """The tile holding (lat, lon), and the pixel within that tile."""
    x, y = world_pixel(lat, lon, zoom)
    px, py = math.floor(x), math.floor(y)
    return (px // TILE_SIZE, py // TILE_SIZE), (px % TILE_SIZE, py % TILE_SIZE)


def compose(frame: RadarFrame, window: Window, base: Tiles, radar: Tiles) -> RadarMap:
    """Lay the frame's radar tiles over the base map's coast and border lines.

    `window` comes from `window_around`, which puts the station at its centre.
    """
    try:
        base_image = _mosaic(window, base)
        rain_image = _mosaic(window, radar)
    except (OSError, UnidentifiedImageError, ValueError) as e:
        raise ForecastError(f"雨雲の画像を読めませんでした: {e!r}") from e
    # The base map is dark lines with white halos on transparency. Keep only
    # how dark and how opaque each pixel is: that is the line's strength.
    darkness = ImageOps.invert(base_image.convert("L"))
    outline = ImageChops.multiply(darkness, base_image.getchannel("A"))
    return RadarMap(
        frame=frame,
        zoom=window.zoom,
        width=window.width,
        height=window.height,
        km_per_pixel=window.km_per_pixel,
        outline=outline.tobytes(),
        rain=rain_image.tobytes(),
        city=(window.width // 2, window.height // 2),
        complete=all(png is not None for png in radar.values()),
    )


def rain_at(frame: RadarFrame, tile: bytes | None, pixel: tuple[int, int]) -> RainPoint:
    """Read the rain level at `pixel` of the frame's tile."""
    if tile is None:
        return RainPoint(frame.at, frame.observed, None, known=False)
    try:
        rgba = Image.open(io.BytesIO(tile)).convert("RGBA").getpixel(pixel)
    except (OSError, UnidentifiedImageError, ValueError) as e:
        raise ForecastError(f"雨雲の画像を読めませんでした: {e!r}") from e
    if not isinstance(rgba, tuple) or len(rgba) != 4:
        raise ForecastError(f"雨雲の画像を読めませんでした: {rgba!r}")
    red, green, blue, alpha = (int(channel) for channel in rgba)
    level = rain_level((red, green, blue)) if alpha else None
    return RainPoint(frame.at, frame.observed, level)


def parse_nowcast_frames(
    observed: list[dict[str, Any]], forecast: list[dict[str, Any]]
) -> tuple[RadarFrame, ...]:
    """The last hour of observations, then the nowcast's forecast, oldest first."""
    try:
        past = sorted(
            (
                _frame(RadarProduct.NOWCAST, _Entry.of(e), observed=True)
                for e in observed
                if "hrpns" in e["elements"]
            ),
            key=_by_time,
        )[-(PAST_FRAMES + 1) :]
        ahead = sorted(
            (
                _frame(RadarProduct.NOWCAST, _Entry.of(e), observed=False)
                for e in forecast
                if "hrpns" in e["elements"]
            ),
            key=_by_time,
        )
    except (LookupError, TypeError, ValueError) as e:
        raise ForecastError(f"雨雲レーダーの形式が想定と違います: {e!r}") from e
    if not past:
        raise ForecastError("雨雲レーダーの観測がありません")
    return (*past, *(frame for frame in ahead if frame.at > past[-1].at))


def parse_short_range_frames(times: list[dict[str, Any]]) -> tuple[RadarFrame, ...]:
    """The newest analysis of the 15-hour forecast, then every step ahead of it.

    JMA's index lists each valid time under the newest issue that covers it:
    a 10-minute 速報 issue (member "immed") for the next six hours, the hourly
    issue after that. Other products share the index; only entries with the
    "rasrf" element have these maps.
    """
    try:
        entries = [_Entry.of(e) for e in times if "rasrf" in e["elements"]]
    except (LookupError, TypeError) as e:
        raise ForecastError(f"降水短時間予報の形式が想定と違います: {e!r}") from e
    analyses = [entry for entry in entries if entry.validtime == entry.basetime]
    if not analyses:
        raise ForecastError("降水短時間予報の解析がありません")
    now = max(analyses, key=lambda entry: entry.basetime)
    newest: dict[str, _Entry] = {}  # validtime -> the newest issue that lists it
    for entry in entries:
        listed = newest.get(entry.validtime)
        if entry.validtime > now.validtime and (
            listed is None or entry.basetime > listed.basetime
        ):
            newest[entry.validtime] = entry
    try:
        return (
            _frame(RadarProduct.SHORT_RANGE, now, observed=True),
            *(
                _frame(RadarProduct.SHORT_RANGE, entry, observed=False)
                for _, entry in sorted(newest.items())
            ),
        )
    except ValueError as e:
        raise ForecastError(f"降水短時間予報の形式が想定と違います: {e!r}") from e


@dataclass(frozen=True)
class _Entry:
    """One line of a targetTimes index."""

    basetime: str
    validtime: str
    member: str

    @classmethod
    def of(cls, entry: dict[str, Any]) -> _Entry:
        return cls(
            str(entry["basetime"]),
            str(entry["validtime"]),
            str(entry.get("member") or "none"),
        )


def _frame(product: RadarProduct, entry: _Entry, *, observed: bool) -> RadarFrame:
    return RadarFrame(
        product=product,
        basetime=entry.basetime,
        validtime=entry.validtime,
        member=entry.member,
        at=_jst(entry.validtime),
        observed=observed,
    )


def _by_time(frame: RadarFrame) -> datetime.datetime:
    return frame.at


def _jst(stamp: str) -> datetime.datetime:
    """Turn JMA's UTC "20260912083000" into 17:30 JST."""
    utc = datetime.datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=datetime.UTC)
    return utc.astimezone(JST)


def _mosaic(window: Window, tiles: Tiles) -> Image.Image:
    """Paste the tiles into one RGBA image covering the window; gaps stay transparent."""
    image = Image.new("RGBA", (window.width, window.height))
    for (x, y), png in tiles.items():
        if png is None:
            continue
        tile = Image.open(io.BytesIO(png)).convert("RGBA")
        image.paste(tile, (x * TILE_SIZE - window.left, y * TILE_SIZE - window.top))
    return image
