import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from packages.vibe_coding_club.fukuoka_tenki_forcast import (
    fukuoka_tenki_cli,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.fixtures import (
    FakeSource,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.fukuoka_tenki_cli import (
    build_parser,
    run_cli,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.model import (
    ForecastError,
)
from packages.vibe_coding_club.fukuoka_tenki_forcast.tui_app import (
    TenkiApp,
)


class Terminal(io.StringIO):
    """A stdout that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


def run(stdout: io.StringIO, *argv: str) -> str:
    """Run the command line with `stdout` as sys.stdout and return what it printed."""
    with redirect_stdout(stdout):
        run_cli(build_parser().parse_args(argv))
    return stdout.getvalue()


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeSource()
        jma = patch.object(fukuoka_tenki_cli, "JmaSource", return_value=self.source)
        jma.start()
        self.addCleanup(jma.stop)
        tui = patch.object(TenkiApp, "run")
        self.run_tui = tui.start()
        self.addCleanup(tui.stop)

    def test_plain_text_when_not_a_terminal(self) -> None:
        out = run(io.StringIO())
        for title in (
            "■ 7日間の予報",
            "■ 3時間ごとの予報",
            "■ 福岡市の雨（ナウキャスト（1時間先まで））",
            "■ 福岡市の雨（降水短時間予報（15時間先まで））",
        ):
            self.assertIn(title, out)
        self.run_tui.assert_not_called()

    def test_tui_on_a_terminal(self) -> None:
        out = run(Terminal())
        self.assertEqual(out, "")
        self.run_tui.assert_called_once()

    def test_plain_flag_on_a_terminal(self) -> None:
        out = run(Terminal(), "--plain")
        self.assertIn("■ 7日間の予報", out)
        self.run_tui.assert_not_called()

    def test_error_exits_with_the_message(self) -> None:
        self.source.fail["forecast"] = ForecastError("天気予報を取得できませんでした")
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as exit_:
            run(stdout)
        self.assertEqual(exit_.exception.code, "エラー: 天気予報を取得できませんでした")
        self.assertEqual(stdout.getvalue(), "")

    def test_failed_extras_are_noted_and_the_rest_prints(self) -> None:
        self.source.fail["hourly"] = ForecastError(
            "3時間ごとの予報を取得できませんでした"
        )
        self.source.fail["radar_frames"] = ForecastError(
            "雨雲レーダーを取得できませんでした"
        )
        out = run(io.StringIO())
        self.assertIn(
            "■ 3時間ごとの予報\n  （3時間ごとの予報を取得できませんでした）", out
        )
        self.assertIn("  （雨雲レーダーを取得できませんでした）", out)
        self.assertIn("■ 7日間の予報", out)


if __name__ == "__main__":
    unittest.main()
