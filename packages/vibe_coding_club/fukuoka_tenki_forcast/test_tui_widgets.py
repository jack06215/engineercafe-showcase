import datetime
import unittest

from packages.vibe_coding_club.fukuoka_tenki_forcast.charts import (
    TempScale,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    Normals,
    WeeklyDay,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.tui_widgets import (
    WEEKLY_COLUMNS,
    pop_bar,
    weekly_key,
    weekly_row,
)

SCALE = TempScale(-5, 30, 8)


class PopBarTest(unittest.TestCase):
    def test_fills_in_proportion(self) -> None:
        self.assertEqual(pop_bar(30, 10).plain, "███░░░░░░░  30%")

    def test_full(self) -> None:
        self.assertEqual(pop_bar(100, 5).plain, "█████ 100%")

    def test_empty(self) -> None:
        self.assertEqual(pop_bar(0, 5).plain, "░░░░░   0%")


class WeeklyRowTest(unittest.TestCase):
    def test_one_cell_per_column(self) -> None:
        day = WeeklyDay(datetime.date(2026, 9, 13), "212", 40, 24, 30, "B")
        self.assertEqual(len(weekly_row(day, SCALE, None)), len(WEEKLY_COLUMNS))

    def test_blanks_become_dashes(self) -> None:
        day = WeeklyDay(datetime.date(2026, 9, 13), "212", None, None, None, None)
        self.assertEqual(
            [cell.plain for cell in weekly_row(day, SCALE, None)],
            ["9/13(日)", "☔ 曇後一時雨", "-", " " * 8, "-", "-", "-"],
        )

    def test_zero_is_shown_not_dashed(self) -> None:
        day = WeeklyDay(datetime.date(2027, 1, 20), "100", 0, -2, 0, "A")
        cells = [cell.plain for cell in weekly_row(day, SCALE, None)]
        self.assertEqual(cells[2], "-2℃")
        self.assertEqual(cells[4:6], ["0℃", "░░░░░   0%"])


class WeeklyKeyTest(unittest.TestCase):
    def test_without_normals(self) -> None:
        self.assertEqual(
            weekly_key(None).plain, "█ 予想の最低〜最高  ░ 予想の幅  ┊ 平年値"
        )

    def test_with_normals(self) -> None:
        key = weekly_key(Normals(21.6, 28.6, 9.6, 40.1)).plain
        self.assertIn("\n平年値: 最低 21.6℃ / 最高 28.6℃", key)


if __name__ == "__main__":
    unittest.main()
