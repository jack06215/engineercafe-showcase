"""JMA's precipitation legend: the eight colours of its radar and rain forecast maps."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RainLevel:
    """One step of the legend, in mm/h."""

    low: float
    high: float | None  # None for the open-ended top step
    color: tuple[int, int, int]
    words: str

    @property
    def label(self) -> str:
        """Return e.g. "1〜5" or "80〜"."""
        high = "" if self.high is None else f"{self.high:g}"
        return f"{self.low:g}〜{high}"


# The colours are the tiles' palette, the same for the nowcast and the 15-hour
# forecast. The words from 10 mm/h up are JMA's own terms (雨の強さと降り方).
RAIN_LEVELS = (
    RainLevel(0, 1, (242, 242, 255), "弱い雨"),
    RainLevel(1, 5, (160, 210, 255), "雨"),
    RainLevel(5, 10, (33, 140, 255), "雨"),
    RainLevel(10, 20, (0, 65, 255), "やや強い雨"),
    RainLevel(20, 30, (250, 245, 0), "強い雨"),
    RainLevel(30, 50, (255, 153, 0), "激しい雨"),
    RainLevel(50, 80, (255, 40, 0), "非常に激しい雨"),
    RainLevel(80, None, (180, 0, 104), "猛烈な雨"),
)

_BY_COLOR = {level.color: level for level in RAIN_LEVELS}


def rain_level(rgb: tuple[int, int, int]) -> RainLevel | None:
    """Return the level drawn in `rgb`, or None if it is not a legend colour."""
    return _BY_COLOR.get(rgb)
