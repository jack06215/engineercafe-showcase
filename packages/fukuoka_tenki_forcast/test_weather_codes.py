import unittest

from packages.fukuoka_tenki_forcast.weather_codes import (
    weather_label,
)


class WeatherLabelTest(unittest.TestCase):
    def test_known_code(self) -> None:
        self.assertEqual(weather_label("203"), "☔ 曇時々雨")

    def test_emoji_follows_representative_weather(self) -> None:
        self.assertEqual(weather_label("102"), "☔ 晴一時雨")

    def test_unknown_code_falls_back_to_first_digit(self) -> None:
        self.assertEqual(weather_label("105"), "☀️ 天気コード 105")

    def test_unknown_category(self) -> None:
        self.assertEqual(weather_label("999"), "❓ 天気コード 999")


if __name__ == "__main__":
    unittest.main()
