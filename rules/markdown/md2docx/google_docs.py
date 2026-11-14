"""The look of a new Google Doc, applied to a python-docx document.

Google Docs has one fixed set of styles -- Normal text, Title, Subtitle and
Heading 1-6 -- and a blank doc downloaded as .docx carries the values below.
python-docx's template ships Word 2013's instead (Calibri theme fonts, 10pt
after every paragraph, bold blue headings, a bordered Title), so those styles
are cleared and rebuilt rather than adjusted: a leftover `w:asciiTheme` quietly
outranks any font name set on top of it.

Google Docs has no code style. Code follows what Docs' own Markdown support
produces instead: Roboto Mono, green for inline code.
"""

import enum
from dataclasses import dataclass

from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
from docx.opc.part import PartFactory, XmlPart
from docx.oxml.ns import qn
from docx.oxml.text.font import CT_RPr
from docx.shared import Emu, Inches, Length, Mm, Pt, RGBColor
from docx.styles.style import ParagraphStyle

from rules.markdown.md2docx.ooxml import PPR_ORDER, element, insert_ordered

# python-docx loads the font table as opaque bytes. As an XmlPart it can be
# edited like the rest of the package; registering a part class is python-docx's
# own extension point -- its __init__ does the same for the parts it models.
PartFactory.part_type_for[CONTENT_TYPE.WML_FONT_TABLE] = XmlPart

FONT = "Arial"
CODE_FONT = "Roboto Mono"
LINK_COLOR = RGBColor.from_string("1155CC")
CODE_COLOR = RGBColor.from_string("188038")
GREY = RGBColor.from_string("666666")
RULE_COLOR = "CCCCCC"
CODE_SHADING = "F3F3F3"

CODE_BLOCK_STYLE = "Code Block"
CODE_STYLE = "Code"

_MARGIN = Inches(1)
_HEADER_DISTANCE = Inches(0.5)
_BODY_HALF_POINTS = 22  # 11pt
_LINE_SPACING = 276  # 1.15 lines, in 240ths of a line
_THEME_FONT_ATTRIBUTES = (
    "w:asciiTheme",
    "w:hAnsiTheme",
    "w:eastAsiaTheme",
    "w:cstheme",
)


class PageSize(enum.StrEnum):
    """Google Docs picks between these by account locale."""

    A4 = "a4"
    LETTER = "letter"


_PAGE_SIZES: dict[PageSize, tuple[Length, Length]] = {
    PageSize.A4: (Mm(210), Mm(297)),
    PageSize.LETTER: (Inches(8.5), Inches(11)),
}


@dataclass(frozen=True)
class _Look:
    size_pt: float
    before_pt: float = 0
    after_pt: float = 0
    color: RGBColor | None = None
    italic: bool = False
    outline_level: int | None = None


_LOOKS = {
    "Title": _Look(26, after_pt=3),
    "Subtitle": _Look(15, after_pt=16, color=GREY),
    "Heading 1": _Look(20, before_pt=20, after_pt=6, outline_level=0),
    "Heading 2": _Look(16, before_pt=18, after_pt=6, outline_level=1),
    "Heading 3": _Look(
        14,
        before_pt=16,
        after_pt=4,
        color=RGBColor.from_string("434343"),
        outline_level=2,
    ),
    "Heading 4": _Look(12, before_pt=14, after_pt=4, color=GREY, outline_level=3),
    "Heading 5": _Look(11, before_pt=12, after_pt=4, color=GREY, outline_level=4),
    "Heading 6": _Look(
        11, before_pt=12, after_pt=4, color=GREY, italic=True, outline_level=5
    ),
}


def apply(document: DocxDocument, page_size: PageSize) -> None:
    """Restyle a fresh python-docx document as a blank Google Doc."""
    _set_defaults(document)
    normal = _paragraph_style(document, "Normal")
    _clear(normal)
    # Also on Normal itself, not only in docDefaults: macOS's own renderer
    # (Quick Look, Pages, TextEdit) ignores docDefaults and falls back to a
    # serif.
    set_fonts(normal.element.get_or_add_rPr(), FONT, east_asian=True)
    normal.font.size = Pt(_BODY_HALF_POINTS / 2)
    for name, look in _LOOKS.items():
        _rebuild(_paragraph_style(document, name), look)
    _add_code_styles(document)
    _declare_code_font(document)

    width, height = _PAGE_SIZES[page_size]
    for section in document.sections:
        section.page_width = width
        section.page_height = height
        section.top_margin = section.bottom_margin = _MARGIN
        section.left_margin = section.right_margin = _MARGIN
        section.header_distance = section.footer_distance = _HEADER_DISTANCE


def content_size(page_size: PageSize) -> tuple[Length, Length]:
    """Width and height of the area inside the margins."""
    width, height = _PAGE_SIZES[page_size]
    return Emu(width - 2 * _MARGIN), Emu(height - 2 * _MARGIN)


def set_fonts(properties: CT_RPr, name: str, *, east_asian: bool) -> None:
    """Point the Latin (and optionally East Asian) font slots at `name`."""
    fonts = properties.get_or_add_rFonts()
    for attribute in _THEME_FONT_ATTRIBUTES:
        if qn(attribute) in fonts.attrib:
            del fonts.attrib[qn(attribute)]
    slots = (
        ("ascii", "hAnsi", "cs", "eastAsia") if east_asian else ("ascii", "hAnsi", "cs")
    )
    for slot in slots:
        fonts.set(qn(f"w:{slot}"), name)


def _paragraph_style(document: DocxDocument, name: str) -> ParagraphStyle:
    style = document.styles[name]
    if not isinstance(style, ParagraphStyle):
        raise TypeError(f"{name!r} is not a paragraph style")
    return style


def _set_defaults(document: DocxDocument) -> None:
    # Queried from the styles root: w:docDefaults has no python-docx element
    # class, so its own `xpath` doesn't know the `w:` prefix.
    styles = document.styles.element

    # Rebuilt rather than patched, keeping only the language tags. Arial fills
    # the East Asian slot too, as Google's export does, so CJK text falls back
    # the same way it does in Docs.
    run_defaults = styles.xpath("w:docDefaults/w:rPrDefault")[0]
    languages = styles.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:lang")
    for found in run_defaults.findall(qn("w:rPr")):
        run_defaults.remove(found)
    run_defaults.append(
        element(
            "w:rPr",
            [
                element("w:rFonts", ascii=FONT, hAnsi=FONT, eastAsia=FONT, cs=FONT),
                element("w:sz", val=_BODY_HALF_POINTS),
                element("w:szCs", val=_BODY_HALF_POINTS),
                *languages,
            ],
        )
    )

    paragraph_defaults = styles.xpath("w:docDefaults/w:pPrDefault")[0]
    for found in paragraph_defaults.findall(qn("w:pPr")):
        paragraph_defaults.remove(found)
    paragraph_defaults.append(
        element(
            "w:pPr",
            [
                element(
                    "w:spacing",
                    before=0,
                    after=0,
                    line=_LINE_SPACING,
                    lineRule="auto",
                )
            ],
        )
    )


def _clear(style: ParagraphStyle) -> None:
    for tag in ("w:pPr", "w:rPr"):
        found = style.element.find(qn(tag))
        if found is not None:
            style.element.remove(found)


def _rebuild(style: ParagraphStyle, look: _Look) -> None:
    _clear(style)
    paragraph = style.paragraph_format
    paragraph.space_before = Pt(look.before_pt)
    paragraph.space_after = Pt(look.after_pt)
    paragraph.keep_with_next = True
    paragraph.keep_together = True
    if look.outline_level is not None:
        insert_ordered(
            style.element.get_or_add_pPr(),
            element("w:outlineLvl", val=look.outline_level),
            PPR_ORDER,
        )

    font = style.font
    font.size = Pt(look.size_pt)
    if look.color is not None:
        font.color.rgb = look.color
    if look.italic:
        font.italic = True


def _add_code_styles(document: DocxDocument) -> None:
    styles = document.styles
    normal = styles["Normal"]

    block = styles.add_style(CODE_BLOCK_STYLE, WD_STYLE_TYPE.PARAGRAPH)
    if not isinstance(block, ParagraphStyle):
        raise TypeError(f"{CODE_BLOCK_STYLE!r} is not a paragraph style")
    block.base_style = normal
    block.next_paragraph_style = normal
    block.paragraph_format.line_spacing = 1.0
    # The East Asian slot is left to the document default: Roboto Mono has no
    # CJK glyphs, and these notes have CJK comments in their code.
    set_fonts(block.element.get_or_add_rPr(), CODE_FONT, east_asian=False)
    block.font.size = Pt(10)
    # Borders in the shading colour pad the text away from the edge of the box.
    properties = block.element.get_or_add_pPr()
    insert_ordered(
        properties,
        element(
            "w:pBdr",
            [
                element(f"w:{side}", val="single", sz=4, space=4, color=CODE_SHADING)
                for side in ("top", "left", "bottom", "right")
            ],
        ),
        PPR_ORDER,
    )
    insert_ordered(
        properties,
        element("w:shd", val="clear", color="auto", fill=CODE_SHADING),
        PPR_ORDER,
    )

    code = styles.add_style(CODE_STYLE, WD_STYLE_TYPE.CHARACTER)
    set_fonts(code.element.get_or_add_rPr(), CODE_FONT, east_asian=False)
    code.font.color.rgb = CODE_COLOR


def _declare_code_font(document: DocxDocument) -> None:
    """Describe Roboto Mono in the font table.

    Word substitutes a missing font by the family and pitch recorded here, so
    this is what makes a machine without Roboto Mono fall back to another
    fixed-pitch font instead of the default serif.
    """
    font_table = document.part.part_related_by(RELATIONSHIP_TYPE.FONT_TABLE)
    if not isinstance(font_table, XmlPart):
        return
    fonts = font_table.element
    if any(
        font.get(qn("w:name")) == CODE_FONT for font in fonts.iterchildren(qn("w:font"))
    ):
        return
    fonts.append(
        element(
            "w:font",
            [
                # PANOSE digit 4 is proportion; 9 means monospaced.
                element("w:panose1", val="02000009000000000000"),
                element("w:charset", val="00"),
                element("w:family", val="modern"),
                element("w:pitch", val="fixed"),
            ],
            name=CODE_FONT,
        )
    )
