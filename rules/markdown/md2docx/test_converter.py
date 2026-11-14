import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.opc.part import XmlPart
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.shared import Emu, Inches, Pt, RGBColor, Twips
from docx.styles.style import ParagraphStyle
from docx.text.paragraph import Paragraph

from rules.markdown.md2docx import converter, diagrams, google_docs
from rules.markdown.md2docx.diagrams import DiagramError, DiagramRenderer
from rules.markdown.md2docx.google_docs import PageSize

TESTDATA = Path(__file__).resolve().parent / "testdata"


def _png(width: int, height: int) -> bytes:
    """A grey PNG of the given pixel size, at the 72dpi python-docx assumes."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def _no_network(url: str) -> bytes:
    raise AssertionError(f"unexpected fetch of {url}")


def _convert(
    markdown: str,
    *,
    base_dir: Path | None = None,
    fetch: converter.Fetch = _no_network,
    page_size: PageSize = PageSize.A4,
    render_diagram: DiagramRenderer | None = None,
) -> DocxDocument:
    return converter.convert(
        markdown,
        base_dir=base_dir or Path(),
        fetch=fetch,
        page_size=page_size,
        render_diagram=render_diagram,
    )


def _texts(document: DocxDocument) -> list[str]:
    return [paragraph.text for paragraph in document.paragraphs]


def _list_item(paragraph: Paragraph) -> tuple[int, int] | None:
    """(num id, level) of a list paragraph, None for anything else."""
    num_ids = paragraph._p.xpath("./w:pPr/w:numPr/w:numId/@w:val")
    levels = paragraph._p.xpath("./w:pPr/w:numPr/w:ilvl/@w:val")
    if not num_ids:
        return None
    return int(num_ids[0]), int(levels[0])


def _style(paragraph: Paragraph) -> str | None:
    return paragraph.style.name if paragraph.style is not None else None


def _paragraph_style(document: DocxDocument, name: str) -> ParagraphStyle:
    style = document.styles[name]
    assert isinstance(style, ParagraphStyle)
    return style


def _level(document: DocxDocument, num_id: int, level: int) -> tuple[str, str, int]:
    """(numFmt, lvlText, start) of `level` in the list `num_id` points at."""
    numbering = document.part.numbering_part.element
    num = numbering.num_having_numId(num_id)
    abstract_id = num.abstractNumId.val
    (definition,) = numbering.xpath(
        f'w:abstractNum[@w:abstractNumId="{abstract_id}"]/w:lvl[@w:ilvl="{level}"]'
    )
    return (
        definition.find(qn("w:numFmt")).get(qn("w:val")),
        definition.find(qn("w:lvlText")).get(qn("w:val")),
        int(definition.find(qn("w:start")).get(qn("w:val"))),
    )


def _border(paragraph: Paragraph, side: str) -> BaseOxmlElement | None:
    return paragraph._p.find(f"{qn('w:pPr')}/{qn('w:pBdr')}/{qn(f'w:{side}')}")


def _hyperlink_targets(document: DocxDocument) -> list[str]:
    rels = document.part.rels
    return [
        rels[link.get(qn("r:id"))].target_ref
        for link in document.element.body.iter(qn("w:hyperlink"))
        if link.get(qn("r:id"))
    ]


class GoogleDocsStyleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _convert("# Title\n\nBody.\n")

    def test_defaults_are_arial_11_at_1_15_with_no_spacing(self) -> None:
        styles = self.document.styles.element
        (fonts,) = styles.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts")
        self.assertEqual(
            dict(fonts.attrib),
            {qn(f"w:{slot}"): "Arial" for slot in ("ascii", "hAnsi", "eastAsia", "cs")},
            "no theme-font attribute may survive: it would outrank Arial",
        )
        (size,) = styles.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:sz")
        self.assertEqual(size.get(qn("w:val")), "22")
        (spacing,) = styles.xpath("w:docDefaults/w:pPrDefault/w:pPr/w:spacing")
        self.assertEqual(
            {key.split("}")[1]: value for key, value in spacing.attrib.items()},
            {"before": "0", "after": "0", "line": "276", "lineRule": "auto"},
        )

    def test_normal_carries_the_font_itself(self) -> None:
        normal = _paragraph_style(self.document, "Normal")
        self.assertEqual(normal.font.name, "Arial")
        self.assertEqual(normal.font.size, Pt(11))

    def test_headings_match_google_docs(self) -> None:
        expected = {
            "Heading 1": (20, 20, 6, None),
            "Heading 2": (16, 18, 6, None),
            "Heading 3": (14, 16, 4, "434343"),
            "Heading 4": (12, 14, 4, "666666"),
            "Heading 5": (11, 12, 4, "666666"),
            "Heading 6": (11, 12, 4, "666666"),
        }
        for name, (size, before, after, color) in expected.items():
            with self.subTest(style=name):
                style = _paragraph_style(self.document, name)
                self.assertEqual(style.font.size, Pt(size))
                self.assertEqual(style.paragraph_format.space_before, Pt(before))
                self.assertEqual(style.paragraph_format.space_after, Pt(after))
                self.assertEqual(
                    style.font.color.rgb,
                    RGBColor.from_string(color) if color else None,
                )
                self.assertIsNone(style.font.bold, "Google Docs headings are not bold")
                self.assertIsNone(style.element.find(f"{qn('w:rPr')}/{qn('w:rFonts')}"))
                outline = style.element.find(f"{qn('w:pPr')}/{qn('w:outlineLvl')}")
                self.assertEqual(outline.get(qn("w:val")), str(int(name[-1]) - 1))
        self.assertTrue(_paragraph_style(self.document, "Heading 6").font.italic)

    def test_title_loses_the_word_template_border(self) -> None:
        title = _paragraph_style(self.document, "Title")
        self.assertEqual(title.font.size, Pt(26))
        self.assertIsNone(title.element.find(f"{qn('w:pPr')}/{qn('w:pBdr')}"))

    def test_page_is_a4_with_one_inch_margins(self) -> None:
        section = self.document.sections[0]
        assert section.page_width is not None and section.page_height is not None
        # Stored in whole twips: 210 x 297mm is Word's 11906 x 16838.
        self.assertEqual(
            (section.page_width.twips, section.page_height.twips), (11906, 16838)
        )
        for margin in (
            section.top_margin,
            section.bottom_margin,
            section.left_margin,
            section.right_margin,
        ):
            self.assertEqual(margin, Inches(1))

    def test_letter_page(self) -> None:
        section = _convert("x", page_size=PageSize.LETTER).sections[0]
        self.assertEqual(
            (section.page_width, section.page_height), (Inches(8.5), Inches(11))
        )

    def test_roboto_mono_is_declared_fixed_pitch(self) -> None:
        font_table = self.document.part.part_related_by(RELATIONSHIP_TYPE.FONT_TABLE)
        self.assertIsInstance(font_table, XmlPart)
        assert isinstance(font_table, XmlPart)
        (font,) = [
            font
            for font in font_table.element.iterchildren(qn("w:font"))
            if font.get(qn("w:name")) == "Roboto Mono"
        ]
        self.assertEqual(font.find(qn("w:pitch")).get(qn("w:val")), "fixed")
        self.assertEqual(font.find(qn("w:family")).get(qn("w:val")), "modern")

    def test_metadata(self) -> None:
        properties = self.document.core_properties
        self.assertEqual(properties.title, "Title")
        self.assertEqual(properties.author, "")
        assert properties.created is not None
        self.assertGreater(properties.created.year, 2013)


class BlockTest(unittest.TestCase):
    def test_blank_line_between_blocks_but_not_around_headings(self) -> None:
        document = _convert("# H\n\none\n\ntwo\n\n## H2\n\nthree\n")
        self.assertEqual(_texts(document), ["H", "one", "", "two", "H2", "three"])
        self.assertEqual(_style(document.paragraphs[0]), "Heading 1")
        self.assertEqual(_style(document.paragraphs[4]), "Heading 2")

    def test_rule_takes_a_blank_line_only_below(self) -> None:
        document = _convert("above\n\n---\n\nbelow\n")
        self.assertEqual(_texts(document), ["above", "", "", "below"])
        self.assertIsNotNone(_border(document.paragraphs[1], "bottom"))
        self.assertIsNone(_border(document.paragraphs[2], "bottom"))

    def test_front_matter_is_dropped(self) -> None:
        document = _convert("---\ntitle: x\n---\n\nbody\n")
        self.assertEqual(_texts(document), ["body"])

    def test_code_block_is_one_paragraph_keeping_lines_and_tabs(self) -> None:
        document = _convert("```py\ndef f():\n\treturn 1\n```\n")
        (paragraph,) = document.paragraphs
        self.assertEqual(_style(paragraph), google_docs.CODE_BLOCK_STYLE)
        self.assertEqual(paragraph.text, "def f():\n\treturn 1")
        self.assertEqual(len(paragraph._p.xpath(".//w:br")), 1)
        self.assertEqual(len(paragraph._p.xpath(".//w:tab")), 1)

    def test_blockquote_is_indented_and_barred_including_its_blank_lines(self) -> None:
        document = _convert("> one\n>\n> two\n")
        self.assertEqual(_texts(document), ["one", "", "two"])
        for paragraph in document.paragraphs:
            self.assertEqual(paragraph.paragraph_format.left_indent, Twips(360))
            self.assertIsNotNone(_border(paragraph, "left"))
        self.assertEqual(
            document.paragraphs[0].runs[0].font.color.rgb,
            RGBColor.from_string("666666"),
        )

    def test_html_block_keeps_its_text(self) -> None:
        document = _convert(
            "<div>\nraw &amp; <b>html</b>\n</div>\n\n<!-- gone -->\n\nafter\n"
        )
        self.assertEqual(_texts(document), ["raw & html", "", "after"])


class InlineTest(unittest.TestCase):
    def test_emphasis(self) -> None:
        (paragraph,) = _convert("**b** *i* ~~s~~").paragraphs
        runs = {run.text: run for run in paragraph.runs}
        self.assertTrue(runs["b"].bold)
        self.assertTrue(runs["i"].italic)
        self.assertTrue(runs["s"].font.strike)

    def test_inline_code_uses_the_code_style(self) -> None:
        (paragraph,) = _convert("run `ls -la` now").paragraphs
        code = next(run for run in paragraph.runs if run.text == "ls -la")
        self.assertEqual(code.style.name, google_docs.CODE_STYLE)
        self.assertEqual(code.style.font.color.rgb, RGBColor.from_string("188038"))

    def test_links_and_autolinks_become_hyperlinks(self) -> None:
        document = _convert(
            "[text **bold**](https://example.com/a) www.example.org a@b.co"
        )
        self.assertEqual(
            _hyperlink_targets(document),
            ["https://example.com/a", "http://www.example.org", "mailto:a@b.co"],
        )
        (link, *_) = document.element.body.iter(qn("w:hyperlink"))
        colors = link.xpath(".//w:color/@w:val")
        self.assertEqual(set(colors), {"1155CC"})
        self.assertEqual(
            len(link.xpath(".//w:b")), 1, "formatting survives inside the link"
        )

    def test_softbreak_is_a_space_except_between_cjk(self) -> None:
        cases = {
            "one\ntwo": "one two",
            "日本語の\n文章": "日本語の文章",
            "漢字。\n次の行": "漢字。次の行",
            "end\n日本": "end 日本",
            "한국어\n문장": "한국어 문장",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                (paragraph,) = _convert(source).paragraphs
                self.assertEqual(paragraph.text, expected)

    def test_html_break_and_other_inline_html(self) -> None:
        (paragraph,) = _convert("a<br>b <kbd>K</kbd>").paragraphs
        self.assertEqual(paragraph.text, "a\nb K")

    def test_hard_break(self) -> None:
        (paragraph,) = _convert("a  \nb").paragraphs
        self.assertEqual(paragraph.text, "a\nb")

    def test_footnotes(self) -> None:
        document = _convert("Claim.[^a] More.[^b]\n\n[^a]: First.\n[^b]: Second.\n")
        body = document.paragraphs[0]
        refs = [run for run in body.runs if run.font.superscript]
        self.assertEqual([run.text for run in refs], ["1", "2"])
        texts = _texts(document)
        self.assertEqual(texts[-2:], ["First.", "Second."])
        first = _list_item(document.paragraphs[-2])
        assert first is not None
        self.assertEqual(_level(document, first[0], 0), ("decimal", "%1.", 1))
        self.assertEqual(_list_item(document.paragraphs[-1]), first)


class ListTest(unittest.TestCase):
    def test_bullets_nest_with_google_glyphs(self) -> None:
        document = _convert("- a\n  - b\n    - c\n      - d\n")
        items = [_list_item(p) for p in document.paragraphs]
        self.assertEqual([item[1] for item in items if item], [0, 1, 2, 3])
        first = items[0]
        assert first is not None
        glyphs = [_level(document, first[0], level)[1] for level in range(4)]
        self.assertEqual(glyphs, ["●", "○", "■", "●"])

    def test_ordered_lists_start_where_markdown_says_and_restart(self) -> None:
        document = _convert("3. three\n4. four\n\nbreak\n\n1. again\n")
        self.assertEqual(_texts(document), ["three", "four", "", "break", "", "again"])
        first, again = (
            _list_item(document.paragraphs[0]),
            _list_item(document.paragraphs[-1]),
        )
        assert first is not None and again is not None
        self.assertNotEqual(first[0], again[0])
        self.assertEqual(_level(document, first[0], 0), ("decimal", "%1.", 3))
        self.assertEqual(_level(document, again[0], 0), ("decimal", "%1.", 1))
        # Separate definitions, not just separate nums: Quick Look counts
        # straight on across nums that share one.
        numbering = document.part.numbering_part.element
        self.assertNotEqual(
            numbering.num_having_numId(first[0]).abstractNumId.val,
            numbering.num_having_numId(again[0]).abstractNumId.val,
        )

    def test_nested_ordered_list_formats(self) -> None:
        document = _convert("1. a\n   1. b\n      1. c\n")
        levels = [_list_item(p) for p in document.paragraphs]
        formats = [
            _level(document, item[0], item[1])[:2]
            for item in levels
            if item is not None
        ]
        self.assertEqual(
            formats, [("decimal", "%1."), ("lowerLetter", "%2."), ("lowerRoman", "%3.")]
        )

    def test_task_items_get_checkboxes_instead_of_bullets(self) -> None:
        document = _convert("- [ ] open\n- [x] done\n- plain\n")
        self.assertEqual(_texts(document), ["open", "done", "plain"])
        glyphs = []
        for paragraph in document.paragraphs:
            item = _list_item(paragraph)
            assert item is not None
            glyphs.append(_level(document, *item)[1])
        self.assertEqual(glyphs, ["☐", "☑", "●"])

    def test_no_blank_lines_inside_lists_and_continuations_are_indented(self) -> None:
        document = _convert("- one\n\n  more of one\n- two\n")
        self.assertEqual(_texts(document), ["one", "more of one", "two"])
        continuation = document.paragraphs[1]
        self.assertIsNone(_list_item(continuation))
        self.assertEqual(continuation.paragraph_format.left_indent, Twips(720))

    def test_item_that_opens_with_a_nested_list_still_gets_its_bullet(self) -> None:
        document = _convert("- - inner\n")
        items = [_list_item(p) for p in document.paragraphs]
        self.assertEqual([item[1] if item else None for item in items], [0, 1])

    def test_abstract_nums_precede_nums(self) -> None:
        document = _convert("- a\n\n1. b\n\npara\n\n1. c\n")
        tags = [child.tag for child in document.part.numbering_part.element]
        last_abstract = max(
            i for i, tag in enumerate(tags) if tag == qn("w:abstractNum")
        )
        first_num = min(i for i, tag in enumerate(tags) if tag == qn("w:num"))
        self.assertLess(last_abstract, first_num)


class TableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _convert(
            "| L | R | C |\n|:--|--:|:-:|\n| a | **1** | x |\n| short |\n"
        )
        (self.table,) = self.document.tables

    def test_shape_and_header(self) -> None:
        self.assertEqual((len(self.table.rows), len(self.table.columns)), (3, 3))
        header = self.table.rows[0]
        self.assertTrue(
            all(run.bold for cell in header.cells for run in cell.paragraphs[0].runs)
        )
        self.assertIsNotNone(header._tr.find(f"{qn('w:trPr')}/{qn('w:tblHeader')}"))
        self.assertEqual(self.table.cell(2, 0).text, "short")
        self.assertEqual(self.table.cell(2, 2).text, "")

    def test_alignment(self) -> None:
        alignments = [self.table.cell(1, c).paragraphs[0].alignment for c in range(3)]
        self.assertEqual(
            alignments,
            [
                WD_ALIGN_PARAGRAPH.LEFT,
                WD_ALIGN_PARAGRAPH.RIGHT,
                WD_ALIGN_PARAGRAPH.CENTER,
            ],
        )

    def test_google_docs_grid(self) -> None:
        properties = self.table._tbl.tblPr
        borders = properties.find(qn("w:tblBorders"))
        self.assertEqual(
            {(side.get(qn("w:sz")), side.get(qn("w:color"))) for side in borders},
            {("8", "000000")},
        )
        self.assertEqual(properties.find(qn("w:tblLayout")).get(qn("w:type")), "fixed")
        width = google_docs.content_size(PageSize.A4)[0].twips
        self.assertEqual(int(properties.find(qn("w:tblW")).get(qn("w:w"))), width)

    def test_blank_paragraphs_keep_adjacent_tables_apart(self) -> None:
        document = _convert("| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n")
        body = [
            child.tag for child in document.element.body if child.tag != qn("w:sectPr")
        ]
        self.assertEqual(body, [qn("w:tbl"), qn("w:p"), qn("w:tbl")])


class ImageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def test_local_image_is_embedded_at_native_size(self) -> None:
        (self.dir / "small.png").write_bytes(_png(72, 36))
        document = _convert("![alt](small.png)", base_dir=self.dir)
        (shape,) = document.inline_shapes
        self.assertEqual((shape.width, shape.height), (Inches(1), Inches(0.5)))

    def test_wide_image_is_scaled_to_the_text_width(self) -> None:
        (self.dir / "wide.png").write_bytes(_png(2000, 100))
        document = _convert("![wide](wide.png)", base_dir=self.dir)
        (shape,) = document.inline_shapes
        width = google_docs.content_size(PageSize.A4)[0]
        self.assertAlmostEqual(shape.width, width, delta=2)
        self.assertAlmostEqual(shape.height / shape.width, 100 / 2000, places=3)

    def test_remote_image_goes_through_fetch(self) -> None:
        fetched: list[str] = []

        def fetch(url: str) -> bytes:
            fetched.append(url)
            return _png(10, 10)

        document = _convert("![r](https://example.com/r.png)", fetch=fetch)
        self.assertEqual(fetched, ["https://example.com/r.png"])
        self.assertEqual(len(document.inline_shapes), 1)

    def test_unfetchable_image_becomes_a_link(self) -> None:
        def fetch(_url: str) -> bytes:
            raise OSError("offline")

        with self.assertLogs(converter.logger, "WARNING") as logs:
            document = _convert("![a cat](https://example.com/cat.png)", fetch=fetch)
        self.assertEqual(len(document.inline_shapes), 0)
        self.assertEqual(document.paragraphs[0].text, "[image: a cat]")
        self.assertEqual(_hyperlink_targets(document), ["https://example.com/cat.png"])
        self.assertIn("cat.png", logs.output[0])

    def test_unsupported_format_becomes_a_link(self) -> None:
        with self.assertLogs(converter.logger, "WARNING") as logs:
            document = _convert(
                "![svg](https://example.com/x.svg)",
                fetch=lambda _url: b"<svg xmlns='x'/>",
            )
        self.assertEqual(document.paragraphs[0].text, "[image: svg]")
        self.assertIn("not a PNG, JPEG", logs.output[0])

    def test_missing_local_image_is_plain_text(self) -> None:
        with self.assertLogs(converter.logger, "WARNING"):
            document = _convert("![gone](nowhere.png)", base_dir=self.dir)
        self.assertEqual(document.paragraphs[0].text, "[image: gone]")
        self.assertEqual(_hyperlink_targets(document), [])


_FLOWCHART = "flowchart TD\n  A --> B"
_MERMAID = f"```mermaid\n{_FLOWCHART}\n```\n"


class DiagramTest(unittest.TestCase):
    def test_mermaid_fence_becomes_a_centred_picture_with_its_source_as_alt(
        self,
    ) -> None:
        seen: list[str] = []

        def render(source: str) -> bytes:
            seen.append(source)
            return diagrams.stamp_dpi(_png(400, 200), 192)

        document = _convert(_MERMAID, render_diagram=render)
        self.assertEqual(seen, [_FLOWCHART])
        (paragraph,) = document.paragraphs
        self.assertEqual(paragraph.alignment, WD_ALIGN_PARAGRAPH.CENTER)
        (shape,) = document.inline_shapes
        # 400px at 2x is 200 CSS px, at 96dpi.
        self.assertEqual(shape.width, Emu(200 * 9525))
        self.assertEqual(shape._inline.docPr.get("descr"), _FLOWCHART)

    def test_wide_diagram_shrinks_to_the_text_width(self) -> None:
        document = _convert(
            _MERMAID,
            render_diagram=lambda _source: diagrams.stamp_dpi(_png(4000, 200), 192),
        )
        (shape,) = document.inline_shapes
        width = google_docs.content_size(PageSize.A4)[0]
        self.assertAlmostEqual(shape.width, width, delta=2)

    def test_other_languages_stay_code(self) -> None:
        def render(source: str) -> bytes:
            raise AssertionError(f"rendered {source!r}")

        document = _convert("```python\nprint(1)\n```\n", render_diagram=render)
        self.assertEqual(_style(document.paragraphs[0]), google_docs.CODE_BLOCK_STYLE)

    def test_a_failed_render_keeps_the_code_and_says_why(self) -> None:
        def render(_source: str) -> bytes:
            raise DiagramError("Parse error on line 2")

        with self.assertLogs(converter.logger, "WARNING") as logs:
            document = _convert(_MERMAID, render_diagram=render)
        (paragraph,) = document.paragraphs
        self.assertEqual(_style(paragraph), google_docs.CODE_BLOCK_STYLE)
        self.assertEqual(paragraph.text, _FLOWCHART)
        self.assertIn("flowchart TD", logs.output[0])
        self.assertIn("Parse error on line 2", logs.output[0])

    def test_output_that_is_not_an_image_keeps_the_code(self) -> None:
        with self.assertLogs(converter.logger, "WARNING"):
            document = _convert(_MERMAID, render_diagram=lambda _source: b"<svg/>")
        self.assertEqual(len(document.inline_shapes), 0)
        self.assertEqual(_style(document.paragraphs[0]), google_docs.CODE_BLOCK_STYLE)

    def test_without_a_renderer_mermaid_is_quietly_code(self) -> None:
        with self.assertNoLogs(converter.logger, "WARNING"):
            document = _convert(_MERMAID)
        self.assertEqual(_style(document.paragraphs[0]), google_docs.CODE_BLOCK_STYLE)


class EndToEndTest(unittest.TestCase):
    def test_sample_round_trips_through_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pixel.png").write_bytes(_png(1, 1))
            source = root / "gfm.md"
            source.write_text(
                (TESTDATA / "gfm.md").read_text(encoding="utf-8"), encoding="utf-8"
            )
            target = converter.convert_file(
                source, root / "out" / "gfm.docx", fetch=_no_network
            )
            document = docx.Document(str(target))

        texts = _texts(document)
        self.assertEqual(texts[0], "Every construct")
        self.assertNotIn("Front matter is not rendered", "\n".join(texts))
        self.assertIn("Line\nbreak and .", texts)
        self.assertEqual(texts[-1], "The footnote.")
        self.assertEqual(len(document.tables), 1)
        self.assertEqual(len(document.inline_shapes), 1)
        self.assertEqual(document.core_properties.title, "Every construct")


if __name__ == "__main__":
    unittest.main()
