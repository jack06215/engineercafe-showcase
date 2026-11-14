"""Command line interface for Markdown (GFM) to DOCX conversion."""

import argparse
import functools
import logging
import os
import sys
from pathlib import Path

import pydantic

from packages.cli_complete import complete
from rules.markdown.md2docx import converter, diagrams
from rules.markdown.md2docx.diagrams import DiagramRenderer
from rules.markdown.md2docx.google_docs import PageSize

WORKSPACE_ENV = "BUILD_WORKSPACE_DIRECTORY"
"""Set by `bazel run`, which executes in the runfiles tree. Relative paths are
resolved against it so they mean the same thing under `bazel run` as outside."""

DEFAULT_OUTPUT_DIR = Path("build/docx")

logger = logging.getLogger(__name__)


class Args(pydantic.BaseModel):
    """Command line arguments."""

    srcs: list[Path]
    output_dir: Path = DEFAULT_OUTPUT_DIR
    page_size: PageSize = PageSize.A4
    enable_mermaid: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for this tool, reused as a subparser parent by packages/cli.py."""
    parser = argparse.ArgumentParser(
        prog="md2docx",
        description="Convert GitHub-flavoured Markdown to .docx in Google Docs' default style.",
    )
    parser.add_argument(
        "srcs",
        nargs="+",
        type=Path,
        metavar="SRC",
        help="Markdown files. A relative path keeps its directories under --output_dir.",
    )
    output_dir = parser.add_argument(
        "--output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write. Default: ./{DEFAULT_OUTPUT_DIR}.",
    )
    complete(output_dir, "directories")
    parser.add_argument(
        "--page_size",
        choices=[size.value for size in PageSize],
        default=PageSize.A4.value,
        help="Default: a4.",
    )
    parser.add_argument(
        "--enable-mermaid",
        action="store_true",
        help=(
            "Render ```mermaid blocks as pictures with mermaid-cli (`mmdc` from "
            f"PATH; install: {diagrams.INSTALL_HINT}). Without it they stay code "
            "blocks."
        ),
    )
    return parser


def run_cli(namespace: argparse.Namespace) -> None:
    """Validate a parsed command line into `Args` and run."""
    main(Args(**vars(namespace)))


def workspace_root() -> Path:
    """The directory relative paths are resolved against."""
    root = os.environ.get(WORKSPACE_ENV)
    return Path(os.path.normpath(root)) if root else Path.cwd()


def output_path(src: Path, *, root: Path, output_dir: Path) -> Path:
    """Where `src`'s .docx goes.

    Its path relative to `root`, under `output_dir`, so two `README.md`s in
    different directories can't overwrite each other. A file outside `root`
    keeps only its name.
    """
    absolute = Path(os.path.normpath(root / src))
    try:
        relative = absolute.relative_to(root)
    except ValueError:
        relative = Path(absolute.name)
    return root / output_dir / relative.with_suffix(".docx")


def main(args: Args) -> None:
    """Convert every src, carrying on past failures, and exit 1 if any failed."""
    logging.basicConfig(format="%(levelname)s: %(message)s")
    root = workspace_root()
    # One download per URL for the whole run: clipped notes share OG images.
    fetch = functools.cache(converter.fetch_url)
    render_diagram = (
        _diagram_renderer(cache_dir=root / args.output_dir / ".cache" / "mermaid")
        if args.enable_mermaid
        else None
    )

    failed = 0
    for src in args.srcs:
        target = output_path(src, root=root, output_dir=args.output_dir)
        try:
            converter.convert_file(
                root / src,
                target,
                page_size=args.page_size,
                fetch=fetch,
                render_diagram=render_diagram,
            )
        except Exception:
            logger.exception("failed to convert %s", src)
            failed += 1
            continue
        print(f"wrote {_display(target, root)}")

    if failed:
        print(f"{failed} of {len(args.srcs)} files failed", file=sys.stderr)
        sys.exit(1)


def _diagram_renderer(*, cache_dir: Path) -> DiagramRenderer:
    """mermaid-cli if it can be found, else a stand-in that says how to install it."""
    executable = diagrams.find_mmdc()
    if executable is not None:
        return diagrams.Mmdc(executable, cache_dir=cache_dir)
    return diagrams.unavailable(
        f"mermaid-cli (mmdc) not found; install it with: {diagrams.INSTALL_HINT}"
    )


def _display(path: Path, root: Path) -> Path:
    return path.relative_to(root) if path.is_relative_to(root) else path


if __name__ == "__main__":
    run_cli(build_parser().parse_args())
