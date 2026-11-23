"""The console's fixed colours, readable on Streamlit's light and dark themes.

The result's own theme colours (`heatmap.colors`) are ignored: they are made
for one background. Each colour here has a contrast ratio of at least 3:1
against both backgrounds below, which `test_palette` checks.
"""

LIGHT_BACKGROUND = "#FFFFFF"
DARK_BACKGROUND = "#0E1117"

# Heatmap bands 0 (slowest) to 4 (fastest).
BANDS = ("#E5484D", "#D9773E", "#8B8D98", "#3B96CA", "#5B6EE8")

ERROR = BANDS[0]
SUB = BANDS[2]
MAIN = BANDS[4]


def contrast_ratio(first: str, second: str) -> float:
    """The WCAG 2 contrast ratio of two `#RRGGBB` colours, from 1 to 21."""
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(colour: str) -> float:
    red, green, blue = (_linear(int(colour[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return float(((channel + 0.055) / 1.055) ** 2.4)
