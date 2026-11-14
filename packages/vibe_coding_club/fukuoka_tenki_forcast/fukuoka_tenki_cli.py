"""Show the Fukuoka City weather forecast: a TUI on a terminal, plain text otherwise.

This is the only module that knows both where the forecast comes from and how
it is shown; it wires the JMA source into whichever view was asked for.
"""

import argparse
import sys

import pydantic

from packages.vibe_coding_club.fukuoka_tenki_forcast.area import FUKUOKA
from packages.vibe_coding_club.fukuoka_tenki_forcast.formatting import (
    CITY_NAME,
    PRODUCT_NAMES,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.jma_client import (
    JmaSource,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    ForecastError,
    RadarProduct,
    WeatherSource,
    from_now,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.render_text import (
    render_hourly_text,
    render_rain_text,
    render_text,
    render_unavailable,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.tui_app import (
    TenkiApp,
)


class Args(pydantic.BaseModel):
    """Command line arguments."""

    plain: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for this app, in the shape packages/cli.py mounts."""
    parser = argparse.ArgumentParser(
        prog="fukuoka_tenki",
        description="Show the Fukuoka City weather forecast, 7-day outlook and rain "
        "radar, all from the JMA website.",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Print plain text instead of starting the TUI. "
        "Always the case when stdout is not a terminal.",
    )
    return parser


def run_cli(namespace: argparse.Namespace) -> None:
    """Validate a parsed command line into `Args` and run."""
    main(Args(**vars(namespace)))


def main(args: Args) -> None:
    source: WeatherSource = JmaSource(FUKUOKA)
    # Fall back to plain text when piped or redirected.
    if args.plain or not sys.stdout.isatty():
        print_forecast(source)
    else:
        TenkiApp(source).run()


def print_forecast(source: WeatherSource) -> None:
    """Print everything as text, exiting with status 1 if the forecast cannot be loaded.

    The 3-hourly forecast and the rain outlooks are extras: when one fails, its
    section says why and the rest still prints.
    """
    try:
        forecast = source.forecast()
    except ForecastError as e:
        raise SystemExit(f"エラー: {e}") from None
    sections = [render_text(forecast)]
    try:
        sections.append(render_hourly_text(source.hourly()))
    except ForecastError as e:
        sections.append(render_unavailable("3時間ごとの予報", str(e)))
    for product in RadarProduct:
        try:
            frames = from_now(source.radar_frames(product))
            sections.append(
                render_rain_text(product, frames, source.rain_at_city(frames))
            )
        except ForecastError as e:
            title = f"{CITY_NAME}の雨（{PRODUCT_NAMES[product]}）"
            sections.append(render_unavailable(title, str(e)))
    print("\n\n".join(sections))


if __name__ == "__main__":
    run_cli(build_parser().parse_args())
