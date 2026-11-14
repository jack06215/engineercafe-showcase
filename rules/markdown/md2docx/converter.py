"""GitHub-flavoured Markdown to a Word document styled like a new Google Doc.

markdown-it-py parses -- CommonMark, which GFM is built on, plus GFM's tables,
strikethrough and autolinks, with task lists and footnotes from mdit-py-plugins
-- and the syntax tree is walked straight into python-docx. `google_docs` owns
the styles and `numbering` the lists.

Google Docs' Normal text has no space above or below, so blocks are kept apart
the way people do it by hand in Docs: an empty paragraph between them.

```mermaid blocks become pictures when a `DiagramRenderer` is passed in (see
`diagrams`), and stay code blocks when it fails or there is none.
"""

import contextlib
import html
import io
import logging
import re
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.exceptions import UnrecognizedImageError
from docx.image.image import Image
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.shape import InlineShape
from docx.shared import Emu, Length, Twips
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from rules.markdown.md2docx import google_docs, numbering
from rules.markdown.md2docx.diagrams import DiagramError, DiagramRenderer
from rules.markdown.md2docx.google_docs import PageSize
from rules.markdown.md2docx.numbering import ListKind
from rules.markdown.md2docx.ooxml import (
    PPR_ORDER,
    TBLPR_ORDER,
    TRPR_ORDER,
    element,
    insert_ordered,
)

Fetch = Callable[[str], bytes]
"""Returns the bytes behind an http(s) or data: URL, raising on failure."""

logger = logging.getLogger(__name__)

# Front matter is not GFM, but a third of these notes open with it, and parsed
# as markdown its closing `---` turns the YAML into a setext heading.
_MARKDOWN = (
    MarkdownIt("gfm-like")
    .use(front_matter_plugin)
    .use(tasklists_plugin)
    .use(footnote_plugin)
)

_FETCH_TIMEOUT_S = 10
# Some image hosts turn away urllib's default agent, and the WordPress CDN
# (i0.wp.com) sends WebP, which Word can't embed, to anyone who accepts it.
_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; md2docx)",
    "Accept": "image/png,image/jpeg,image/gif,*/*;q=0.5",
}
_REMOTE_SCHEMES = ("http", "https", "data")

_QUOTE_INDENT = 360  # twips per blockquote level
_CELL_PADDING = 100  # twips, Google Docs' 5pt
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"<[^>]*>")
_ALIGN = re.compile(r"text-align:\s*(left|center|right)")
_ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
}


def fetch_url(url: str) -> bytes:
    """Download `url`; the default `Fetch`."""
    request = urllib.request.Request(url, headers=_FETCH_HEADERS)
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_S) as response:
        body: bytes = response.read()
    return body


def convert(
    markdown: str,
    *,
    base_dir: Path,
    page_size: PageSize = PageSize.A4,
    fetch: Fetch = fetch_url,
    render_diagram: DiagramRenderer | None = None,
    fallback_title: str = "",
) -> DocxDocument:
    """Render `markdown` as a Word document.

    Relative image paths resolve against `base_dir`. ```mermaid blocks go
    through `render_diagram`, when there is one. The document title is the
    first heading, or `fallback_title` when there is none.
    """
    document = docx.Document()
    google_docs.apply(document, page_size)
    renderer = _Renderer(
        document,
        base_dir=base_dir,
        page_size=page_size,
        fetch=fetch,
        render_diagram=render_diagram,
    )
    renderer.render(SyntaxTreeNode(_MARKDOWN.parse(markdown)))
    _set_metadata(document, renderer.title or fallback_title)
    return document


def convert_file(
    src: Path,
    dst: Path,
    *,
    page_size: PageSize = PageSize.A4,
    fetch: Fetch = fetch_url,
    render_diagram: DiagramRenderer | None = None,
) -> Path:
    """Convert the markdown file `src` and write it to `dst`."""
    document = convert(
        # utf-8-sig drops the BOM some Windows editors write.
        src.read_text(encoding="utf-8-sig"),
        base_dir=src.parent,
        page_size=page_size,
        fetch=fetch,
        render_diagram=render_diagram,
        fallback_title=src.stem,
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(dst))
    return dst


@dataclass(frozen=True)
class _Where:
    """The container blocks are going into."""

    indent: int = 0  # twips
    quote_depth: int = 0
    list_level: int = -1


@dataclass(frozen=True)
class _Format:
    """Character formatting in effect for a run."""

    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False
    superscript: bool = False
    grey: bool = False


class _Renderer:
    def __init__(
        self,
        document: DocxDocument,
        *,
        base_dir: Path,
        page_size: PageSize,
        fetch: Fetch,
        render_diagram: DiagramRenderer | None,
    ) -> None:
        self._document = document
        self._base_dir = base_dir
        self._fetch = fetch
        self._render_diagram = render_diagram
        self._lists = numbering.Numbering(document)
        self._content_width, self._content_height = google_docs.content_size(page_size)
        self._image_width: Length = self._content_width
        # A list item's (num id, level), waiting for the item's first paragraph.
        self._pending_item: tuple[int, int] | None = None
        # The w:hyperlink new runs go into, while inside a link.
        self._link: BaseOxmlElement | None = None
        # The last character written, for the CJK line-break rule.
        self._last_char = ""
        self.title: str | None = None

    def render(self, root: SyntaxTreeNode) -> None:
        body = [
            n for n in root.children if n.type not in ("front_matter", "footnote_block")
        ]
        self._blocks(body, _Where(), separate=True)
        for block in root.children:
            if block.type == "footnote_block":
                self._footnotes(block)

    # -- blocks --------------------------------------------------------------

    def _blocks(
        self, nodes: Sequence[SyntaxTreeNode], where: _Where, *, separate: bool
    ) -> None:
        previous: SyntaxTreeNode | None = None
        for node in nodes:
            if node.type == "html_block" and not _html_text(node.content):
                continue
            # Headings bring their own space above and below. A rule is drawn
            # at the foot of an empty line, so it takes a blank line only below
            # it, which leaves it centred.
            if (
                separate
                and previous is not None
                and previous.type != "heading"
                and node.type not in ("heading", "hr")
            ):
                self._paragraph(where)
            self._block(node, where)
            previous = node

    def _block(self, node: SyntaxTreeNode, where: _Where) -> None:
        match node.type:
            case "paragraph":
                self._inline(
                    self._paragraph(where), _inlines(node), _base_format(where)
                )
            case "heading":
                paragraph = self._paragraph(where, style=f"Heading {node.tag[1:]}")
                self._inline(paragraph, _inlines(node), _base_format(where))
                if self.title is None:
                    self.title = _plain_text(node)
            case "bullet_list" | "ordered_list":
                self._list(node, where)
            case "blockquote":
                inner = replace(
                    where,
                    indent=where.indent + _QUOTE_INDENT,
                    quote_depth=where.quote_depth + 1,
                )
                self._blocks(node.children, inner, separate=True)
            case "fence" if (
                self._render_diagram is not None and _language(node) == "mermaid"
            ):
                self._diagram(node, where, self._render_diagram)
            case "fence" | "code_block":
                self._code_block(node, where)
            case "hr":
                _rule(self._paragraph(where), "bottom", size=6, space=1)
            case "table":
                self._table(node, where)
            case "html_block":
                self._add_run(
                    self._paragraph(where),
                    _html_text(node.content),
                    _base_format(where),
                )
            case _:
                self._blocks(node.children, where, separate=True)

    def _code_block(self, node: SyntaxTreeNode, where: _Where) -> None:
        paragraph = self._paragraph(where, style=google_docs.CODE_BLOCK_STYLE)
        # python-docx turns "\n" and "\t" into w:br and w:tab.
        paragraph.add_run(node.content.rstrip("\n"))

    def _diagram(
        self, node: SyntaxTreeNode, where: _Where, render: DiagramRenderer
    ) -> None:
        source = node.content.rstrip("\n")
        try:
            blob = render(source)
            image = Image.from_blob(blob)
        except (DiagramError, OSError, UnrecognizedImageError) as error:
            first_line = source.split("\n", 1)[0].strip()
            logger.warning(
                "mermaid diagram kept as code: %s (%s)", first_line, _describe(error)
            )
            self._code_block(node, where)
            return
        paragraph = self._paragraph(where)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        shape = self._add_picture(paragraph, blob, image)
        # The source as the picture's alt text, so the diagram can still be
        # read -- and edited -- from the document.
        shape._inline.docPr.set("descr", source)

    def _paragraph(self, where: _Where, style: str | None = None) -> Paragraph:
        paragraph = self._document.add_paragraph(style=style)
        if self._pending_item is not None:
            num_id, level = self._pending_item
            numbering.apply(paragraph, num_id, level)
            self._pending_item = None
        elif where.indent:
            paragraph.paragraph_format.left_indent = Twips(where.indent)
        if where.quote_depth:
            _rule(paragraph, "left", size=18, space=8)
        self._image_width = Emu(self._content_width - Twips(where.indent))
        self._last_char = ""
        return paragraph

    def _flush_item(self, where: _Where) -> None:
        """Give a pending list item a paragraph when its content isn't one."""
        if self._pending_item is not None:
            self._paragraph(where)

    def _list(self, node: SyntaxTreeNode, where: _Where) -> None:
        self._flush_item(where)
        level = where.list_level + 1
        ordered_id = None
        if node.type == "ordered_list":
            start = int(node.attrs.get("start", 1))
            ordered_id = self._lists.new_list(level=level, start=start)
        inner = replace(where, indent=numbering.text_indent(level), list_level=level)

        for item in node.children:
            done = _task_state(item)
            # GitHub drops the number or bullet of a task item for its checkbox.
            if done is not None:
                num_id = self._lists.shared(
                    ListKind.TASK_DONE if done else ListKind.TASK_OPEN
                )
            elif ordered_id is not None:
                num_id = ordered_id
            else:
                num_id = self._lists.shared(ListKind.BULLET)
            self._pending_item = (num_id, level)
            # No blank lines inside items: lists stay compact, as in Docs.
            self._blocks(item.children, inner, separate=False)
            self._flush_item(inner)

    def _table(self, node: SyntaxTreeNode, where: _Where) -> None:
        self._flush_item(where)
        rows = [row for section in node.children for row in section.children]
        columns = max((len(row.children) for row in rows), default=0)
        if not columns:
            return

        width = self._content_width.twips - where.indent
        column_width = Twips(width // columns)
        table = self._document.add_table(rows=len(rows), cols=columns)
        _table_look(table, width=width, indent=where.indent)
        for column in table.columns:
            column.width = column_width

        for row_index, row in enumerate(rows):
            if row.parent is not None and row.parent.type == "thead":
                # Repeated at the top of every page the table runs onto.
                insert_ordered(
                    table.rows[row_index]._tr.get_or_add_trPr(),
                    element("w:tblHeader"),
                    TRPR_ORDER,
                )
            for column_index, cell_node in enumerate(row.children):
                cell = table.cell(row_index, column_index)
                cell.width = column_width
                paragraph = cell.paragraphs[0]
                alignment = _alignment(cell_node)
                if alignment is not None:
                    paragraph.alignment = alignment
                self._image_width = Emu(column_width - 2 * Twips(_CELL_PADDING))
                self._last_char = ""
                cell_format = replace(_base_format(where), bold=cell_node.type == "th")
                self._inline(paragraph, _inlines(cell_node), cell_format)

    def _footnotes(self, block: SyntaxTreeNode) -> None:
        if not block.children:
            return
        top = _Where()
        _rule(self._paragraph(top), "bottom", size=6, space=1)
        self._paragraph(top)
        # Footnotes are numbered in order of first reference, the same order
        # they're listed in, so an ordered list reproduces the reference marks.
        first = int(block.children[0].meta.get("id", 0)) + 1
        num_id = self._lists.new_list(start=first)
        inner = _Where(indent=numbering.text_indent(0), list_level=0)
        for footnote in block.children:
            self._pending_item = (num_id, 0)
            self._blocks(footnote.children, inner, separate=False)
            self._flush_item(inner)

    # -- inlines -------------------------------------------------------------

    def _inline(
        self, paragraph: Paragraph, nodes: Sequence[SyntaxTreeNode], fmt: _Format
    ) -> None:
        for index, node in enumerate(nodes):
            match node.type:
                case "text":
                    text = node.content
                    # The space after a checkbox or a `<br>` would start the
                    # line; HTML collapses it, so do the same.
                    if index and _starts_line(nodes[index - 1]):
                        text = text.lstrip()
                    self._add_run(paragraph, text, fmt)
                case "softbreak":
                    # Joining CJK lines with a space would put one inside a
                    # word, so -- as browsers do -- a break between two CJK
                    # characters disappears instead.
                    following = _first_char(nodes[index + 1 :])
                    if not (_is_cjk(self._last_char) and _is_cjk(following)):
                        self._add_run(paragraph, " ", fmt)
                case "hardbreak":
                    self._add_run(paragraph, "\n", fmt)
                case "code_inline":
                    self._add_run(paragraph, node.content, replace(fmt, code=True))
                case "em":
                    self._inline(paragraph, node.children, replace(fmt, italic=True))
                case "strong":
                    self._inline(paragraph, node.children, replace(fmt, bold=True))
                case "s":
                    self._inline(paragraph, node.children, replace(fmt, strike=True))
                case "link":
                    with self._linked(paragraph, str(node.attrs.get("href", ""))):
                        self._inline(paragraph, node.children, fmt)
                case "image":
                    self._image(paragraph, node, fmt)
                case "html_inline":
                    if _BREAK.fullmatch(node.content.strip()):
                        self._add_run(paragraph, "\n", fmt)
                case "footnote_ref":
                    number = str(int(node.meta["id"]) + 1)
                    self._add_run(paragraph, number, replace(fmt, superscript=True))
                case _:
                    # Unknown inline markup (and footnote back-references):
                    # keep whatever text it wraps.
                    self._inline(paragraph, node.children, fmt)

    def _add_run(self, paragraph: Paragraph, text: str, fmt: _Format) -> Run | None:
        if not text:
            return None
        run = paragraph.add_run(text)
        font = run.font
        if fmt.bold:
            font.bold = True
        if fmt.italic:
            font.italic = True
        if fmt.strike:
            font.strike = True
        if fmt.superscript:
            font.superscript = True
        if fmt.code:
            run.style = google_docs.CODE_STYLE
        if self._link is not None:
            font.color.rgb = google_docs.LINK_COLOR
            font.underline = True
            self._link.append(run._r)
        elif fmt.grey and not fmt.code:
            font.color.rgb = google_docs.GREY
        self._last_char = text[-1]
        return run

    @contextlib.contextmanager
    def _linked(self, paragraph: Paragraph, href: str) -> Generator[None]:
        """Route the runs added inside the block into a hyperlink to `href`."""
        if not href or self._link is not None:
            yield
            return
        link = element("w:hyperlink")
        if href.startswith("#"):
            link.set(qn("w:anchor"), href[1:])
        else:
            relationship = paragraph.part.relate_to(
                href, RELATIONSHIP_TYPE.HYPERLINK, is_external=True
            )
            link.set(qn("r:id"), relationship)
        # Runs are created on the paragraph by python-docx, which keeps its
        # formatting API usable, and then moved in here.
        paragraph._p.append(link)
        self._link = link
        try:
            yield
        finally:
            self._link = None

    def _image(self, paragraph: Paragraph, node: SyntaxTreeNode, fmt: _Format) -> None:
        src = str(node.attrs.get("src", ""))
        try:
            blob = self._load(src)
            image = Image.from_blob(blob)
        except (OSError, ValueError, HTTPException, UnrecognizedImageError) as error:
            logger.warning("image not embedded: %s (%s)", src, _describe(error))
            alt = _plain_text(node)
            label = f"[image: {alt}]" if alt else "[image]"
            remote = urllib.parse.urlsplit(src).scheme in ("http", "https")
            with self._linked(paragraph, src if remote else ""):
                self._add_run(paragraph, label, fmt)
            return
        self._add_picture(paragraph, blob, image)

    def _add_picture(
        self, paragraph: Paragraph, blob: bytes, image: Image
    ) -> InlineShape:
        """Embed `blob` at its natural size, shrunk to fit the page if needed."""
        width, height = max(image.width, 1), max(image.height, 1)
        scale = min(1.0, self._image_width / width, self._content_height / height)
        run = paragraph.add_run()
        shape = run.add_picture(
            io.BytesIO(blob),
            width=Emu(int(width * scale)),
            height=Emu(int(height * scale)),
        )
        if self._link is not None:
            self._link.append(run._r)
        self._last_char = ""
        return shape

    def _load(self, src: str) -> bytes:
        if not src:
            raise ValueError("no image source")
        if urllib.parse.urlsplit(src).scheme in _REMOTE_SCHEMES:
            return self._fetch(src)
        return (self._base_dir / urllib.parse.unquote(src)).read_bytes()


# -- helpers -----------------------------------------------------------------


def _language(node: SyntaxTreeNode) -> str:
    """A fence's language: the first word of its info string, lower-cased."""
    words = node.info.split(maxsplit=1)
    return words[0].lower() if words else ""


def _describe(error: Exception) -> str:
    # UnrecognizedImageError carries no message of its own.
    if isinstance(error, UnrecognizedImageError):
        return "not a PNG, JPEG, GIF, BMP or TIFF"
    return str(error) or type(error).__name__


def _base_format(where: _Where) -> _Format:
    return _Format(grey=where.quote_depth > 0)


def _inlines(node: SyntaxTreeNode) -> list[SyntaxTreeNode]:
    """The inline content of a block, skipping anything else it holds.

    A footnote's back-reference sits beside the inline node, not inside it.
    """
    return [
        child
        for inline in node.children
        if inline.type == "inline"
        for child in inline.children
    ]


def _plain_text(node: SyntaxTreeNode) -> str:
    return "".join(
        child.content for child in node.walk() if child.type in ("text", "code_inline")
    )


def _task_state(item: SyntaxTreeNode) -> bool | None:
    """Whether a task-list item is ticked; None for an ordinary item."""
    if item.attrs.get("class") != "task-list-item":
        return None
    for node in item.walk():
        if _is_checkbox(node):
            return 'checked="checked"' in node.content
    return None


def _is_checkbox(node: SyntaxTreeNode) -> bool:
    return node.type == "html_inline" and "task-list-item-checkbox" in node.content


def _starts_line(node: SyntaxTreeNode) -> bool:
    """Whether what follows `node` begins a line: after a `<br>` or checkbox."""
    return _is_checkbox(node) or (
        node.type == "html_inline"
        and _BREAK.fullmatch(node.content.strip()) is not None
    )


def _first_char(nodes: Sequence[SyntaxTreeNode]) -> str:
    for node in nodes:
        for child in node.walk():
            if child.type in ("text", "code_inline") and child.content:
                return child.content[0]
            if child.type in ("softbreak", "hardbreak", "image"):
                return ""
    return ""


def _is_cjk(char: str) -> bool:
    """A wide East Asian character -- except Hangul, which spaces its words."""
    if not char or "HANGUL" in unicodedata.name(char, ""):
        return False
    return unicodedata.east_asian_width(char) in ("W", "F", "H")


def _html_text(source: str) -> str:
    """The text of raw HTML: tags and comments dropped, `<br>` kept as a break."""
    text = html.unescape(_TAG.sub("", _BREAK.sub("\n", _COMMENT.sub("", source))))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _alignment(cell: SyntaxTreeNode) -> WD_ALIGN_PARAGRAPH | None:
    found = _ALIGN.search(str(cell.attrs.get("style", "")))
    return _ALIGNMENTS[found.group(1)] if found else None


def _rule(paragraph: Paragraph, side: str, *, size: int, space: int) -> None:
    """A grey border on one side of `paragraph` (sizes in eighths of a point)."""
    border = element(
        f"w:{side}", val="single", sz=size, space=space, color=google_docs.RULE_COLOR
    )
    insert_ordered(
        paragraph._p.get_or_add_pPr(), element("w:pBdr", [border]), PPR_ORDER
    )


def _table_look(table: Table, *, width: int, indent: int) -> None:
    """Google Docs' default table style.

    Full width in equal columns, a 1pt black grid and 5pt padding. `width` and
    `indent` are in twips.
    """
    properties = table._tbl.tblPr
    # Fixed layout, as Google exports it, so renderers keep the equal columns
    # instead of shrinking the table around its content.
    insert_ordered(properties, element("w:tblW", w=width, type="dxa"), TBLPR_ORDER)
    insert_ordered(properties, element("w:tblLayout", type="fixed"), TBLPR_ORDER)
    borders = element(
        "w:tblBorders",
        [
            element(f"w:{side}", val="single", sz=8, space=0, color="000000")
            for side in ("top", "left", "bottom", "right", "insideH", "insideV")
        ],
    )
    insert_ordered(properties, borders, TBLPR_ORDER)
    margins = element(
        "w:tblCellMar",
        [
            element(f"w:{side}", w=_CELL_PADDING, type="dxa")
            for side in ("top", "left", "bottom", "right")
        ],
    )
    insert_ordered(properties, margins, TBLPR_ORDER)
    if indent:
        insert_ordered(
            properties, element("w:tblInd", w=indent, type="dxa"), TBLPR_ORDER
        )


def _set_metadata(document: DocxDocument, title: str) -> None:
    # python-docx's template would otherwise sign every file "python-docx",
    # created 2013.
    properties = document.core_properties
    now = datetime.now(UTC)
    properties.title = title
    properties.author = ""
    properties.last_modified_by = ""
    properties.created = now
    properties.modified = now
    properties.revision = 1
