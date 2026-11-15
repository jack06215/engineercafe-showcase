import dataclasses
import datetime
import unittest

from packages.fukuoka_tenki_forcast.fixtures import (
    nowcast_frames,
    short_range_frames,
)
from packages.fukuoka_tenki_forcast.formatting import (
    center,
    clock,
    frame_label,
    normals_text,
    rain_summary,
    wind_text,
)
from packages.fukuoka_tenki_forcast.model import (
    Hourly,
    Normals,
    RainPoint,
)
from packages.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
    RainLevel,
)

JST = datetime.timezone(datetime.timedelta(hours=9))


def at(hour: int, minute: int = 0, day: int = 12) -> datetime.datetime:
    return datetime.datetime(2026, 9, day, hour, minute, tzinfo=JST)


class ClockTest(unittest.TestCase):
    def test_same_day(self) -> None:
        self.assertEqual(clock(at(18, 5), at(0).date()), "18:05")

    def test_another_day(self) -> None:
        self.assertEqual(clock(at(3, day=13), at(0).date()), "13日 3:00")


class FrameLabelTest(unittest.TestCase):
    def test_nowcast(self) -> None:
        frames = nowcast_frames()
        now = frames[12]
        self.assertEqual(frame_label(now, now), "17:30 実況")
        self.assertEqual(frame_label(frames[21], now), "18:15 予測（+45分）")
        self.assertEqual(frame_label(frames[-1], now), "18:30 予測（+1時間）")

    def test_short_range(self) -> None:
        frames = short_range_frames()
        self.assertEqual(frame_label(frames[0], frames[0]), "18:00 解析")
        self.assertEqual(frame_label(frames[1], frames[0]), "18:50 予測（+50分）")
        self.assertEqual(
            frame_label(frames[-1], frames[0]), "13日 8:00 予測（+14時間）"
        )


class TextTest(unittest.TestCase):
    def test_wind(self) -> None:
        hour = Hourly(at(18), 27, "くもり", "南東", (3, 5))
        self.assertEqual(wind_text(hour), "南東 3〜5m/s")
        self.assertEqual(wind_text(dataclasses.replace(hour, wind_speed=None)), "南東")

    def test_normals(self) -> None:
        self.assertEqual(
            normals_text(Normals(21.6, 28.6, 9.6, 40.1)),
            "平年値: 最低 21.6℃ / 最高 28.6℃、7日間の降水量 平年並 9.6〜40.1mm",
        )

    def test_center(self) -> None:
        self.assertEqual(center("雨", 6), "  雨  ")
        self.assertEqual(center("27℃", 6), " 27℃  ")


class RainSummaryTest(unittest.TestCase):
    dry, light, heavy = None, RAIN_LEVELS[1], RAIN_LEVELS[4]

    def summary(self, now: RainLevel | None, *ahead: RainLevel | None) -> str:
        """The summary for `now` at 18:00, then `ahead` every 10 minutes."""
        points = [RainPoint(at(18), True, now)]
        points += [
            RainPoint(at(18, 10 * (i + 1)), False, level)
            for i, level in enumerate(ahead)
        ]
        return rain_summary(points)

    def test_starts(self) -> None:
        self.assertEqual(
            self.summary(self.dry, self.dry, self.light, self.heavy),
            "いまは降っていません。18:20ごろから降り出す見込み。最も強いときで強い雨（20〜30mm/h）",
        )

    def test_stops(self) -> None:
        self.assertEqual(
            self.summary(self.light, self.light, self.dry),
            "いまは雨（1〜5mm/h）。18:20ごろ やむ見込み。最も強いときで雨（1〜5mm/h）",
        )

    def test_keeps_raining(self) -> None:
        self.assertEqual(
            self.summary(self.heavy, self.light),
            "いまは強い雨（20〜30mm/h）。18:10まで降り続く見込み。最も強いときで雨（1〜5mm/h）",
        )

    def test_stays_dry(self) -> None:
        self.assertEqual(
            self.summary(self.dry, self.dry, self.dry),
            "いまは降っていません。18:20まで雨の予想はありません",
        )

    def test_unknown_points_are_skipped(self) -> None:
        points = [
            RainPoint(at(18), True, None),
            RainPoint(at(18, 10), False, self.heavy, known=False),
        ]
        self.assertEqual(rain_summary(points), "いまは降っていません")

    def test_no_observation(self) -> None:
        self.assertEqual(rain_summary([]), "いまの雨のようすが分かりません")


if __name__ == "__main__":
    unittest.main()
