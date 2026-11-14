import json
import os
import shlex
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any
from unittest import mock

from docx.image.image import Image

from rules.markdown.md2docx import diagrams
from rules.markdown.md2docx.diagrams import DiagramError, Mmdc


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _png(width: int, height: int, *, dpi: int | None = None) -> bytes:
    """A grey PNG, optionally carrying a pHYs chunk."""
    header = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    physical = b""
    if dpi is not None:
        per_metre = round(dpi / 0.0254)
        physical = _chunk(b"pHYs", struct.pack(">IIB", per_metre, per_metre, 1))
    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + header
        + physical
        + _chunk(b"IDAT", zlib.compress(rows))
        + _chunk(b"IEND", b"")
    )


def _chunk_types(png: bytes) -> list[bytes]:
    types, offset = [], 8
    while offset < len(png):
        (length,) = struct.unpack(">I", png[offset : offset + 4])
        types.append(png[offset + 4 : offset + 8])
        offset += 12 + length
    return types


# Stands in for mermaid-cli: records each render's arguments, then writes a PNG
# to the -o path -- or fails, hangs or writes nothing, as settings.json says.
_FAKE_MMDC = """\
import json, sys, time
from pathlib import Path

state = Path({state!r})
settings = json.loads((state / "settings.json").read_text())
args = sys.argv[1:]
if args == ["--version"]:
    print(settings["version"])
    sys.exit(0)
with (state / "calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
time.sleep(settings["sleep"])
if settings["exit"]:
    sys.stderr.write(settings["stderr"])
    sys.exit(settings["exit"])
if settings["write"]:
    Path(args[args.index("-o") + 1]).write_bytes(bytes.fromhex(settings["png"]))
"""


class _FakeMmdc:
    def __init__(self, directory: Path) -> None:
        self.state = directory
        script = directory / "fake_mmdc.py"
        script.write_text(_FAKE_MMDC.format(state=str(directory)), encoding="utf-8")
        self.executable = directory / "mmdc"
        self.executable.write_text(
            f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "
            '"$@"\n',
            encoding="utf-8",
        )
        self.executable.chmod(0o755)
        self.configure()

    def configure(self, **overrides: Any) -> None:
        settings = {
            "version": "11.0.0",
            "sleep": 0,
            "exit": 0,
            "stderr": "",
            "write": True,
            "png": _png(40, 20).hex(),
        }
        settings.update(overrides)
        (self.state / "settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )

    @property
    def calls(self) -> list[list[str]]:
        log = self.state / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]


class StampDpiTest(unittest.TestCase):
    def test_stamps_a_png_that_had_no_dpi(self) -> None:
        stamped = diagrams.stamp_dpi(_png(400, 200), 192)
        image = Image.from_blob(stamped)
        self.assertEqual((image.horz_dpi, image.vert_dpi), (192, 192))
        self.assertEqual((image.px_width, image.px_height), (400, 200))
        types = _chunk_types(stamped)
        self.assertEqual(types[:2], [b"IHDR", b"pHYs"])

    def test_replaces_an_existing_dpi(self) -> None:
        stamped = diagrams.stamp_dpi(_png(10, 10, dpi=72), 192)
        self.assertEqual(Image.from_blob(stamped).horz_dpi, 192)
        self.assertEqual(_chunk_types(stamped).count(b"pHYs"), 1)

    def test_rejects_what_is_not_a_png(self) -> None:
        with self.assertRaises(DiagramError):
            diagrams.stamp_dpi(b"<svg/>", 192)
        with self.assertRaises(DiagramError):
            diagrams.stamp_dpi(_png(10, 10)[:20], 192)


class MmdcTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.fake = _FakeMmdc(self.dir)
        self.cache = self.dir / "cache"

    def test_renders_at_2x_on_white_and_stamps_css_size(self) -> None:
        png = Mmdc(self.fake.executable)("flowchart TD\n  A --> B")
        image = Image.from_blob(png)
        self.assertEqual(image.horz_dpi, 192)
        (args,) = self.fake.calls
        self.assertEqual(args[args.index("-s") + 1], "2")
        self.assertEqual(args[args.index("-b") + 1], "white")
        self.assertIn("-c", args)
        self.assertIn("-q", args)

    def test_same_source_is_served_from_the_cache(self) -> None:
        render = Mmdc(self.fake.executable, cache_dir=self.cache)
        first = render("graph LR\n  a --> b")
        second = render("graph LR\n  a --> b")
        self.assertEqual(first, second)
        self.assertEqual(len(self.fake.calls), 1)
        render("graph LR\n  a --> c")
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(len(list(self.cache.glob("*.png"))), 2)
        self.assertEqual(list(self.cache.glob("*.partial")), [])

    def test_the_cache_survives_across_runs_until_mmdc_changes(self) -> None:
        Mmdc(self.fake.executable, cache_dir=self.cache)("graph LR\n  a --> b")
        Mmdc(self.fake.executable, cache_dir=self.cache)("graph LR\n  a --> b")
        self.assertEqual(len(self.fake.calls), 1)
        self.fake.configure(version="11.1.0")
        Mmdc(self.fake.executable, cache_dir=self.cache)("graph LR\n  a --> b")
        self.assertEqual(len(self.fake.calls), 2)

    def test_without_a_cache_every_call_renders(self) -> None:
        render = Mmdc(self.fake.executable)
        render("graph LR\n  a --> b")
        render("graph LR\n  a --> b")
        self.assertEqual(len(self.fake.calls), 2)

    def test_a_failed_render_reports_mmdc_stderr(self) -> None:
        self.fake.configure(exit=1, stderr="Error: Parse error on line 2:\n...\n")
        with self.assertRaises(DiagramError) as raised:
            Mmdc(self.fake.executable)("flowchart TD\n  A -->")
        self.assertIn("Parse error on line 2", str(raised.exception))
        self.assertIn("exited 1", str(raised.exception))

    def test_a_hung_render_times_out(self) -> None:
        self.fake.configure(sleep=5)
        with self.assertRaises(DiagramError) as raised:
            Mmdc(self.fake.executable, timeout_s=0.5)("graph LR\n  a --> b")
        self.assertIn("timed out", str(raised.exception))

    def test_a_render_that_writes_nothing_fails(self) -> None:
        self.fake.configure(write=False)
        with self.assertRaises(DiagramError):
            Mmdc(self.fake.executable)("graph LR\n  a --> b")

    def test_a_missing_executable_fails_as_a_diagram_error(self) -> None:
        with self.assertRaises(DiagramError):
            Mmdc(self.dir / "nowhere")("graph LR\n  a --> b")


class FindMmdcTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def test_found_on_path(self) -> None:
        executable = self.dir / "mmdc"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(self.dir)}):
            self.assertEqual(diagrams.find_mmdc(), executable)


class UnavailableTest(unittest.TestCase):
    def test_always_fails_with_the_reason(self) -> None:
        render = diagrams.unavailable("mmdc not found")
        with self.assertRaisesRegex(DiagramError, "mmdc not found"):
            render("graph LR\n  a --> b")


if __name__ == "__main__":
    unittest.main()
