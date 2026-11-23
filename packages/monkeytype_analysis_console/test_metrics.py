import dataclasses
import math
import unittest

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.metrics import (
    band_groups,
    band_labels,
    chars_left_wrong,
    default_threshold,
    fastest_speed,
    flags,
    format_number,
    goal_met,
    has_afk_flag,
    is_aborted,
    is_mistyped,
    is_slow,
    keypresses,
    position_groups,
    previous_pb,
    slow_words,
    thirds,
    time_lost,
    too_fast_count,
)
from packages.monkeytype_analysis_console.results import (
    Chars,
    Crown,
    Keys,
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


class MistypedTest(unittest.TestCase):
    def test_matches_yr_missed_word_list(self) -> None:
        # multi.yml's first result has a trimmed word list, so it is left out.
        for path in [p for p in fixtures.GOOD_FILES if p != fixtures.MULTI]:
            result = fixtures.result(path)
            with self.subTest(path.name):
                mistyped = [word.word for word in result.words if is_mistyped(word)]
                self.assertEqual(
                    tuple(dict.fromkeys(mistyped)), result.missed_word_list
                )

    def test_each_sign_of_a_wrong_keypress(self) -> None:
        plain = _word(40)
        self.assertFalse(is_mistyped(plain))
        self.assertTrue(is_mistyped(dataclasses.replace(plain, typed="wrd")))
        self.assertTrue(is_mistyped(dataclasses.replace(plain, marks="..f.")))
        self.assertTrue(is_mistyped(dataclasses.replace(plain, error=True)))
        self.assertTrue(is_mistyped(dataclasses.replace(plain, extra_fixed=True)))


class ResultChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.real = fixtures.result(fixtures.REAL)

    def test_keypresses_from_keys_then_chars(self) -> None:
        self.assertEqual(keypresses(self.real), 62)
        no_keys = dataclasses.replace(self.real, keys=None, chars=Chars(20, 2, 1, 5))
        self.assertEqual(keypresses(no_keys), 23)
        self.assertIsNone(keypresses(dataclasses.replace(no_keys, chars=None)))

    def test_aborted_under_25_keypresses(self) -> None:
        self.assertTrue(is_aborted(fixtures.result(fixtures.ABORTED)))
        self.assertTrue(is_aborted(dataclasses.replace(self.real, keys=Keys(20, 4))))
        self.assertFalse(is_aborted(dataclasses.replace(self.real, keys=Keys(20, 5))))
        self.assertFalse(is_aborted(self.real))

    def test_aborted_when_monkeytype_says_too_short(self) -> None:
        self.assertTrue(
            is_aborted(dataclasses.replace(self.real, flags=("invalid: too short",)))
        )

    def test_afk_flag_above_2_percent(self) -> None:
        self.assertFalse(has_afk_flag(dataclasses.replace(self.real, afk_pct=2.0)))
        self.assertTrue(has_afk_flag(dataclasses.replace(self.real, afk_pct=2.01)))
        self.assertFalse(has_afk_flag(dataclasses.replace(self.real, afk_pct=None)))

    def test_goal(self) -> None:
        self.assertTrue(goal_met(dataclasses.replace(self.real, acc=96.0), 96))
        self.assertFalse(goal_met(dataclasses.replace(self.real, acc=95.99), 96))
        self.assertIsNone(goal_met(dataclasses.replace(self.real, acc=None), 96))

    def test_time_lost(self) -> None:
        # 1 wrong key and its backspace at 51.69 raw wpm.
        self.assertAlmostEqual(time_lost(self.real) or 0, 2 * 60 / (51.69 * 5))
        self.assertEqual(time_lost(dataclasses.replace(self.real, time=0.3)), 0.3)
        self.assertIsNone(time_lost(dataclasses.replace(self.real, raw=0.0)))
        self.assertIsNone(time_lost(dataclasses.replace(self.real, keys=None)))

    def test_characters_left_wrong(self) -> None:
        self.assertEqual(chars_left_wrong(fixtures.result(fixtures.TYPOS)), 5)
        self.assertIsNone(chars_left_wrong(dataclasses.replace(self.real, chars=None)))

    def test_flags(self) -> None:
        self.assertEqual(
            flags(fixtures.result(fixtures.ABORTED)),
            ["failed (min accuracy)", "aborted"],
        )
        self.assertEqual(
            flags(fixtures.result(fixtures.MULTI, 2)),
            ["afk detected", "AFK 20.41%", "aborted"],
        )
        self.assertEqual(flags(self.real), [])


class WordGroupsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.typos = fixtures.result(fixtures.TYPOS)

    def test_one_row_per_band_then_all(self) -> None:
        groups = band_groups(self.typos)
        self.assertEqual(
            [group.label for group in groups],
            ["<31", "31-44", "45-59", "60-89", "90+", "all"],
        )
        self.assertEqual([group.words for group in groups], [2, 2, 3, 1, 1, 10])
        self.assertEqual([group.mistyped for group in groups], [2, 1, 2, 0, 0, 5])

    def test_band_means(self) -> None:
        slowest, second = band_groups(self.typos)[:2]
        self.assertEqual(slowest.mean_speed, 23.5)  # sneeing 17, about 30
        # Vec<T> and test: Shift presses 4 and 0, symbols 2 and 0.
        self.assertEqual(
            (second.mean_length, second.mean_shift_presses, second.mean_symbols),
            (5.0, 2.0, 1.0),
        )

    def test_all_row_speed_leaves_out_inf(self) -> None:
        everything = band_groups(self.typos)[-1]
        self.assertAlmostEqual(everything.mean_speed or 0, 473 / 9)
        self.assertEqual(too_fast_count(self.typos.words), 1)

    def test_empty_band_has_no_means(self) -> None:
        only_band_0 = tuple(
            dataclasses.replace(word, bucket=0) for word in self.typos.words[:2]
        )
        empty = band_groups(dataclasses.replace(self.typos, words=only_band_0))[1]
        self.assertEqual((empty.words, empty.mean_speed), (0, None))

    def test_thirds(self) -> None:
        words = [_word(speed) for speed in range(10)]
        self.assertEqual(
            [(label, len(group)) for label, group in thirds(words)],
            [("first", 3), ("middle", 4), ("last", 3)],
        )
        self.assertEqual([len(group) for _, group in thirds(words[:3])], [1, 1, 1])
        self.assertEqual(
            [(label, len(group)) for label, group in thirds(words[:2])], [("all", 2)]
        )

    def test_position_groups(self) -> None:
        groups = position_groups(self.typos.words)
        self.assertEqual([group.mistyped for group in groups], [1, 3, 1])


if __name__ == "__main__":
    unittest.main()
