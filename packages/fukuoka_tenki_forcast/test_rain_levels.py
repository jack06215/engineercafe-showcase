import unittest

from packages.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
    rain_level,
)


class RainLevelTest(unittest.TestCase):
    def test_labels(self) -> None:
        self.assertEqual(
            [level.label for level in RAIN_LEVELS],
            ["0〜1", "1〜5", "5〜10", "10〜20", "20〜30", "30〜50", "50〜80", "80〜"],
        )

    def test_by_colour(self) -> None:
        self.assertEqual(rain_level((160, 210, 255)), RAIN_LEVELS[1])
        self.assertIsNone(rain_level((255, 255, 255)))


if __name__ == "__main__":
    unittest.main()
