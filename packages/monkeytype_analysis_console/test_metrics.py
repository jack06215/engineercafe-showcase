import dataclasses
import math
import unittest

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.metrics import (
    band_labels,
    default_threshold,
    fastest_speed,
    format_number,
    is_slow,
    previous_pb,
    slow_words,
)
from packages.monkeytype_analysis_console.results import (
    Crown,
    Word,
)


def _word(speed: float | None) -> Word:
    return Word(i=0, word="word", wpm=speed, bucket=None)


class SlowWordTest(unittest.TestCase):
    def test_below_the_threshold_is_slow(self) -> None:
        self.assertTrue(is_slow(_word(39.9), 40))

    def test_equal_to_the_threshold_is_not_slow(self) -> None:
        self.assertFalse(is_slow(_word(40), 40))

    def test_too_fast_or_missing_is_never_slow(self) -> None:
        self.assertFalse(is_slow(_word(math.inf), 1000))
        self.assertFalse(is_slow(_word(None), 1000))

    def test_matches_yr_at_the_starting_threshold(self) -> None:
        for path in fixtures.GOOD_FILES:
            result = fixtures.result(path)
            with self.subTest(path.name):
                slow = slow_words(result.words, default_threshold(result))
                self.assertEqual(tuple(word.word for word in slow), result.slow_word)


class DefaultThresholdTest(unittest.TestCase):
    def test_the_result_threshold(self) -> None:
        self.assertEqual(default_threshold(fixtures.result(fixtures.REAL)), 30)

    def test_without_one_yr_offers_the_mean_speed_rounded_half_up(self) -> None:
        result = dataclasses.replace(
            fixtures.result(fixtures.CUSTOM), wpm_threshold=None
        )
        # (36 + 30 + 21) / 3 = 29
        self.assertEqual(default_threshold(result), 29)
        halves = dataclasses.replace(
            result, words=(_word(20), _word(21), _word(math.inf))
        )
        self.assertEqual(default_threshold(halves), 21)

    def test_without_speeds_yr_offers_80(self) -> None:
        result = dataclasses.replace(
            fixtures.result(fixtures.MULTI, 1), wpm_threshold=None
        )
        self.assertEqual(default_threshold(result), 80)


class FastestSpeedTest(unittest.TestCase):
    def test_ignores_inf(self) -> None:
        self.assertEqual(fastest_speed(fixtures.result(fixtures.TYPOS).words), 120)

    def test_none_without_speeds(self) -> None:
        self.assertIsNone(fastest_speed([_word(math.inf), _word(None)]))


class BandLabelsTest(unittest.TestCase):
    def test_monkeytype_labels(self) -> None:
        self.assertEqual(
            band_labels([0, 37, 70, 92, 127]),
            ("<37", "37-69", "70-91", "92-126", "127+"),
        )

    def test_the_labels_yr_copied_are_rebuilt(self) -> None:
        self.assertEqual(
            band_labels([0, 14, 20, 27, 33]),
            ("<14", "14-19", "20-26", "27-32", "33+"),
        )

    def test_equal_edges_make_an_empty_band(self) -> None:
        self.assertEqual(
            band_labels([0, 40, 40, 52, 60]), ("<40", "40", "40-51", "52-59", "60+")
        )

    def test_speeds_that_are_not_whole(self) -> None:
        self.assertEqual(
            band_labels([0, 0.5, 0.75, 1, 1.5]),
            ("<0.5", "0.5-0.75", "0.75-1", "1-1.5", "1.5+"),
        )

    def test_no_steps(self) -> None:
        self.assertEqual(band_labels([]), ())


class PreviousPbTest(unittest.TestCase):
    def test_wpm_minus_the_margin(self) -> None:
        pb = previous_pb(fixtures.result(fixtures.REAL))
        self.assertAlmostEqual(pb or 0, 51.69 - 26.38)

    def test_not_a_pb(self) -> None:
        self.assertIsNone(previous_pb(fixtures.result(fixtures.TYPOS)))

    def test_other_units_have_none(self) -> None:
        self.assertIsNone(previous_pb(fixtures.result(fixtures.CPM)))

    def test_unreadable_margin(self) -> None:
        result = dataclasses.replace(
            fixtures.result(fixtures.REAL), crown=Crown("pending", "pending")
        )
        self.assertIsNone(previous_pb(result))


class FormatNumberTest(unittest.TestCase):
    def test_formats(self) -> None:
        self.assertEqual(format_number(51.69), "51.69")
        self.assertEqual(format_number(17.5), "17.5")
        self.assertEqual(format_number(30.0), "30")
        self.assertEqual(format_number(2.345, 1), "2.3")
        self.assertEqual(format_number(math.inf), "∞")
        self.assertEqual(format_number(None), "–")


if __name__ == "__main__":
    unittest.main()
