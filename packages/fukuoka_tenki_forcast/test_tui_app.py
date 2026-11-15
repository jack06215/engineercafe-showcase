import unittest

from textual.pilot import Pilot
from textual.widgets import TabbedContent

from packages.fukuoka_tenki_forcast.fixtures import (
    FakeSource,
    week_forecast,
)
from packages.fukuoka_tenki_forcast.model import (
    ForecastError,
)
from packages.fukuoka_tenki_forcast.tui_app import (
    TenkiApp,
)
from packages.fukuoka_tenki_forcast.tui_radar import (
    RadarImage,
    RadarPanel,
)
from packages.fukuoka_tenki_forcast.tui_widgets import (
    DayCard,
    ErrorBanner,
    HourlyStrip,
    WeeklyKey,
    WeeklyTable,
)


async def settle(app: TenkiApp, pilot: Pilot[None]) -> None:
    """Let every worker finish, including those started by other workers' results."""
    for _ in range(4):
        await app.workers.wait_for_complete()
        await pilot.pause()


class TenkiAppTest(unittest.IsolatedAsyncioTestCase):
    async def test_today_tab(self) -> None:
        app = TenkiApp(FakeSource())
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)

            self.assertEqual(app.title, "福岡市の天気予報")
            self.assertEqual(app.sub_title, "福岡管区気象台 2026-09-12 11:00 発表")
            self.assertEqual(app.query_one(TabbedContent).active, "today")
            cards = list(app.query(DayCard))
            self.assertEqual(
                [card.border_title for card in cards],
                ["9/12(土) 今日", "9/13(日) 明日", "9/14(月) 明後日"],
            )
            self.assertTrue(cards[0].has_class("cloudy"))
            self.assertTrue(cards[1].has_class("rainy"))
            self.assertIn("18時", str(app.query_one(HourlyStrip).content))
            self.assertFalse(app.query_one(ErrorBanner).display)
            self.assertFalse(app.query_one("#today-view").loading)

    async def test_week_tab(self) -> None:
        app = TenkiApp(FakeSource(week_forecast()))
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)
            await pilot.press("2")

            self.assertEqual(app.query_one(TabbedContent).active, "week")
            self.assertEqual(app.query_one(WeeklyTable).row_count, 7)
            key = app.query_one(WeeklyKey)
            self.assertTrue(key.display)
            self.assertIn("平年値: 最低 21.6℃", str(key.content))

    async def test_radar_loads_only_when_opened(self) -> None:
        source = FakeSource()
        app = TenkiApp(source)
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)
            self.assertEqual(sorted(source.calls), ["forecast", "hourly"])

            await pilot.press("3")
            await settle(app, pilot)

            panel = app.query_one(RadarPanel)
            self.assertTrue(panel.has_focus)
            self.assertEqual(len(panel.frames), 25)
            self.assertIsNotNone(panel.rain)
            self.assertIsNotNone(app.query_one(RadarImage).radar_map)
            self.assertIn("radar_map", source.calls)

    async def test_error_then_reload(self) -> None:
        error = ForecastError("天気予報を取得できませんでした: unreachable")
        source = FakeSource(fail={"forecast": error})
        app = TenkiApp(source)
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)

            banner = app.query_one(ErrorBanner)
            self.assertTrue(banner.display)
            self.assertIn("取得できませんでした", str(banner.content))
            self.assertFalse(app.query_one(WeeklyTable).display)
            self.assertFalse(app.query_one("#today-view").loading)

            source.fail.clear()
            await pilot.press("r")
            await settle(app, pilot)

            self.assertFalse(banner.display)
            self.assertEqual(len(app.query(DayCard)), 3)
            self.assertTrue(app.query_one(WeeklyTable).display)

    async def test_a_failed_extra_leaves_the_rest(self) -> None:
        error = ForecastError("3時間ごとの予報を取得できませんでした: unreachable")
        app = TenkiApp(FakeSource(fail={"hourly": error}))
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)

            self.assertIn(
                "取得できませんでした", str(app.query_one(HourlyStrip).content)
            )
            self.assertFalse(app.query_one(ErrorBanner).display)
            self.assertEqual(len(app.query(DayCard)), 3)

    async def test_reload_replaces_rather_than_appends(self) -> None:
        app = TenkiApp(FakeSource())
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)
            await pilot.press("r")
            await settle(app, pilot)

            self.assertEqual(len(app.query(DayCard)), 3)
            self.assertEqual(app.query_one(WeeklyTable).row_count, 3)

    async def test_cards_side_by_side_when_wide(self) -> None:
        app = TenkiApp(FakeSource())
        async with app.run_test(size=(120, 50)) as pilot:
            await settle(app, pilot)
            self.assertTrue(app.screen.has_class("-wide"))
            self.assertEqual(len({card.region.y for card in app.query(DayCard)}), 1)

    async def test_cards_stacked_when_narrow(self) -> None:
        app = TenkiApp(FakeSource())
        async with app.run_test(size=(80, 60)) as pilot:
            await settle(app, pilot)
            self.assertTrue(app.screen.has_class("-narrow"))
            self.assertEqual(len({card.region.x for card in app.query(DayCard)}), 1)


if __name__ == "__main__":
    unittest.main()
