import base64
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docx
from docx.document import Document as DocxDocument

from rules.markdown.md2docx import diagrams, md2docx_cli
from rules.markdown.md2docx.google_docs import PageSize
from rules.markdown.md2docx.md2docx_cli import Args, output_path

ROOT = Path("/ws")
OUT = Path("build/docx")

_CHART = "graph LR\n  a --> b"
# One pixel, standing in for what mermaid-cli renders.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "2mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class OutputPathTest(unittest.TestCase):
    def test_relative_src_is_mirrored_under_the_output_dir(self) -> None:
        self.assertEqual(
            output_path(Path("docs/notes/a b.md"), root=ROOT, output_dir=OUT),
            Path("/ws/build/docx/docs/notes/a b.docx"),
        )

    def test_same_names_in_different_dirs_do_not_collide(self) -> None:
        git = output_path(Path("inbox/git/Useful.md"), root=ROOT, output_dir=OUT)
        ps = output_path(Path("inbox/PowerShell/Useful.md"), root=ROOT, output_dir=OUT)
        self.assertNotEqual(git, ps)

    def test_a_file_named_dot_md(self) -> None:
        # Path(".md").suffix is "", so this can't become a bare ".docx".
        self.assertEqual(
            output_path(Path("t/.md"), root=ROOT, output_dir=OUT),
            Path("/ws/build/docx/t/.md.docx"),
        )

    def test_parent_references_cannot_escape_the_output_dir(self) -> None:
        self.assertEqual(
            output_path(Path("docs/../a.md"), root=ROOT, output_dir=OUT),
            Path("/ws/build/docx/a.docx"),
        )
        self.assertEqual(
            output_path(Path("../elsewhere/b.md"), root=ROOT, output_dir=OUT),
            Path("/ws/build/docx/b.docx"),
        )

    def test_absolute_srcs(self) -> None:
        self.assertEqual(
            output_path(Path("/ws/docs/c.md"), root=ROOT, output_dir=OUT),
            Path("/ws/build/docx/docs/c.docx"),
        )
        self.assertEqual(
            output_path(Path("/tmp/d.md"), root=ROOT, output_dir=OUT),
            Path("/ws/build/docx/d.docx"),
        )

    def test_absolute_output_dir(self) -> None:
        self.assertEqual(
            output_path(Path("e.md"), root=ROOT, output_dir=Path("/out")),
            Path("/out/e.docx"),
        )


class ParserTest(unittest.TestCase):
    def test_defaults(self) -> None:
        namespace = md2docx_cli.build_parser().parse_args(["a.md", "b.md"])
        args = Args(**vars(namespace))
        self.assertEqual(args.srcs, [Path("a.md"), Path("b.md")])
        self.assertEqual(args.output_dir, Path("build/docx"))
        self.assertIs(args.page_size, PageSize.A4)
        self.assertFalse(args.enable_mermaid)

    def test_letter(self) -> None:
        namespace = md2docx_cli.build_parser().parse_args(
            ["--page_size", "letter", "a.md"]
        )
        self.assertIs(Args(**vars(namespace)).page_size, PageSize.LETTER)

    def test_enable_mermaid(self) -> None:
        namespace = md2docx_cli.build_parser().parse_args(["--enable-mermaid", "a.md"])
        self.assertTrue(Args(**vars(namespace)).enable_mermaid)


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        # resolve(): on macOS the temp dir is reached through a /var symlink.
        self.root = Path(temp.name).resolve()
        (self.root / "notes").mkdir()
        (self.root / "notes" / "one.md").write_text("# One\n", encoding="utf-8")
        (self.root / "notes" / "two words.md").write_text("two\n", encoding="utf-8")
        patcher = mock.patch.dict(
            os.environ, {md2docx_cli.WORKSPACE_ENV: str(self.root)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, *srcs: str) -> str:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            md2docx_cli.main(Args(srcs=[Path(src) for src in srcs]))
        return stdout.getvalue()

    def test_relative_paths_resolve_against_the_workspace(self) -> None:
        output = self._run("notes/one.md", "notes/two words.md")
        self.assertEqual(
            output.splitlines(),
            [
                "wrote build/docx/notes/one.docx",
                "wrote build/docx/notes/two words.docx",
            ],
        )
        document = docx.Document(str(self.root / "build/docx/notes/one.docx"))
        self.assertEqual(document.paragraphs[0].text, "One")

    def _convert_chart(self, *, enable_mermaid: bool) -> DocxDocument:
        (self.root / "notes" / "chart.md").write_text(
            f"```mermaid\n{_CHART}\n```\n", encoding="utf-8"
        )
        with contextlib.redirect_stdout(io.StringIO()):
            md2docx_cli.main(
                Args(srcs=[Path("notes/chart.md")], enable_mermaid=enable_mermaid)
            )
        return docx.Document(str(self.root / "build/docx/notes/chart.docx"))

    def test_mermaid_quietly_stays_code_unless_enabled(self) -> None:
        with (
            mock.patch.object(diagrams, "find_mmdc") as find_mmdc,
            self.assertNoLogs("rules.markdown.md2docx.converter", "WARNING"),
        ):
            document = self._convert_chart(enable_mermaid=False)
        find_mmdc.assert_not_called()
        self.assertEqual(document.paragraphs[0].text, _CHART)
        self.assertEqual(len(document.inline_shapes), 0)

    def test_enabled_without_mmdc_keeps_code_and_says_how_to_install(self) -> None:
        with (
            mock.patch.object(diagrams, "find_mmdc", return_value=None),
            self.assertLogs("rules.markdown.md2docx.converter", "WARNING") as logs,
        ):
            document = self._convert_chart(enable_mermaid=True)
        self.assertIn(diagrams.INSTALL_HINT, logs.output[0])
        self.assertEqual(document.paragraphs[0].text, _CHART)
        self.assertEqual(len(document.inline_shapes), 0)

    def test_enabled_renders_with_the_mmdc_it_finds(self) -> None:
        executable = Path("/opt/homebrew/bin/mmdc")
        with (
            mock.patch.object(diagrams, "find_mmdc", return_value=executable),
            mock.patch.object(diagrams, "Mmdc") as mmdc,
        ):
            mmdc.return_value.return_value = _PNG
            document = self._convert_chart(enable_mermaid=True)
        mmdc.assert_called_once_with(
            executable, cache_dir=self.root / "build/docx/.cache/mermaid"
        )
        mmdc.return_value.assert_called_once_with(_CHART)
        self.assertEqual(len(document.inline_shapes), 1)

    def test_a_failing_file_does_not_stop_the_rest(self) -> None:
        stderr = io.StringIO()
        with (
            self.assertLogs(md2docx_cli.logger, "ERROR"),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            self._run("notes/missing.md", "notes/one.md")
        self.assertEqual(raised.exception.code, 1)
        self.assertTrue((self.root / "build/docx/notes/one.docx").is_file())
        self.assertIn("1 of 2 files failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
