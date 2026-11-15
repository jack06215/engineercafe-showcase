import http.client
import io
import json
import unittest
import urllib.error
import urllib.request
from email.message import Message
from unittest.mock import MagicMock, patch

from packages.fukuoka_tenki_forcast import jma_client
from packages.fukuoka_tenki_forcast.area import FUKUOKA
from packages.fukuoka_tenki_forcast.fixtures import (
    base_tile,
    nowcast_frames,
    radar_tile,
    raw_forecast,
    raw_hourly,
    raw_nowcast_times,
)
from packages.fukuoka_tenki_forcast.jma_client import (
    JmaSource,
    fetch_tile,
    load_forecast,
)
from packages.fukuoka_tenki_forcast.jma_radar import (
    city_tile,
)
from packages.fukuoka_tenki_forcast.model import (
    ForecastError,
    RadarProduct,
)
from packages.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.test", code, "error", Message(), None
    )


class LoadForecastTest(unittest.TestCase):
    def test_fetches_the_office_forecast(self) -> None:
        body = io.BytesIO(json.dumps(raw_forecast()).encode())
        with patch.object(urllib.request, "urlopen", return_value=body) as urlopen:
            forecast = load_forecast(FUKUOKA)

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://www.jma.go.jp/bosai/forecast/data/forecast/400000.json",
        )
        self.assertEqual(request.get_header("User-agent"), "fukuoka-tenki/1.0")
        self.assertEqual(forecast.office, "福岡管区気象台")

    def test_network_error(self) -> None:
        error = urllib.error.URLError("unreachable")
        with (
            patch.object(urllib.request, "urlopen", side_effect=error),
            self.assertRaisesRegex(ForecastError, "取得できませんでした"),
        ):
            load_forecast(FUKUOKA)

    def test_connection_reset_while_reading(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.side_effect = ConnectionResetError()
        with (
            patch.object(urllib.request, "urlopen", return_value=response),
            self.assertRaisesRegex(ForecastError, "取得できませんでした"),
        ):
            load_forecast(FUKUOKA)

    def test_retries_a_download_cut_off_part_way(self) -> None:
        cut_off = MagicMock()
        cut_off.__enter__.return_value.read.side_effect = http.client.IncompleteRead(
            b"["
        )
        whole = io.BytesIO(json.dumps(raw_forecast()).encode())
        with patch.object(
            urllib.request, "urlopen", side_effect=[cut_off, whole]
        ) as urlopen:
            forecast = load_forecast(FUKUOKA)
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(forecast.office, "福岡管区気象台")

    def test_not_json(self) -> None:
        body = io.BytesIO(b"<html>maintenance</html>")
        with (
            patch.object(urllib.request, "urlopen", return_value=body),
            self.assertRaisesRegex(ForecastError, "JSON を読めませんでした"),
        ):
            load_forecast(FUKUOKA)


class FetchTileTest(unittest.TestCase):
    def test_not_published_yet(self) -> None:
        with patch.object(urllib.request, "urlopen", side_effect=http_error(404)):
            self.assertIsNone(fetch_tile("https://example.test/t.png", "地図"))

    def test_server_error(self) -> None:
        with (
            patch.object(urllib.request, "urlopen", side_effect=http_error(503)),
            self.assertRaisesRegex(ForecastError, "地図を取得できませんでした"),
        ):
            fetch_tile("https://example.test/t.png", "地図")


class JmaSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = JmaSource(FUKUOKA)
        self.fetched: list[str] = []

    def fake_tile(self, url: str, what: str) -> bytes | None:
        """Base map tiles, and radar tiles with level 2 rain at every pixel (0, 0)."""
        self.fetched.append(url)
        return base_tile() if "/tile/jma/base/" in url else radar_tile({(0, 0): 2})

    def test_hourly(self) -> None:
        with patch.object(jma_client, "fetch_json", return_value=raw_hourly()) as fetch:
            hours = self.source.hourly()
        self.assertEqual(
            fetch.call_args.args[0],
            "https://www.jma.go.jp/bosai/jmatile/data/wdist/VPFD/400010.json",
        )
        self.assertEqual(len(hours), 11)

    def test_nowcast_frames(self) -> None:
        observed, forecast = raw_nowcast_times()
        indexes = {
            jma_client.NOWCAST_OBSERVED_URL: observed,
            jma_client.NOWCAST_FORECAST_URL: forecast,
        }
        with patch.object(
            jma_client, "fetch_json", side_effect=lambda url, what: indexes[url]
        ):
            frames = self.source.radar_frames(RadarProduct.NOWCAST)
        self.assertEqual(frames, nowcast_frames())

    def test_radar_map_urls(self) -> None:
        frame = nowcast_frames()[-1]
        with patch.object(jma_client, "fetch_tile", side_effect=self.fake_tile):
            radar_map = self.source.radar_map(frame, 6, 96, 80)
        self.assertEqual((radar_map.width, radar_map.height), (96, 80))
        self.assertIn("https://www.jma.go.jp/tile/jma/base/6/54/25.png", self.fetched)
        self.assertIn(
            "https://www.jma.go.jp/bosai/jmatile/data/nowc/20260912083000/none/"
            "20260912093000/surf/hrpns/6/55/25.png",
            self.fetched,
        )
        self.assertEqual(len(self.fetched), 4)  # two base tiles, two radar tiles

    def test_tiles_are_fetched_once(self) -> None:
        frame = nowcast_frames()[-1]
        with patch.object(jma_client, "fetch_tile", side_effect=self.fake_tile):
            self.source.radar_map(frame, 6, 96, 80)
            self.source.radar_map(frame, 6, 96, 80)
        self.assertEqual(len(self.fetched), 4)

    def test_missing_tiles_are_asked_for_again(self) -> None:
        frame = nowcast_frames()[-1]
        with patch.object(jma_client, "fetch_tile", return_value=None) as fetch:
            self.assertFalse(self.source.radar_map(frame, 6, 96, 80).complete)
            self.source.radar_map(frame, 6, 96, 80)
        self.assertEqual(fetch.call_count, 8)

    def test_rain_at_city(self) -> None:
        frames = nowcast_frames()[-3:]
        (x, y), pixel = city_tile(FUKUOKA.lat, FUKUOKA.lon)

        def tile(url: str, what: str) -> bytes | None:
            self.fetched.append(url)
            wet = url.endswith(f"/8/{x}/{y}.png") and frames[1].validtime in url
            return radar_tile({pixel: 4} if wet else {})

        with patch.object(jma_client, "fetch_tile", side_effect=tile):
            rain = self.source.rain_at_city(frames)
        self.assertEqual([point.level for point in rain], [None, RAIN_LEVELS[4], None])
        self.assertEqual(len(self.fetched), 3)


if __name__ == "__main__":
    unittest.main()
