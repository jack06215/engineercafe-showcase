import datetime
import unittest

from packages.vibe_coding_club.fukuoka_tenki_forcast.charts import (
    TempScale,
    hourly_chart,
    rain_strip,
    temp_bar,
    temp_color,
    week_scale,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.fixtures import (
    nowcast_frames,
    sample_hourly,
    week_forecast,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.formatting import (
    display_width,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    Normals,
    RainPoint,
    TempRange,
    WeeklyDay,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)

DAY = datetime.date(2026, 9, 16)


class TempColorTest(unittest.TestCase):
    def test_stops_and_blends(self) -> None:
        self.assertEqual(temp_color(-5), "#5a82ff")
        self.assertEqual(temp_color(5), "#55a5ff")  # halfway from 0℃ to 10℃
        self.assertEqual(temp_color(40), "#eb2d3c")


class WeekScaleTest(unittest.TestCase):
    def test_covers_temperatures_ranges_and_normals(self) -> None:
        forecast = week_forecast()
        # Lowest is the 21.6℃ normal, highest a likely maximum of 33℃.
        self.assertEqual(
            week_scale(forecast.weekly, forecast.normals), TempScale(20, 34, 24)
        )

    def test_nothing_known(self) -> None:
        day = WeeklyDay(DAY, "100", None, None, None, None)
        self.assertEqual(week_scale([day], None, 10), TempScale(0, 30, 10))


class TempBarTest(unittest.TestCase):
    scale = TempScale(20, 32, 13)  # one cell per degree
    normals = Normals(21.0, 29.0, 0, 0)

    def test_bar_band_and_normals(self) -> None:
        day = WeeklyDay(
            DAY, "100", None, 24, 30, None, TempRange(22, 25), TempRange(28, 32)
        )
        self.assertEqual(temp_bar(day, self.scale, self.normals).plain, " ┊░░███████░░")

    def test_bar_is_coloured_by_temperature(self) -> None:
        day = WeeklyDay(DAY, "100", None, 24, 30, None)
        bar = temp_bar(day, self.scale)
        styles = [str(span.style) for span in bar.spans]
        self.assertEqual(styles[0], temp_color(24))
        self.assertEqual(styles[-1], temp_color(30))

    def test_only_the_maximum(self) -> None:
        day = WeeklyDay(DAY, "100", None, None, 25, None)
        self.assertEqual(temp_bar(day, self.scale).plain, "     █       ")

    def test_nothing_known_leaves_the_normals(self) -> None:
        day = WeeklyDay(DAY, "100", None, None, None, None)
        self.assertEqual(temp_bar(day, self.scale, self.normals).plain, " ┊       ┊   ")


class HourlyChartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = hourly_chart(sample_hourly()).plain.split("\n")

    def test_rows(self) -> None:
        self.assertEqual(len(self.rows), 8)
        self.assertTrue(all(display_width(row) == 11 * 6 for row in self.rows))

    def test_labels(self) -> None:
        times, weather, temps = self.rows[:3]
        # Midnight shows the date instead of the hour.
        self.assertTrue(times.startswith(" 18時  21時  9/13 "))
        self.assertEqual(
            weather.split()[:7], ["曇", "曇", "曇", "曇", "曇", "曇", "雨"]
        )
        self.assertEqual(temps.split()[:3], ["27℃", "27℃", "26℃"])
        self.assertEqual(self.rows[-2].split()[:2], ["南東", "南"])
        self.assertEqual(self.rows[-1].split()[0], "3-5m")

    def test_bars_grow_with_the_temperature(self) -> None:
        bars = self.rows[3:6]
        # 6時 is the coldest (24℃): an eighth of a cell. 12時 the warmest (29℃): full.
        self.assertEqual([row[25:29] for row in bars], ["    ", "    ", "▁▁▁▁"])
        self.assertEqual([row[37:41] for row in bars], ["████", "████", "████"])


class RainStripTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frames = nowcast_frames()[:4]
        at = [frame.at for frame in self.frames]
        self.rain = (
            RainPoint(at[0], True, None),
            RainPoint(at[1], True, RAIN_LEVELS[0]),
            RainPoint(at[2], True, RAIN_LEVELS[7]),
            RainPoint(at[3], True, None, known=False),
        )

    def test_height_follows_the_level(self) -> None:
        strip, ruler = rain_strip(self.frames, self.rain).plain.split("\n")
        self.assertEqual(strip, "· ▁▁██  ")
        self.assertEqual(ruler, "16:30")

    def test_cursor(self) -> None:
        marker = rain_strip(self.frames, self.rain, cursor=2).plain.split("\n")[0]
        self.assertEqual(marker.index("▼"), 4)

    def test_not_loaded_yet(self) -> None:
        strip = rain_strip(self.frames, None).plain.split("\n")[0]
        self.assertEqual(strip.strip(), "")


if __name__ == "__main__":
    unittest.main()
