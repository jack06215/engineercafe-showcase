"""Test data shared by the test_*.py files.

`testdata/real_words10.yml` is a real result, copied with `yr` on 2026-11-23.
The other files are written by hand in `yr`'s layout from it, one case each:

- `typos.yml`: first attempts, fixed, wrong and extra letters, an early space,
  an `inf` speed, and words that YAML would misread unquoted ("on", "null").
- `heatmap_off.yml`: `steps` without the labels and colours.
- `custom.yml`: custom mode, so no `language`.
- `chart_error.yml`: `chart_error` instead of a chart.
- `cpm.yml`: speeds in cpm, and a PB.
- `aborted.yml`: 20 keypresses and Monkeytype's `failed (min accuracy)` flag.
- `multi.yml`: three results; the first is `real_words10.yml` copied again
  later, the second has no chart and no input history, and the third has 20
  keypresses, so it counts as aborted too.
- `not_a_result.yml` and `broken.yml`: files the console must refuse.
"""

import shutil
from collections.abc import Iterable
from pathlib import Path

from packages.monkeytype_analysis_console.results import (
    ParsedFile,
    Result,
    parse_file,
)

TESTDATA = Path(__file__).resolve().parent / "testdata"
REAL = TESTDATA / "real_words10.yml"
TYPOS = TESTDATA / "typos.yml"
HEATMAP_OFF = TESTDATA / "heatmap_off.yml"
CUSTOM = TESTDATA / "custom.yml"
CHART_ERROR = TESTDATA / "chart_error.yml"
CPM = TESTDATA / "cpm.yml"
ABORTED = TESTDATA / "aborted.yml"
MULTI = TESTDATA / "multi.yml"
NOT_A_RESULT = TESTDATA / "not_a_result.yml"
BROKEN = TESTDATA / "broken.yml"

GOOD_FILES = (REAL, TYPOS, HEATMAP_OFF, CUSTOM, CHART_ERROR, CPM, ABORTED, MULTI)


def read(path: Path) -> ParsedFile:
    """Parses one fixture file."""
    return parse_file(path.name, path.read_bytes())


def result(path: Path, index: int = 0) -> Result:
    """One result of a fixture file that has no errors."""
    parsed = read(path)
    if parsed.errors:
        raise ValueError(f"{path.name} has errors: {parsed.errors}")
    return parsed.results[index]


def copy_to(folder: Path, paths: Iterable[Path]) -> None:
    """Copies fixture files into `folder`, keeping their names."""
    for path in paths:
        shutil.copyfile(path, folder / path.name)


def long_result_yaml(seconds: float = 739.6, word_count: int = 100) -> str:
    """A long result in `yr`'s layout: one chart row per second, and words.

    The last chart row is at `seconds`, which may be fractional. Word speeds
    cycle from 12 to 47 wpm, and the bands follow the steps 0, 14, 20, 27, 33.
    """
    steps = (0, 14, 20, 27, 33)
    times = [float(t) for t in range(1, int(seconds) + 1)]
    if seconds > int(seconds):
        times.append(seconds)
    lines = [
        "---",
        "datetime: 2026-11-23T12:08:10+09:00",
        "result:",
        "  wpm_threshold: 24",
        '  word_list: ""',
        '  missed_word_list: ""',
        '  slow_word: ""',
        "detail:",
        "  test: words 100",
        "  language: english 450k",
        "  unit: wpm",
        "  wpm: 17.51",
        "  raw: 17.51",
        "  acc: 91.02",
        "  time: 739.6",
        "  heatmap:",
        f"    steps: [{', '.join(map(str, steps))}]",
        "  chart:",
    ]
    for n, t in enumerate(times):
        speed = 10 + n % 30
        time_text = str(int(t)) if t.is_integer() else str(t)
        lines.append(
            f"    - {{t: {time_text}, wpm: {speed}, raw: {speed + 1}, "
            f"burst: {speed + 2}, errors: {n % 7 == 0:d}}}"
        )
    lines.append("  words:")
    for i in range(word_count):
        speed = 12 + i % 36
        band = sum(1 for step in steps[1:] if speed >= step)
        lines.append(f"    - {{i: {i}, word: word{i}, wpm: {speed}, bucket: {band}}}")
    return "\n".join(lines) + "\n"
