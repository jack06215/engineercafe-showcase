"""Fetch forecasts and radar maps from the JMA website. The only module that does I/O."""

import collections
import http.client
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from packages.fukuoka_tenki_forcast.area import Area
from packages.fukuoka_tenki_forcast.jma_parser import (
    parse_forecast,
)
from packages.fukuoka_tenki_forcast.jma_radar import (
    CITY_ZOOM,
    city_tile,
    compose,
    parse_nowcast_frames,
    parse_short_range_frames,
    rain_at,
    window_around,
)
from packages.fukuoka_tenki_forcast.jma_timeseries import (
    parse_hourly,
)
from packages.fukuoka_tenki_forcast.model import (
    Forecast,
    ForecastError,
    Hourly,
    RadarFrame,
    RadarMap,
    RadarProduct,
    RainPoint,
)

FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{office}.json"
HOURLY_URL = "https://www.jma.go.jp/bosai/jmatile/data/wdist/VPFD/{region}.json"
NOWCAST_OBSERVED_URL = (
    "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json"
)
NOWCAST_FORECAST_URL = (
    "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N2.json"
)
SHORT_RANGE_TIMES_URL = (
    "https://www.jma.go.jp/bosai/jmatile/data/rasrf/targetTimes.json"
)
RADAR_TILE_URL = (
    "https://www.jma.go.jp/bosai/jmatile/data/{product}/{basetime}/{member}/{validtime}"
    "/surf/{element}/{z}/{x}/{y}.png"
)
# JMA's own outline map. The tile/gsi/ maps on the same host are GSI's.
BASE_TILE_URL = "https://www.jma.go.jp/tile/jma/base/{z}/{x}/{y}.png"
ELEMENTS = {RadarProduct.NOWCAST: "hrpns", RadarProduct.SHORT_RANGE: "rasrf"}
TIMEOUT_SECONDS = 10
USER_AGENT = "fukuoka-tenki/1.0"
# Tiles downloaded at once. JMA's own map page asks for far more.
PARALLEL_FETCHES = 4
CACHED_TILES = 512


def load_forecast(area: Area) -> Forecast:
    """Fetch and parse the forecast for `area`, raising ForecastError on any failure."""
    return parse_forecast(fetch_json(FORECAST_URL.format(office=area.office)), area)


def fetch_json(url: str, what: str = "天気予報") -> Any:
    """Download and decode a JSON document; `what` names it in error messages."""
    try:
        data: Any = json.loads(_download(url))
    # OSError covers URLError, HTTPError, timeouts and connections reset mid-read.
    except (OSError, http.client.HTTPException) as e:
        raise ForecastError(f"{what}を取得できませんでした: {e}") from e
    # JSONDecodeError, or a body that is not UTF-8 at all.
    except ValueError as e:
        raise ForecastError(f"{what}の JSON を読めませんでした: {e}") from e
    return data


def fetch_tile(url: str, what: str) -> bytes | None:
    """Download one map tile; None if JMA has not published it (HTTP 404)."""
    try:
        png = _download(url)
    except urllib.error.HTTPError as e:
        e.close()  # it holds the response body
        if e.code == 404:
            return None
        raise ForecastError(f"{what}を取得できませんでした: {e}") from e
    except (OSError, http.client.HTTPException) as e:
        raise ForecastError(f"{what}を取得できませんでした: {e}") from e
    return png


def radar_tile_url(frame: RadarFrame, zoom: int, x: int, y: int) -> str:
    """Return the URL of one radar tile for *frame*."""
    return RADAR_TILE_URL.format(
        product=frame.product.value,
        basetime=frame.basetime,
        member=frame.member,
        validtime=frame.validtime,
        element=ELEMENTS[frame.product],
        z=zoom,
        x=x,
        y=y,
    )


class JmaSource:
    """The `WeatherSource` for `area`, read from the JMA website.

    Map tiles never change once published, so they are kept in memory:
    stepping back through frames, or looping them, costs no downloads.
    """

    def __init__(self, area: Area) -> None:
        """Read forecasts for *area*, keeping recent radar tiles in memory."""
        self.area = area
        self._tiles = _TileCache(CACHED_TILES)

    def forecast(self) -> Forecast:
        """Fetch the forecast for the area."""
        return load_forecast(self.area)

    def hourly(self) -> tuple[Hourly, ...]:
        """Fetch the 3-hourly forecast for the area's region."""
        url = HOURLY_URL.format(region=self.area.region)
        return parse_hourly(fetch_json(url, "3時間ごとの予報"))

    def radar_frames(self, product: RadarProduct) -> tuple[RadarFrame, ...]:
        """Fetch the list of available frames for *product*."""
        if product is RadarProduct.NOWCAST:
            return parse_nowcast_frames(
                fetch_json(NOWCAST_OBSERVED_URL, "雨雲レーダー"),
                fetch_json(NOWCAST_FORECAST_URL, "雨雲レーダー"),
            )
        return parse_short_range_frames(
            fetch_json(SHORT_RANGE_TIMES_URL, "降水短時間予報")
        )

    def radar_map(
        self, frame: RadarFrame, zoom: int, width: int, height: int
    ) -> RadarMap:
        """Fetch the map and radar tiles around the city and compose them."""
        window = window_around(self.area.lat, self.area.lon, zoom, width, height)
        keys = window.tiles()
        pngs = self._fetch_all(
            [(BASE_TILE_URL.format(z=zoom, x=x, y=y), "地図") for x, y in keys]
            + [(radar_tile_url(frame, zoom, x, y), "雨雲の地図") for x, y in keys]
        )
        base = dict(zip(keys, pngs[: len(keys)], strict=True))
        radar = dict(zip(keys, pngs[len(keys) :], strict=True))
        return compose(frame, window, base, radar)

    def rain_at_city(self, frames: Sequence[RadarFrame]) -> tuple[RainPoint, ...]:
        """Read the rain rate at the city's pixel in each of *frames*."""
        (x, y), pixel = city_tile(self.area.lat, self.area.lon, CITY_ZOOM)
        pngs = self._fetch_all(
            [(radar_tile_url(frame, CITY_ZOOM, x, y), "雨雲の地図") for frame in frames]
        )
        return tuple(
            rain_at(frame, png, pixel) for frame, png in zip(frames, pngs, strict=True)
        )

    def _fetch_all(self, requests: list[tuple[str, str]]) -> list[bytes | None]:
        """Fetch (url, what) pairs a few at a time, in order."""
        with ThreadPoolExecutor(PARALLEL_FETCHES) as pool:
            return list(pool.map(lambda request: self._tile(*request), requests))

    def _tile(self, url: str, what: str) -> bytes | None:
        png = self._tiles.get(url)
        if png is None:
            png = fetch_tile(url, what)
            # A missing tile may be published a minute later; only keep real ones.
            if png is not None:
                self._tiles.put(url, png)
        return png


class _TileCache:
    """The most recently used tiles, by URL. Safe to share between threads."""

    def __init__(self, size: int) -> None:
        self._size = size
        self._tiles: collections.OrderedDict[str, bytes] = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, url: str) -> bytes | None:
        with self._lock:
            png = self._tiles.get(url)
            if png is not None:
                self._tiles.move_to_end(url)
            return png

    def put(self, url: str, png: bytes) -> None:
        with self._lock:
            self._tiles[url] = png
            self._tiles.move_to_end(url)
            while len(self._tiles) > self._size:
                self._tiles.popitem(last=False)


def _download(url: str) -> bytes:
    try:
        return _read(url)
    except http.client.IncompleteRead, ConnectionResetError:
        # A response cut off part way is worth one more try.
        return _read(url)


def _read(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body: bytes = response.read()
    return body
