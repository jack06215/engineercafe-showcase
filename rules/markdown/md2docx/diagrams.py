"""Mermaid diagrams to PNG, with mermaid-cli (`mmdc`).

Mermaid lays text out with a browser's layout engine, so it can't be rendered
from Python alone: mmdc drives a headless Chrome of its own (Chrome for
Testing, which puppeteer installs alongside it). It is a host tool, like
markdownlint and opencc in //rules/markdown -- see `INSTALL_HINT`.

The output is PNG, not SVG: python-docx embeds raster images only, and Google
Docs, which these documents are headed for, doesn't take SVG either.
"""

import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path

DiagramRenderer = Callable[[str], bytes]
"""Renders mermaid source to PNG bytes, raising `DiagramError` on failure."""

INSTALL_HINT = "npm install -g @mermaid-js/mermaid-cli"

_TIMEOUT_S = 60.0
_CSS_DPI = 96
_HOMEBREW_BINS = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
# Arial to match the document around the diagram. Chrome falls back to the
# system's CJK fonts for labels Arial has no glyphs for.
_CONFIG = {"theme": "default", "themeVariables": {"fontFamily": "Arial"}}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_METRES_PER_INCH = 0.0254


class DiagramError(Exception):
    """A diagram couldn't be rendered."""


class Mmdc:
    """Renders with mermaid-cli, caching the PNGs by what went into them."""

    def __init__(
        self,
        executable: Path,
        *,
        cache_dir: Path | None = None,
        scale: int = 2,
        timeout_s: float = _TIMEOUT_S,
    ) -> None:
        self._executable = executable
        self._cache_dir = cache_dir
        self._scale = scale
        self._timeout_s = timeout_s
        self._version: str | None = None

    def __call__(self, source: str) -> bytes:
        cached = self._cache_path(source)
        if cached is not None and cached.is_file():
            return cached.read_bytes()
        png = stamp_dpi(self._render(source), _CSS_DPI * self._scale)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            # Via a rename, so an interrupted run can't leave half a PNG that
            # later runs would keep serving.
            partial = cached.with_suffix(".partial")
            partial.write_bytes(png)
            partial.replace(cached)
        return png

    def _cache_path(self, source: str) -> Path | None:
        if self._cache_dir is None:
            return None
        # The mmdc version is part of the key, so an upgrade re-renders.
        key = json.dumps(
            [self._mmdc_version(), _CONFIG, self._scale, source], sort_keys=True
        )
        return self._cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.png"

    def _mmdc_version(self) -> str:
        if self._version is None:
            self._version = self._run(["--version"]).stdout.strip()
        return self._version

    def _render(self, source: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="md2docx-mermaid-") as temp:
            work = Path(temp)
            diagram = work / "diagram.mmd"
            config = work / "config.json"
            output = work / "diagram.png"
            diagram.write_text(source, encoding="utf-8")
            config.write_text(json.dumps(_CONFIG), encoding="utf-8")
            self._run(
                [
                    "-i",
                    str(diagram),
                    "-o",
                    str(output),
                    "-s",
                    str(self._scale),
                    "-b",
                    "white",
                    "-c",
                    str(config),
                    "-q",
                ]
            )
            if not output.is_file():
                raise DiagramError("mmdc exited cleanly but wrote no image")
            return output.read_bytes()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [str(self._executable), *args],
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise DiagramError(f"mmdc timed out after {self._timeout_s:g}s") from error
        except OSError as error:
            raise DiagramError(f"can't run {self._executable}: {error}") from error
        if result.returncode != 0:
            raise DiagramError(
                f"mmdc exited {result.returncode}: {_tail(result.stderr)}"
            )
        return result


def find_mmdc() -> Path | None:
    """The mermaid-cli executable, or None.

    `mmdc` from PATH -- the asdf or nvm shim under `bazel run`, which keeps the
    caller's PATH -- else a Homebrew prefix, the same fallbacks
    //rules/markdown's scripts use.
    """
    found = shutil.which("mmdc")
    if found is not None:
        return Path(found)
    for prefix in _HOMEBREW_BINS:
        candidate = prefix / "mmdc"
        if candidate.is_file():
            return candidate
    return None


def unavailable(reason: str) -> DiagramRenderer:
    """A renderer that always fails with `reason`.

    Stands in when mmdc is missing, so the warning only appears for notes that
    actually have a diagram in them.
    """

    def render(_source: str) -> bytes:
        raise DiagramError(reason)

    return render


def stamp_dpi(png: bytes, dpi: int) -> bytes:
    """Record `dpi` in the PNG's pHYs chunk, replacing any it had.

    Readers size an image by it. python-docx assumes 72dpi when it's missing,
    which would make a 2x render come out 2.7 times too big; stamped at
    96dpi x scale, it comes out at the diagram's CSS size.
    """
    if not png.startswith(_PNG_SIGNATURE):
        raise DiagramError("mmdc output is not a PNG")
    per_metre = round(dpi / _METRES_PER_INCH)
    physical = _chunk(b"pHYs", struct.pack(">IIB", per_metre, per_metre, 1))
    parts = [_PNG_SIGNATURE]
    for kind, raw in _chunks(png):
        if kind == b"pHYs":
            continue
        parts.append(raw)
        # The spec wants pHYs before the first IDAT; straight after the header
        # always is.
        if kind == b"IHDR":
            parts.append(physical)
    return b"".join(parts)


def _chunks(png: bytes) -> Iterator[tuple[bytes, bytes]]:
    """(type, raw bytes including length and CRC) for each chunk of `png`."""
    offset = len(_PNG_SIGNATURE)
    while offset < len(png):
        if offset + 8 > len(png):
            raise DiagramError("truncated PNG")
        (length,) = struct.unpack(">I", png[offset : offset + 4])
        kind = png[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(png):
            raise DiagramError("truncated PNG")
        yield kind, png[offset:end]
        if kind == b"IEND":
            return
        offset = end


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _tail(stderr: str, lines: int = 5) -> str:
    """The end of mmdc's stderr: where its parse errors say what went wrong."""
    kept = [line.strip() for line in stderr.splitlines() if line.strip()]
    return " / ".join(kept[-lines:]) or "no error output"
