import dataclasses
import datetime
import re
import unittest

from packages.fukuoka_tenki_forcast.fixtures import (
    FakeSource,
    nowcast_frames,
    sample_forecast,
    sample_hourly,
    week_forecast,
)
from packages.fukuoka_tenki_forcast.model import (
    RadarProduct,
    WeeklyDay,
    from_now,
)
from packages.fukuoka_tenki_forcast.render_text import (
    render_hourly_text,
    render_rain_text,
    render_text,
    render_unavailable,
)


class RenderTextTest(unittest.TestCase):
    def test_render(self) -> None:
        text = render_text(sample_forecast())
        self.assertIn("福岡市の天気予報（福岡管区気象台 2026-09-12 11:00 発表）", text)
        self.assertIn("■ 9/12(土) 今日", text)
        self.assertIn("■ 9/14(月) 明後日", text)
        self.assertIn("  気温: 最高 29℃\n", text)
        self.assertIn("  気温: 最低 25℃ / 最高 31℃", text)
        self.assertIn("  降水確率: 12-18時 30% / 18-24時 10%", text)
        self.assertIn("  風: 北の風  波: 1.5メートル", text)
        self.assertIn("■ 7日間の予報", text)
        self.assertIn("9/13(日) ☔ 曇後一時雨", text)
        self.assertIn("降水  -%  信頼度 -", text)
        self.assertIn("9/15(火) ❓ 天気コード 999", text)

    def test_week_rows_have_a_bar_between_the_temperatures(self) -> None:
        text = render_text(week_forecast())
        row = next(line for line in text.split("\n") if "9/18(金)" in line)
        self.assertRegex(row, r" 24℃ [ ┊░]*█+[ ┊░]* 31℃ ")

    def test_first_week_day_uses_the_detailed_temperatures(self) -> None:
        text = render_text(sample_forecast())
        row = next(line for line in text.split("\n") if "9/13(日) ☔" in line)
        self.assertRegex(row, r" 25℃ .* 31℃ ")

    def test_normals(self) -> None:
        self.assertIn(
            "  平年値: 最低 21.6℃ / 最高 28.6℃、7日間の降水量 平年並 9.6〜40.1mm",
            render_text(week_forecast()),
        )

    def test_zero_is_shown_not_dashed(self) -> None:
        cold_dry_day = WeeklyDay(datetime.date(2027, 1, 20), "100", 0, -2, 0, "A")
        forecast = dataclasses.replace(sample_forecast(), weekly=(cold_dry_day,))
        row = render_text(forecast).split("\n")[-1]
        self.assertRegex(row, r" -2℃ .* 0℃ +降水  0%  信頼度 A$")


class RenderExtrasTest(unittest.TestCase):
    def test_hourly(self) -> None:
        text = render_hourly_text(sample_hourly())
        self.assertTrue(text.startswith("■ 3時間ごとの予報\n"))
        self.assertIn("18時", text)

    def test_rain(self) -> None:
        frames = from_now(nowcast_frames())
        rain = FakeSource().rain_at_city(frames)
        lines = render_rain_text(RadarProduct.NOWCAST, frames, rain).split("\n")
        self.assertEqual(lines[0], "■ 福岡市の雨（ナウキャスト（1時間先まで））")
        self.assertEqual(
            lines[1],
            "  いまは降っていません。18:20ごろから降り出す見込み。最も強いときで雨（1〜5mm/h）",
        )
        self.assertEqual(re.sub(r"\s", "", lines[2]), "·" * 10 + "▂" * 6)

    def test_unavailable(self) -> None:
        self.assertEqual(
            render_unavailable("3時間ごとの予報", "取得できませんでした"),
            "■ 3時間ごとの予報\n  （取得できませんでした）",
        )


if __name__ == "__main__":
    unittest.main()
