"""The TUI's widgets. Each one carries its own look in DEFAULT_CSS."""

import datetime
from collections.abc import Sequence

from rich.text import Text
from textual.widgets import DataTable, Static

from packages.fukuoka_tenki_forcast.charts import (
    BAND,
    BAR,
    NORMAL,
    TempScale,
    hourly_chart,
    temp_bar,
    week_scale,
)
from packages.fukuoka_tenki_forcast.formatting import (
    day_title,
    format_date,
    normals_text,
    pad,
    slot_label,
)
from packages.fukuoka_tenki_forcast.model import (
    DayForecast,
    Hourly,
    Normals,
    WeeklyDay,
)
from packages.fukuoka_tenki_forcast.weather_codes import (
    weather_category,
    weather_emoji,
    weather_label,
)

CATEGORY_CLASSES = {"100": "sunny", "200": "cloudy", "300": "rainy", "400": "snowy"}
MIN_STYLE = "bold dodger_blue1"
MAX_STYLE = "bold red1"
WEEKLY_COLUMNS = ("日付", "天気", "最低", "気温", "最高", "降水確率", "信頼度")


def pop_bar(pop: int, width: int) -> Text:
    """Render a probability of precipitation as e.g. "███░░░░░░░  30%"."""
    filled = round(pop * width / 100)
    bar = Text("█" * filled, style="dodger_blue1")
    bar.append("░" * (width - filled), style="grey35")
    bar.append(f" {pop:>3}%")
    return bar


def date_text(date: datetime.date) -> Text:
    """The date, in blue on Saturdays and red on Sundays."""
    weekday = date.weekday()
    style = "dodger_blue1" if weekday == 5 else "red1" if weekday == 6 else ""
    return Text(format_date(date), style=style)


def temp_text(temp: int | None, style: str) -> Text:
    """Format *temp* in degrees Celsius, or a dim dash if it is unknown."""
    if temp is None:
        return Text("-", style="dim")
    return Text(f"{temp}℃", style=style)


def day_card_content(day: DayForecast) -> Text:
    """Build the text of one day card."""
    text = Text()
    text.append(f"{weather_emoji(day.weather_code)} ")
    text.append(day.weather, style="bold")
    text.append("\n\n")

    if day.temp_min is not None or day.temp_max is not None:
        if day.temp_min is not None:
            text.append("最低 ", style="dim")
            text.append(f"{day.temp_min}℃", style=MIN_STYLE)
            text.append("  ")
        if day.temp_max is not None:
            text.append("最高 ", style="dim")
            text.append(f"{day.temp_max}℃", style=MAX_STYLE)
        text.append("\n\n")

    if day.pops:
        text.append("降水確率\n", style="dim")
        for slot in day.pops:
            text.append(pad(slot_label(slot), 8))
            text.append_text(pop_bar(slot.pop, 10))
            text.append("\n")
        text.append("\n")

    text.append("風 ", style="dim")
    text.append(day.wind)
    if day.wave:
        text.append("\n波 ", style="dim")
        text.append(day.wave)
    return text


def weekly_row(
    day: WeeklyDay, scale: TempScale, normals: Normals | None
) -> tuple[Text, ...]:
    """One row of the weekly table, in the order of WEEKLY_COLUMNS."""
    return (
        date_text(day.date),
        Text(weather_label(day.weather_code)),
        temp_text(day.temp_min, MIN_STYLE),
        temp_bar(day, scale, normals),
        temp_text(day.temp_max, MAX_STYLE),
        Text("-", style="dim") if day.pop is None else pop_bar(day.pop, 5),
        Text(day.reliability or "-", style="" if day.reliability else "dim"),
    )


def weekly_key(normals: Normals | None) -> Text:
    """What the weekly table's bars mean, and the week's normals."""
    key = Text.assemble(
        (BAR, "gold1"),
        " 予想の最低〜最高  ",
        (BAND, "grey42"),
        " 予想の幅  ",
        (NORMAL, "grey50"),
        " 平年値",
    )
    if normals is not None:
        key.append(f"\n{normals_text(normals)}", style="dim")
    return key


class DayCard(Static):
    """One day of the detailed forecast, bordered in the colour of its weather."""

    DEFAULT_CSS = """
    DayCard {
        width: 1fr;
        height: auto;
        margin: 1 1 0 1;
        padding: 0 1;
        border: round $primary;
        border-title-style: bold;
    }
    DayCard.sunny {
        border: round orange;
    }
    DayCard.cloudy {
        border: round gray;
    }
    DayCard.rainy {
        border: round dodgerblue;
    }
    DayCard.snowy {
        border: round white;
    }
    """

    def __init__(self, day: DayForecast, today: datetime.date) -> None:
        """Show *day*, titled relative to *today*."""
        category = CATEGORY_CLASSES.get(weather_category(day.weather_code), "")
        super().__init__(day_card_content(day), classes=category)
        self.border_title = day_title(day.date, today)


class WeeklyTable(DataTable[Text]):
    """The seven days ahead, one row per day, with a bar chart of the temperatures.

    Hidden until it has rows. `WeeklyKey` explains the bars.
    """

    DEFAULT_CSS = """
    WeeklyTable {
        display: none;
        height: auto;
        margin: 1 1 0 1;
        border: round $primary;
        border-title-style: bold;
    }
    """

    def __init__(self) -> None:
        """Set up an empty, striped table."""
        super().__init__(cursor_type="none", zebra_stripes=True)
        self.border_title = "7日間の予報"

    def show_days(self, days: Sequence[WeeklyDay], normals: Normals | None) -> None:
        """Fill the table with one row per day in *days*."""
        # Columns need a running app, so they are added on first use rather
        # than in __init__.
        if not self.columns:
            self.add_columns(*WEEKLY_COLUMNS)
        self.clear()
        scale = week_scale(days, normals)
        for day in days:
            self.add_row(*weekly_row(day, scale, normals))
        self.display = True


class WeeklyKey(Static):
    """The key to the weekly table's bars. Hidden until the table has rows."""

    DEFAULT_CSS = """
    WeeklyKey {
        display: none;
        margin: 0 2 1 2;
    }
    """

    def show_normals(self, normals: Normals | None) -> None:
        """Show the key for *normals* and make it visible."""
        self.update(weekly_key(normals))
        self.display = True


class HourlyStrip(Static):
    """The 3-hourly forecast for about the next 30 hours."""

    DEFAULT_CSS = """
    HourlyStrip {
        height: auto;
        min-height: 3;
        margin: 1 1 0 1;
        padding: 0 1;
        border: round $primary;
        border-title-style: bold;
    }
    """

    def __init__(self) -> None:
        """Set up the strip with its border title."""
        super().__init__()
        self.border_title = "3時間ごとの予報"

    def show_hours(self, hours: Sequence[Hourly]) -> None:
        """Show the chart of *hours*, cropped to the screen width."""
        chart = hourly_chart(hours)
        # Too narrow a screen crops the right-hand hours rather than wrapping.
        chart.no_wrap = True
        chart.overflow = "crop"
        self.update(chart)

    def show_error(self, message: str) -> None:
        """Show *message* in red in place of the chart."""
        self.update(Text(message, style="red"))


class ErrorBanner(Static):
    """Why the last load failed, and how to retry. Hidden while all is well."""

    DEFAULT_CSS = """
    ErrorBanner {
        display: none;
        margin: 1 1 0 1;
        padding: 0 1;
        border: round $error;
        color: $error;
    }
    """

    def set_error(self, message: str | None) -> None:
        """Show `message`, or hide the banner when it is None."""
        if message is not None:
            self.update(Text.assemble(message, ("\nr で再読み込みします", "dim")))
        self.display = message is not None
