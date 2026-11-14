import datetime
import unittest

from packages.vibe_coding_club.fukuoka_tenki_forcast.area import FUKUOKA
from packages.vibe_coding_club.fukuoka_tenki_forcast.fixtures import (
    base_tile,
    nowcast_frames,
    radar_tile,
    raw_short_range_times,
    short_range_frames,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.jma_radar import (
    Window,
    city_tile,
    compose,
    parse_nowcast_frames,
    parse_short_range_frames,
    rain_at,
    window_around,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    ForecastError,
    RadarProduct,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)

JST = datetime.timezone(datetime.timedelta(hours=9))


class TileMathTest(unittest.TestCase):
    def test_the_station_tile(self) -> None:
        tile, pixel = city_tile(FUKUOKA.lat, FUKUOKA.lon, 8)
        self.assertEqual(tile, (220, 102))
        self.assertTrue(all(0 <= p < 256 for p in pixel))

    def test_window_around_the_station(self) -> None:
        window = window_around(FUKUOKA.lat, FUKUOKA.lon, 6, 96, 80)
        self.assertEqual(window.tiles(), [(54, 25), (55, 25)])
        self.assertAlmostEqual(window.km_per_pixel, 2.04, places=2)


class ComposeTest(unittest.TestCase):
    # Six pixels of tile (0, 0) and six of tile (1, 0), four rows deep.
    window = Window(zoom=6, left=250, top=0, width=12, height=4, km_per_pixel=2.0)

    def setUp(self) -> None:
        self.frame = nowcast_frames()[0]

    def compose(self, radar_right: bytes | None = b"") -> tuple[bytes, bytes, bool]:
        base = {(0, 0): base_tile([(252, 1)]), (1, 0): base_tile()}
        right = radar_tile({(2, 2): 3}) if radar_right == b"" else radar_right
        radar = {(0, 0): radar_tile(), (1, 0): right}
        radar_map = compose(self.frame, self.window, base, radar)
        return radar_map.outline, radar_map.rain, radar_map.complete

    def test_lines(self) -> None:
        outline, _, _ = self.compose()
        self.assertEqual(outline[1 * 12 + 2], 255)  # the line at tile pixel (252, 1)
        self.assertEqual(outline[0 * 12 + 6], 0)  # the white halo of tile (1, 0)
        self.assertEqual(sum(1 for strength in outline if strength), 1)

    def test_rain(self) -> None:
        _, rain, complete = self.compose()
        pixel = (2 * 12 + 8) * 4  # tile (1, 0) pixel (2, 2)
        self.assertEqual(tuple(rain[pixel : pixel + 4]), (*RAIN_LEVELS[3].color, 255))
        self.assertEqual(sum(1 for i in range(3, len(rain), 4) if rain[i]), 1)
        self.assertTrue(complete)

    def test_a_missing_radar_tile_leaves_the_map_incomplete(self) -> None:
        _, rain, complete = self.compose(radar_right=None)
        self.assertFalse(any(rain[3::4]))  # every pixel transparent
        self.assertFalse(complete)

    def test_unreadable_tile(self) -> None:
        with self.assertRaisesRegex(ForecastError, "雨雲の画像を読めませんでした"):
            compose(self.frame, self.window, {(0, 0): b"<html>"}, {})


class RainAtTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = nowcast_frames()[0]

    def test_level(self) -> None:
        point = rain_at(self.frame, radar_tile({(10, 20): 5}), (10, 20))
        self.assertEqual(point.level, RAIN_LEVELS[5])
        self.assertTrue(point.known)

    def test_dry(self) -> None:
        point = rain_at(self.frame, radar_tile({(10, 20): 5}), (11, 20))
        self.assertIsNone(point.level)
        self.assertTrue(point.known)

    def test_tile_not_published(self) -> None:
        self.assertFalse(rain_at(self.frame, None, (0, 0)).known)


class NowcastFramesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frames = nowcast_frames()

    def test_an_hour_back_and_an_hour_ahead(self) -> None:
        observed = [frame for frame in self.frames if frame.observed]
        ahead = [frame for frame in self.frames if not frame.observed]
        self.assertEqual((len(observed), len(ahead)), (13, 12))
        self.assertEqual(
            observed[0].at, datetime.datetime(2026, 9, 12, 16, 30, tzinfo=JST)
        )
        self.assertEqual(
            observed[-1].at, datetime.datetime(2026, 9, 12, 17, 30, tzinfo=JST)
        )
        self.assertEqual(
            ahead[-1].at, datetime.datetime(2026, 9, 12, 18, 30, tzinfo=JST)
        )

    def test_oldest_first(self) -> None:
        times = [frame.at for frame in self.frames]
        self.assertEqual(times, sorted(times))

    def test_forecasts_share_the_newest_observation_basetime(self) -> None:
        self.assertEqual(
            {frame.basetime for frame in self.frames if not frame.observed},
            {"20260912083000"},
        )
        self.assertEqual({frame.member for frame in self.frames}, {"none"})

    def test_no_observations(self) -> None:
        with self.assertRaisesRegex(ForecastError, "観測がありません"):
            parse_nowcast_frames([], [])


class ShortRangeFramesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frames = short_range_frames()

    def test_starts_at_the_newest_analysis(self) -> None:
        first = self.frames[0]
        self.assertTrue(first.observed)
        self.assertEqual((first.basetime, first.member), ("20260912090000", "immed"))
        self.assertEqual(first.at, datetime.datetime(2026, 9, 12, 18, tzinfo=JST))
        self.assertEqual(
            {frame.product for frame in self.frames}, {RadarProduct.SHORT_RANGE}
        )

    def test_each_valid_time_from_the_issue_that_lists_it(self) -> None:
        ahead = self.frames[1:]
        self.assertEqual(len(ahead), 15)
        # Six hours from the 10-minute 速報 issue of 17:50, then the hourly issue of 17:00.
        self.assertEqual(
            {(frame.basetime, frame.member) for frame in ahead[:6]},
            {("20260912085000", "immed")},
        )
        self.assertEqual(
            {(frame.basetime, frame.member) for frame in ahead[6:]},
            {("20260912080000", "none")},
        )
        self.assertEqual(ahead[-1].at, datetime.datetime(2026, 9, 13, 8, tzinfo=JST))

    def test_other_products_in_the_index_are_ignored(self) -> None:
        times = [
            entry
            for entry in raw_short_range_times()
            if "rasrf" not in entry["elements"]
        ]
        with self.assertRaisesRegex(ForecastError, "解析がありません"):
            parse_short_range_frames(times)

    def test_malformed(self) -> None:
        with self.assertRaisesRegex(ForecastError, "形式が想定と違います"):
            parse_short_range_frames([{"elements": ["rasrf"]}])


if __name__ == "__main__":
    unittest.main()
