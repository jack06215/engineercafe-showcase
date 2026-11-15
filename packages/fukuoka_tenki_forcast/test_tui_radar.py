import dataclasses
import unittest

from rich.color import Color
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Static

from packages.fukuoka_tenki_forcast.fixtures import (
    FakeSource,
    nowcast_frames,
    radar_map,
)
from packages.fukuoka_tenki_forcast.model import (
    ForecastError,
    RadarMap,
    RadarProduct,
)
from packages.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)
from packages.fukuoka_tenki_forcast.tui_radar import (
    CITY,
    GROUND,
    LINE,
    LINE_STRENGTH,
    RadarImage,
    RadarPanel,
    map_pixels,
)


def small_map() -> RadarMap:
    """5×3 pixels: a line at the top left, rain at the bottom right, the station at the centre."""
    outline = bytearray(15)
    outline[0] = 255
    rain = bytearray(60)
    rain[4 * 14 : 4 * 15] = bytes([*RAIN_LEVELS[6].color, 255])
    return dataclasses.replace(
        radar_map(nowcast_frames()[0], 6, 5, 3),
        outline=bytes(outline),
        rain=bytes(rain),
    )


class MapPixelsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pixels = map_pixels(small_map())

    def test_layers(self) -> None:
        line = tuple(
            round(g + (c - g) * LINE_STRENGTH)
            for g, c in zip(GROUND, LINE, strict=True)
        )
        self.assertEqual(self.pixels[0], line)
        self.assertEqual(self.pixels[14], RAIN_LEVELS[6].color)
        self.assertEqual(self.pixels[4], GROUND)

    def test_the_station_is_marked(self) -> None:
        self.assertEqual([self.pixels[i] for i in (2, 6, 7, 8, 12)], [CITY] * 5)


class ImageApp(App[None]):
    def compose(self) -> ComposeResult:
        yield RadarImage()


class RadarImageTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_pixels_per_cell(self) -> None:
        app = ImageApp()
        # Tall enough for the image's minimum height, so no scrollbar takes columns.
        async with app.run_test(size=(10, 8)):
            image = app.query_one(RadarImage)
            image.show_map(small_map())
            pixels = map_pixels(small_map())

            first = image.render_line(0)
            segment = next(iter(first))
            self.assertEqual(segment.text[0], "▀")
            assert segment.style is not None
            self.assertEqual(segment.style.color, Color.from_rgb(*pixels[0]))
            self.assertEqual(segment.style.bgcolor, Color.from_rgb(*pixels[5]))
            self.assertEqual(first.cell_length, 10)  # padded past the map's 5 pixels

            # Row 1 holds pixel row 2 on top and nothing below it.
            bottom = list(image.render_line(1))[-2]
            assert bottom.style is not None
            self.assertEqual(bottom.style.color, Color.from_rgb(*RAIN_LEVELS[6].color))
            self.assertEqual(bottom.style.bgcolor, Color.from_rgb(*GROUND))


class PanelApp(App[None]):
    def __init__(self, source: FakeSource) -> None:
        super().__init__()
        self.source = source

    def compose(self) -> ComposeResult:
        yield RadarPanel(self.source)


async def open_panel(app: PanelApp, pilot: Pilot[None]) -> RadarPanel:
    panel = app.query_one(RadarPanel)
    panel.activate()
    await settle(app, pilot)
    return panel


async def settle(app: App[None], pilot: Pilot[None]) -> None:
    for _ in range(4):
        await app.workers.wait_for_complete()
        await pilot.pause()


def info(panel: RadarPanel) -> str:
    return str(panel.query_one("#radar-info", Static).content)


class RadarPanelTest(unittest.IsolatedAsyncioTestCase):
    async def test_opens_on_the_newest_observation(self) -> None:
        app = PanelApp(FakeSource())
        async with app.run_test(size=(100, 40)) as pilot:
            panel = await open_panel(app, pilot)

            self.assertEqual(panel.index, 12)
            self.assertIn("17:30 実況", info(panel))
            self.assertIn("北部九州", info(panel))
            shown = panel.query_one(RadarImage).radar_map
            assert shown is not None
            image = panel.query_one(RadarImage)
            self.assertEqual(
                (shown.width, shown.height), (image.size.width, image.size.height * 2)
            )
            self.assertIn(
                "18:20ごろから降り出す見込み",
                str(panel.query_one("#radar-summary", Static).content),
            )

    async def test_step_and_zoom(self) -> None:
        app = PanelApp(FakeSource())
        async with app.run_test(size=(100, 40)) as pilot:
            panel = await open_panel(app, pilot)

            await pilot.press("right")
            await settle(app, pilot)
            self.assertIn("17:35 予測（+5分）", info(panel))
            shown = panel.query_one(RadarImage).radar_map
            assert shown is not None
            self.assertEqual(shown.frame, panel.frames[13])

            await pilot.press("minus")
            await settle(app, pilot)
            self.assertEqual(panel.zoom, 4)
            self.assertIn("九州", info(panel))

            for _ in range(20):
                await pilot.press("left")
            self.assertEqual(panel.index, 0)

    async def test_switch_to_the_15_hour_forecast(self) -> None:
        app = PanelApp(FakeSource())
        async with app.run_test(size=(100, 40)) as pilot:
            panel = await open_panel(app, pilot)
            await pilot.press("m")
            await settle(app, pilot)

            self.assertIs(panel.product, RadarProduct.SHORT_RANGE)
            self.assertEqual(len(panel.frames), 16)
            self.assertIn("18:00 解析", info(panel))
            self.assertIn("降水短時間予報", info(panel))

    async def test_play_and_pause(self) -> None:
        app = PanelApp(FakeSource())
        async with app.run_test(size=(100, 40)) as pilot:
            panel = await open_panel(app, pilot)
            await pilot.press("space")
            self.assertTrue(panel.playing)
            self.assertTrue(info(panel).startswith("▶"))
            await pilot.press("space")
            self.assertFalse(panel.playing)

    async def test_error(self) -> None:
        error = ForecastError("雨雲レーダーを取得できませんでした: unreachable")
        app = PanelApp(FakeSource(fail={"radar_frames": error}))
        async with app.run_test(size=(100, 40)) as pilot:
            panel = await open_panel(app, pilot)

            self.assertEqual(info(panel), str(error))
            self.assertIsNone(panel.query_one(RadarImage).radar_map)


if __name__ == "__main__":
    unittest.main()
