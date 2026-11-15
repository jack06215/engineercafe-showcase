import datetime
import unittest

from packages.fukuoka_tenki_forcast.fixtures import (
    raw_hourly,
)
from packages.fukuoka_tenki_forcast.jma_timeseries import (
    parse_hourly,
)
from packages.fukuoka_tenki_forcast.model import (
    ForecastError,
    Hourly,
)

JST = datetime.timezone(datetime.timedelta(hours=9))


class ParseHourlyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hours = parse_hourly(raw_hourly())

    def test_every_three_hours(self) -> None:
        self.assertEqual(len(self.hours), 11)
        self.assertEqual(
            self.hours[0].at, datetime.datetime(2026, 9, 12, 18, tzinfo=JST)
        )
        self.assertEqual(
            self.hours[1].at - self.hours[0].at, datetime.timedelta(hours=3)
        )

    def test_step(self) -> None:
        self.assertEqual(
            self.hours[0],
            Hourly(
                at=datetime.datetime(2026, 9, 12, 18, tzinfo=JST),
                temp=27,
                weather="くもり",
                wind_direction="南東",
                wind_speed=(3, 5),
            ),
        )

    def test_the_last_temperature_has_no_weather(self) -> None:
        last = self.hours[-1]
        self.assertEqual(last.temp, 26)
        self.assertIsNone(last.weather)
        self.assertIsNone(last.wind_speed)

    def test_malformed(self) -> None:
        data = raw_hourly()
        data["areaTimeSeries"]["weather"].pop()
        with self.assertRaisesRegex(
            ForecastError, "3時間ごとの予報の形式が想定と違います"
        ):
            parse_hourly(data)


if __name__ == "__main__":
    unittest.main()
