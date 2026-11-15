import datetime
import unittest

from packages.fukuoka_tenki_forcast.area import FUKUOKA
from packages.fukuoka_tenki_forcast.fixtures import (
    raw_forecast,
    raw_forecast_1700,
)
from packages.fukuoka_tenki_forcast.jma_parser import (
    find_area,
    parse_forecast,
    parse_short_term,
    parse_weekly,
)
from packages.fukuoka_tenki_forcast.model import (
    ForecastError,
    Normals,
    PopSlot,
    TempRange,
)


class FindAreaTest(unittest.TestCase):
    def test_finds_by_code_not_position(self) -> None:
        time_series = raw_forecast()[0]["timeSeries"][0]
        self.assertEqual(find_area(time_series, "400010")["area"]["name"], "福岡地方")

    def test_missing_code_raises(self) -> None:
        with self.assertRaises(LookupError):
            find_area(raw_forecast()[0]["timeSeries"][0], "123456")


class ParseShortTermTest(unittest.TestCase):
    def setUp(self) -> None:
        self.today, self.tomorrow, self.day_after = parse_short_term(
            raw_forecast(), FUKUOKA
        )

    def test_dates(self) -> None:
        self.assertEqual(self.today.date, datetime.date(2026, 9, 12))
        self.assertEqual(self.day_after.date, datetime.date(2026, 9, 14))

    def test_text_is_normalized_to_half_width(self) -> None:
        self.assertEqual(self.today.weather, "くもり 所により 夜のはじめ頃 まで 雨")
        self.assertEqual(self.today.wave, "1.5メートル")
        self.assertEqual(self.tomorrow.wind, "南の風 後 北の風")

    def test_today_shows_only_the_maximum(self) -> None:
        self.assertIsNone(self.today.temp_min)
        self.assertEqual(self.today.temp_max, 29)

    def test_temperatures_are_matched_by_time(self) -> None:
        self.assertEqual(self.tomorrow.temp_min, 25)
        self.assertEqual(self.tomorrow.temp_max, 31)

    def test_day_after_has_no_temperatures_or_pops(self) -> None:
        self.assertIsNone(self.day_after.temp_min)
        self.assertIsNone(self.day_after.temp_max)
        self.assertEqual(self.day_after.pops, ())

    def test_pops_are_grouped_by_day(self) -> None:
        self.assertEqual(self.today.pops, (PopSlot(12, 30), PopSlot(18, 10)))
        self.assertEqual(len(self.tomorrow.pops), 4)


class ParseWeeklyTest(unittest.TestCase):
    def test_blank_values_become_none(self) -> None:
        first = parse_weekly(raw_forecast(), FUKUOKA)[0]
        self.assertIsNone(first.pop)
        self.assertIsNone(first.temp_min)
        self.assertIsNone(first.temp_max)
        self.assertIsNone(first.reliability)

    def test_values(self) -> None:
        third = parse_weekly(raw_forecast(), FUKUOKA)[2]
        self.assertEqual(third.date, datetime.date(2026, 9, 15))
        self.assertEqual(third.pop, 80)
        self.assertEqual((third.temp_min, third.temp_max), (24, 28))
        self.assertEqual(third.reliability, "A")


class WeekTest(unittest.TestCase):
    """The 17:00 report: a full week, with likely ranges and normals."""

    def setUp(self) -> None:
        self.forecast = parse_forecast(raw_forecast_1700(), FUKUOKA)

    def test_seven_days_from_tomorrow(self) -> None:
        dates = [day.date for day in self.forecast.weekly]
        self.assertEqual(len(dates), 7)
        self.assertEqual(dates[0], datetime.date(2026, 9, 13))
        self.assertEqual(dates[-1], datetime.date(2026, 9, 19))

    def test_first_day_temperatures_come_from_the_detailed_forecast(self) -> None:
        first = self.forecast.weekly[0]
        tomorrow = self.forecast.days[1]
        self.assertEqual((first.temp_min, first.temp_max), (24, 30))
        self.assertEqual(
            (first.temp_min, first.temp_max), (tomorrow.temp_min, tomorrow.temp_max)
        )
        self.assertIsNone(first.pop)
        self.assertIsNone(first.temp_min_range)

    def test_weekly_values_are_not_overwritten(self) -> None:
        details = self.forecast.days
        weekly = parse_weekly(raw_forecast_1700(), FUKUOKA, details)
        self.assertEqual(weekly[1], self.forecast.weekly[1])
        self.assertEqual((weekly[1].temp_min, weekly[1].temp_max), (25, 29))

    def test_likely_ranges(self) -> None:
        second = self.forecast.weekly[1]
        self.assertEqual(second.temp_min_range, TempRange(24, 27))
        self.assertEqual(second.temp_max_range, TempRange(27, 32))

    def test_normals(self) -> None:
        self.assertEqual(self.forecast.normals, Normals(21.6, 28.6, 9.6, 40.1))

    def test_without_normals(self) -> None:
        data = raw_forecast_1700()
        del data[1]["tempAverage"]
        self.assertIsNone(parse_forecast(data, FUKUOKA).normals)

    def test_the_evening_report_has_no_temperatures_for_today(self) -> None:
        today = self.forecast.days[0]
        self.assertEqual(today.date, datetime.date(2026, 9, 12))
        self.assertEqual((today.temp_min, today.temp_max), (None, None))
        self.assertEqual(today.pops, (PopSlot(18, 20),))


class ParseForecastTest(unittest.TestCase):
    def test_report(self) -> None:
        forecast = parse_forecast(raw_forecast(), FUKUOKA)
        self.assertEqual(forecast.office, "福岡管区気象台")
        self.assertEqual(forecast.reported.isoformat(), "2026-09-12T11:00:00+09:00")
        self.assertEqual((len(forecast.days), len(forecast.weekly)), (3, 3))

    def test_missing_area(self) -> None:
        data = raw_forecast()
        data[0]["timeSeries"][0]["areas"].pop()
        with self.assertRaisesRegex(ForecastError, "形式が想定と違います"):
            parse_forecast(data, FUKUOKA)

    def test_null_where_a_list_is_expected(self) -> None:
        data = raw_forecast()
        data[0]["timeSeries"][1]["areas"][0]["pops"] = None
        with self.assertRaisesRegex(ForecastError, "形式が想定と違います"):
            parse_forecast(data, FUKUOKA)

    def test_value_that_is_not_a_number(self) -> None:
        data = raw_forecast()
        data[1]["timeSeries"][1]["areas"][0]["tempsMax"][1] = "暑い"
        with self.assertRaisesRegex(ForecastError, "形式が想定と違います"):
            parse_forecast(data, FUKUOKA)


if __name__ == "__main__":
    unittest.main()
