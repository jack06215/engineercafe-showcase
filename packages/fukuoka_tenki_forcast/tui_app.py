"""The Textual app: three tabs, each loading its data in the background."""

from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, TabbedContent, TabPane
from textual.worker import get_current_worker

from packages.fukuoka_tenki_forcast.formatting import (
    APP_TITLE,
    format_report,
)
from packages.fukuoka_tenki_forcast.model import (
    Forecast,
    ForecastError,
    Hourly,
    WeatherSource,
)
from packages.fukuoka_tenki_forcast.tui_radar import (
    RadarPanel,
)
from packages.fukuoka_tenki_forcast.tui_widgets import (
    DayCard,
    ErrorBanner,
    HourlyStrip,
    WeeklyKey,
    WeeklyTable,
)


class TenkiApp(App[None]):
    """Shows what `source` returns; knows nothing of where that comes from.

    Each tab loads on its own, so a failure in one leaves the others working:
    the forecast feeds the first two tabs, the 3-hourly forecast the first,
    and the radar tab loads nothing until it is opened.
    """

    TITLE = APP_TITLE
    # Three cards side by side need ~96 cells; stack them below that. App
    # annotates this as `ClassVar[...] | None`, which mypy reads as an instance
    # variable, so a ClassVar here would clash with it.
    HORIZONTAL_BREAKPOINTS: list[tuple[int, str]] | None = [  # noqa: RUF012
        (0, "-narrow"),
        (96, "-wide"),
    ]
    # Only the page layout: the widgets bring their own styles.
    CSS = """
    TabbedContent, ContentSwitcher, TabPane {
        height: 1fr;
    }
    TabPane {
        padding: 0;
    }
    #days {
        height: auto;
    }
    Screen.-narrow #days {
        layout: vertical;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "reload", "再読み込み"),
        Binding("q", "quit", "終了"),
        Binding("1", "show_tab('today')", "今日・明日", show=False),
        Binding("2", "show_tab('week')", "7日間", show=False),
        Binding("3", "show_tab('radar')", "雨雲レーダー", show=False),
    ]

    def __init__(self, source: WeatherSource) -> None:
        """Every call on `source` runs in a worker thread and may raise ForecastError."""
        super().__init__()
        self.source = source

    def compose(self) -> ComposeResult:
        """Lay out the header, error banner and tabs."""
        yield Header()
        yield ErrorBanner()
        with TabbedContent(id="tabs"):
            with TabPane("1 今日・明日", id="today"), VerticalScroll(id="today-view"):
                yield Horizontal(id="days")
                yield HourlyStrip()
            with TabPane("2 7日間", id="week"), VerticalScroll(id="week-view"):
                yield WeeklyTable()
                yield WeeklyKey()
            with TabPane("3 雨雲レーダー", id="radar"):
                yield RadarPanel(self.source)
        yield Footer()

    def on_mount(self) -> None:
        """Load the data when the app starts."""
        self.action_reload()

    def action_reload(self) -> None:
        """Reload the forecast, the hourly strip and the radar."""
        for view in self.query("#today-view, #week-view"):
            view.loading = True
        self.query_one(HourlyStrip).loading = True
        self.load_forecast()
        self.load_hourly()
        radar = self.query_one(RadarPanel)
        if radar.loaded:
            radar.reload()

    def action_show_tab(self, tab: str) -> None:
        """Switch to the tab with ID *tab*."""
        self.query_one(TabbedContent).active = tab

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Start the radar when its tab opens."""
        if event.pane.id == "radar":
            self.query_one(RadarPanel).activate()

    @work(thread=True, exclusive=True, group="forecast")
    def load_forecast(self) -> None:
        """Fetch the forecast in a worker thread and show it."""
        try:
            forecast = self.source.forecast()
        except ForecastError as e:
            if not get_current_worker().is_cancelled:
                self.call_from_thread(self.show_error, str(e))
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(self.show_forecast, forecast)

    @work(thread=True, exclusive=True, group="hourly")
    def load_hourly(self) -> None:
        """Fetch the 3-hourly forecast in a worker thread and show it."""
        try:
            hours = self.source.hourly()
        except ForecastError as e:
            if not get_current_worker().is_cancelled:
                self.call_from_thread(self.show_hourly_error, str(e))
            return
        if not get_current_worker().is_cancelled:
            self.call_from_thread(self.show_hourly, hours)

    def show_forecast(self, forecast: Forecast) -> None:
        """Show *forecast* in the day cards and the weekly table."""
        self.sub_title = format_report(forecast)
        self.query_one(ErrorBanner).set_error(None)

        days = self.query_one("#days", Horizontal)
        days.remove_children()
        days.mount_all(DayCard(day, forecast.reported.date()) for day in forecast.days)

        self.query_one(WeeklyTable).show_days(forecast.weekly, forecast.normals)
        self.query_one(WeeklyKey).show_normals(forecast.normals)
        for view in self.query("#today-view, #week-view"):
            view.loading = False

    def show_error(self, message: str) -> None:
        """Show *message* and stop the loading indicators."""
        self.query_one(ErrorBanner).set_error(message)
        for view in self.query("#today-view, #week-view"):
            view.loading = False

    def show_hourly(self, hours: tuple[Hourly, ...]) -> None:
        """Show *hours* in the hourly strip."""
        strip = self.query_one(HourlyStrip)
        strip.show_hours(hours)
        strip.loading = False

    def show_hourly_error(self, message: str) -> None:
        """Show *message* in the hourly strip."""
        strip = self.query_one(HourlyStrip)
        strip.show_error(message)
        strip.loading = False
