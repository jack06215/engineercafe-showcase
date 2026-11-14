"""The radar tab: JMA's radar and rain forecast over a map around the station.

The map is drawn with half blocks: each cell is "▀" in the colour of its upper
pixel on the colour of its lower one, so a cell holds two roughly square pixels.
"""

import functools
from typing import ClassVar

from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static
from textual.worker import get_current_worker

from packages.vibe_coding_club.fukuoka_tenki_forcast.charts import (
    rain_strip,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.formatting import (
    CITY_NAME,
    PRODUCT_NAMES,
    SOURCE_CREDIT,
    frame_label,
    rain_summary,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    ForecastError,
    RadarFrame,
    RadarMap,
    RadarProduct,
    RainPoint,
    WeatherSource,
    now_index,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.rain_levels import (
    RAIN_LEVELS,
)

RGB = tuple[int, int, int]
GROUND: RGB = (14, 17, 26)
LINE: RGB = (125, 132, 150)
CITY: RGB = (255, 70, 70)
# How strongly the coast and border lines show against the ground: dimmed, so
# that even the palest rain stands out from them.
LINE_STRENGTH = 0.55
# Line strengths below this are anti-aliasing fuzz, which at a pixel per half
# cell only thickens the lines.
LINE_THRESHOLD = 64
# Zoom levels on offer, widest first; JMA has radar tiles at the even ones.
ZOOM_NAMES = {4: "九州", 6: "北部九州", 8: "福岡市周辺"}
ZOOMS = tuple(ZOOM_NAMES)
DEFAULT_ZOOM = 6
PLAY_SECONDS = 0.6


def map_pixels(radar_map: RadarMap) -> list[RGB]:
    """Every pixel's colour, row by row: ground, then lines, rain, and the station."""
    outline, rain = radar_map.outline, radar_map.rain
    pixels = []
    for i in range(radar_map.width * radar_map.height):
        strength = outline[i] if outline[i] >= LINE_THRESHOLD else 0
        color = _blend(GROUND, LINE, strength / 255 * LINE_STRENGTH)
        if alpha := rain[4 * i + 3]:
            color = _blend(
                color, (rain[4 * i], rain[4 * i + 1], rain[4 * i + 2]), alpha / 255
            )
        pixels.append(color)
    cx, cy = radar_map.city
    for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        x, y = cx + dx, cy + dy
        if 0 <= x < radar_map.width and 0 <= y < radar_map.height:
            pixels[y * radar_map.width + x] = CITY
    return pixels


def legend() -> Text:
    """JMA's colours and what they mean, in mm/h."""
    text = Text()
    for level in RAIN_LEVELS:
        text.append("██", style=Style(color=Color.from_rgb(*level.color)))
        text.append(f"{level.label} ")
    text.append("mm/h  ")
    text.append(SOURCE_CREDIT, style="dim")
    return text


class RadarImage(Widget):
    """Shows a `RadarMap`, two pixels to a cell."""

    DEFAULT_CSS = """
    RadarImage {
        height: 1fr;
        min-height: 6;
    }
    """

    class Resized(Message):
        """The image changed size, so a map that fits should be fetched."""

    def __init__(self) -> None:
        super().__init__()
        self.radar_map: RadarMap | None = None
        self._pixels: list[RGB] = []

    def show_map(self, radar_map: RadarMap) -> None:
        self.radar_map = radar_map
        self._pixels = map_pixels(radar_map)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        radar_map = self.radar_map
        if radar_map is None:
            return Strip.blank(width, _half_block(GROUND, GROUND))
        drawn = min(width, radar_map.width)
        segments = [
            Segment("▀", _half_block(self._pixel(x, 2 * y), self._pixel(x, 2 * y + 1)))
            for x in range(drawn)
        ]
        if drawn < width:
            segments.append(Segment(" " * (width - drawn), _half_block(GROUND, GROUND)))
        return Strip(segments, width).simplify()

    def on_resize(self, _: events.Resize) -> None:
        self.post_message(self.Resized())

    def _pixel(self, x: int, y: int) -> RGB:
        radar_map = self.radar_map
        if radar_map is None or y >= radar_map.height:
            return GROUND
        return self._pixels[y * radar_map.width + x]


class RadarPanel(Vertical, can_focus=True):
    """The radar tab: a map, the frame's time, and the rain at the station over time.

    Nothing is loaded until the tab is first shown. Stepping, playing and
    zooming fetch only the map being shown; the source keeps tiles it has seen.
    """

    DEFAULT_CSS = """
    RadarPanel {
        height: 1fr;
    }
    RadarPanel #radar-info, RadarPanel #radar-legend {
        height: 1;
        padding: 0 1;
    }
    RadarPanel #radar-timeline, RadarPanel #radar-summary {
        height: auto;
        padding: 0 1;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "step(-1)", "前"),
        Binding("right", "step(1)", "次"),
        Binding("space", "play", "再生/停止"),
        Binding("plus,equals_sign", "zoom(1)", "拡大"),
        Binding("minus", "zoom(-1)", "縮小"),
        Binding("m", "switch_product", "ナウキャスト/15時間"),
    ]

    def __init__(self, source: WeatherSource) -> None:
        super().__init__()
        self.source = source
        self.product = RadarProduct.NOWCAST
        self.zoom = DEFAULT_ZOOM
        self.frames: tuple[RadarFrame, ...] = ()
        self.rain: tuple[RainPoint, ...] | None = None
        self.index = 0
        self.loaded = False
        self.playing = False
        self.error: str | None = None
        self._map_pending = False

    def compose(self) -> ComposeResult:
        yield Static(id="radar-info")
        yield RadarImage()
        yield Static(id="radar-timeline")
        yield Static(id="radar-summary")
        yield Static(legend(), id="radar-legend")

    def on_mount(self) -> None:
        self._player = self.set_interval(PLAY_SECONDS, self._advance, pause=True)

    def activate(self) -> None:
        """Called when the tab is shown: load it the first time, and take the keys."""
        if not self.loaded:
            self.reload()
        self.focus()

    def reload(self) -> None:
        # The info line says it is loading. Not `RadarImage.loading`: that
        # hides the image behind an indicator and reports its size as 0×0,
        # and the image's size is what the map is fetched for.
        self.loaded = True
        self.error = None
        self.frames, self.rain = (), None
        self._refresh_text()
        self._load_frames(self.product)

    def action_step(self, delta: int) -> None:
        if self.frames:
            self._show_frame(min(max(self.index + delta, 0), len(self.frames) - 1))

    def action_play(self) -> None:
        if not self.frames:
            return
        self.playing = not self.playing
        if self.playing:
            self._player.resume()
        else:
            self._player.pause()
        self._refresh_text()

    def action_zoom(self, delta: int) -> None:
        position = min(max(ZOOMS.index(self.zoom) + delta, 0), len(ZOOMS) - 1)
        if ZOOMS[position] != self.zoom:
            self.zoom = ZOOMS[position]
            self._refresh_text()
            self._request_map()

    def action_switch_product(self) -> None:
        self.product = (
            RadarProduct.SHORT_RANGE
            if self.product is RadarProduct.NOWCAST
            else RadarProduct.NOWCAST
        )
        self.playing = False
        self._player.pause()
        self.reload()

    def on_radar_image_resized(self, _: RadarImage.Resized) -> None:
        self._request_map()

    @work(thread=True, exclusive=True, group="radar-frames")
    def _load_frames(self, product: RadarProduct) -> None:
        try:
            frames = self.source.radar_frames(product)
        except ForecastError as e:
            if not get_current_worker().is_cancelled:
                self.app.call_from_thread(self._failed, str(e))
            return
        if not get_current_worker().is_cancelled:
            self.app.call_from_thread(self._frames_loaded, product, frames)

    @work(thread=True, exclusive=True, group="radar-map")
    def _load_map(self, frame: RadarFrame, zoom: int, width: int, height: int) -> None:
        try:
            radar_map = self.source.radar_map(frame, zoom, width, height)
        except ForecastError as e:
            if not get_current_worker().is_cancelled:
                self.app.call_from_thread(self._failed, str(e))
            return
        if not get_current_worker().is_cancelled:
            self.app.call_from_thread(self._map_loaded, radar_map)

    @work(thread=True, exclusive=True, group="radar-rain")
    def _load_rain(self, frames: tuple[RadarFrame, ...]) -> None:
        try:
            rain = self.source.rain_at_city(frames)
        except ForecastError as e:
            if not get_current_worker().is_cancelled:
                self.app.call_from_thread(self._rain_failed, frames, str(e))
            return
        if not get_current_worker().is_cancelled:
            self.app.call_from_thread(self._rain_loaded, frames, rain)

    def _frames_loaded(
        self, product: RadarProduct, frames: tuple[RadarFrame, ...]
    ) -> None:
        if product is not self.product:
            return
        self.frames = frames
        self.index = now_index(frames)
        self._refresh_text()
        self._request_map()
        self._load_rain(frames)

    def _map_loaded(self, radar_map: RadarMap) -> None:
        self._map_pending = False
        if self.frames and (radar_map.frame, radar_map.zoom) == (
            self.frames[self.index],
            self.zoom,
        ):
            self.query_one(RadarImage).show_map(radar_map)
            self._refresh_text()

    def _rain_loaded(
        self, frames: tuple[RadarFrame, ...], rain: tuple[RainPoint, ...]
    ) -> None:
        if frames == self.frames:
            self.rain = rain
            self._refresh_text()

    def _rain_failed(self, frames: tuple[RadarFrame, ...], message: str) -> None:
        if frames == self.frames:
            self.query_one("#radar-summary", Static).update(
                Text(f"{CITY_NAME}: {message}", style="red")
            )

    def _failed(self, message: str) -> None:
        self.error = message
        self._map_pending = False
        self._refresh_text()

    def _advance(self) -> None:
        """One tick of playback: move on, unless the last map is still coming."""
        if self.frames and not self._map_pending:
            self._show_frame((self.index + 1) % len(self.frames))

    def _show_frame(self, index: int) -> None:
        self.index = index
        self._refresh_text()
        self._request_map()

    def _request_map(self) -> None:
        image = self.query_one(RadarImage)
        width, height = image.size.width, image.size.height * 2
        # Not laid out yet: the image's first Resized message will ask again.
        if not self.frames or width < 1 or height < 1:
            return
        self._map_pending = True
        self._load_map(self.frames[self.index], self.zoom, width, height)

    def _refresh_text(self) -> None:
        self.query_one("#radar-info", Static).update(self._info())
        timeline = self.query_one("#radar-timeline", Static)
        summary = self.query_one("#radar-summary", Static)
        if not self.frames:
            timeline.update("")
            summary.update("")
            return
        timeline.update(rain_strip(self.frames, self.rain, cursor=self.index))
        if self.rain is None:
            summary.update(Text(f"{CITY_NAME}: 雨のようすを読み込み中…", style="dim"))
        else:
            summary.update(f"{CITY_NAME}: {rain_summary(self.rain)}")

    def _info(self) -> Text:
        """The line above the map: which frame, which product, how wide."""
        if self.error is not None:
            return Text(self.error, style="red")
        if not self.frames:
            return Text("読み込み中…" if self.loaded else "", style="dim")
        frame = self.frames[self.index]
        info = Text()
        if self.playing:
            info.append("▶ ", style="bold green")
        info.append(
            frame_label(frame, self.frames[now_index(self.frames)]), style="bold"
        )
        info.append(f"  {PRODUCT_NAMES[self.product]}  {ZOOM_NAMES[self.zoom]}")
        shown = self.query_one(RadarImage).radar_map
        if shown is not None and shown.zoom == self.zoom:
            info.append(
                f"（東西 約{shown.width * shown.km_per_pixel:.0f}km）", style="dim"
            )
            if shown.frame == frame and not shown.complete:
                info.append(
                    "  この時刻の地図はまだ一部しか公開されていません", style="yellow"
                )
        return info


def _blend(below: RGB, above: RGB, alpha: float) -> RGB:
    return (
        round(below[0] + (above[0] - below[0]) * alpha),
        round(below[1] + (above[1] - below[1]) * alpha),
        round(below[2] + (above[2] - below[2]) * alpha),
    )


@functools.lru_cache(maxsize=4096)
def _half_block(top: RGB, bottom: RGB) -> Style:
    return Style(color=Color.from_rgb(*top), bgcolor=Color.from_rgb(*bottom))
