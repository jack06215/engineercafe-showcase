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
- `progress.yml`: 9 results over 5 days, for the Progress tests: two word
  lists and two test types, words that are slow or mistyped more than once,
  the key confusion e→r twice, a PB, and an aborted result last.

`fake_claude` stands in for the Anthropic client, so no test calls the API.
"""

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest import mock

import anthropic
import httpx2
from anthropic.types.beta import BetaFallbackBlock, BetaMessage, BetaTextBlock

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
PROGRESS = TESTDATA / "progress.yml"

GOOD_FILES = (REAL, TYPOS, HEATMAP_OFF, CUSTOM, CHART_ERROR, CPM, ABORTED, MULTI)

_API_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


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


def claude_message(
    answer: object,
    stop_reason: str = "end_turn",
    declined_first: bool = False,
) -> BetaMessage:
    """A Messages API response whose text is `answer` as JSON.

    A string `answer` is sent as it is. With `declined_first`, a model writes
    some text and declines, and a fallback model writes the answer.
    """
    text = answer if isinstance(answer, str) else json.dumps(answer)
    content: list[Any] = [BetaTextBlock(type="text", text=text)]
    if declined_first:
        content[:0] = [
            BetaTextBlock(type="text", text='{"gro'),
            BetaFallbackBlock.model_validate(
                {
                    "type": "fallback",
                    "from": {"model": "claude-opus-5-5"},
                    "to": {"model": "claude-opus-4-8"},
                    "trigger": {"type": "refusal", "category": None},
                }
            ),
        ]
    return BetaMessage.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": [block.model_dump(by_alias=True) for block in content],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1234, "output_tokens": 56},
        }
    )


def fake_claude(*replies: BetaMessage | Exception) -> mock.MagicMock:
    """A client whose `beta.messages.create` records each request.

    Each call returns, or raises, the next of `replies`.
    """
    client = mock.MagicMock(spec_set=["beta"])
    client.beta.messages.create.side_effect = list(replies)
    return client


def api_error(
    error: type[anthropic.APIStatusError],
    status: int,
    headers: dict[str, str] | None = None,
) -> anthropic.APIStatusError:
    """An error the SDK raises for an HTTP `status` answer."""
    response = httpx2.Response(status, headers=headers, request=_API_REQUEST)
    return error("error from the test", response=response, body=None)


def connection_error() -> anthropic.APIConnectionError:
    """The error the SDK raises when it can't reach the API."""
    return anthropic.APIConnectionError(request=_API_REQUEST)


def timeout_error() -> anthropic.APITimeoutError:
    """The error the SDK raises when a request times out."""
    return anthropic.APITimeoutError(request=_API_REQUEST)


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
