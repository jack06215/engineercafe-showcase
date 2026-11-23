import dataclasses
import unittest

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.progress import (
    TREND_WINDOW,
    Recurring,
    Trend,
    by_word_list,
    common_tests,
    counted,
    latest_results,
    recurring_problems,
    repeated_confusions,
    trend_groups,
)
from packages.monkeytype_analysis_console.results import (
    Result,
)


def _results() -> tuple[Result, ...]:
    return fixtures.read(fixtures.PROGRESS).results


class CountedTest(unittest.TestCase):
    def test_leaves_out_aborted_results_and_sorts_oldest_first(self) -> None:
        results = counted(reversed(_results()))
        self.assertEqual(len(results), 8)
        self.assertNotIn(20, [result.wpm for result in results])
        dates = [result.copied_at for result in results]
        self.assertEqual(dates, sorted(dates))

    def test_most_common_test_type_first(self) -> None:
        self.assertEqual(common_tests(_results()), ["words 10", "time 15"])


class TrendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.groups = trend_groups(_results())

    def test_one_group_per_word_list_and_test_type(self) -> None:
        self.assertEqual(
            [
                (group.word_list, group.test, len(group.results))
                for group in self.groups
            ],
            [
                ("code python", "words 10", 2),
                ("english 1k", "time 15", 2),
                ("english 1k", "words 10", 4),
            ],
        )

    def test_latest_against_the_mean_of_the_earlier_results(self) -> None:
        english = self.groups[2]
        self.assertEqual(english.latest.wpm, 55)
        self.assertEqual(len(english.earlier), 3)
        self.assertAlmostEqual(english.change("wpm") or 0, 55 - (50 + 52 + 49) / 3)
        self.assertAlmostEqual(english.change("acc") or 0, 2.0)
        self.assertAlmostEqual(english.change("consistency") or 0, 5.0)

    def test_no_earlier_results(self) -> None:
        single = Trend("english 1k", "words 10", self.groups[2].results[:1])
        self.assertEqual(single.earlier, ())
        self.assertIsNone(single.change("wpm"))

    def test_at_most_10_earlier_results(self) -> None:
        base = self.groups[2].results[0]
        results = tuple(
            dataclasses.replace(base, wpm=float(n)) for n in range(TREND_WINDOW + 5)
        )
        trend = Trend("english 1k", "words 10", results)
        self.assertEqual(len(trend.earlier), TREND_WINDOW)
        # Latest 14 against the mean of 4..13.
        self.assertAlmostEqual(trend.change("wpm") or 0, 14 - 8.5)

    def test_missing_values_are_skipped(self) -> None:
        results = tuple(
            dataclasses.replace(result, consistency=None)
            for result in self.groups[2].results
        )
        self.assertIsNone(Trend("a", "b", results).change("consistency"))


class RecurringTest(unittest.TestCase):
    def test_words_in_at_least_two_results(self) -> None:
        self.assertEqual(
            recurring_problems(_results()),
            [
                Recurring("century", results=3, slow=3, mistyped=0),
                Recurring("salt", results=2, slow=0, mistyped=2),
                Recurring("self", results=2, slow=2, mistyped=0),
                Recurring("they", results=2, slow=0, mistyped=2),
            ],
        )

    def test_slow_uses_each_result_own_threshold(self) -> None:
        # century is 50 wpm in the 3rd English result: not under its 45.
        lowered = [
            dataclasses.replace(result, wpm_threshold=10) for result in _results()
        ]
        words = [item.word for item in recurring_problems(lowered)]
        self.assertEqual(words, ["salt", "they"])

    def test_window_and_limit(self) -> None:
        self.assertEqual(len(latest_results(_results(), window=3)), 3)
        self.assertEqual(recurring_problems(_results(), window=2), [])
        self.assertEqual(len(recurring_problems(_results(), limit=2)), 2)

    def test_repeated_confusions(self) -> None:
        self.assertEqual(repeated_confusions(_results()), [("e→r", 2)])
        self.assertEqual(repeated_confusions(_results(), window=4), [])


class ByWordListTest(unittest.TestCase):
    def test_groups_in_name_order(self) -> None:
        words_10 = [result for result in _results() if result.test == "words 10"]
        groups = by_word_list(words_10)
        self.assertEqual(list(groups), ["code python", "english 1k"])
        self.assertEqual([len(group) for group in groups.values()], [2, 4])


if __name__ == "__main__":
    unittest.main()
