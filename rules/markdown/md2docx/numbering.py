"""List numbering as Google Docs defines it.

Word keeps list glyphs and indents out of the paragraph, in numbering.xml: an
`abstractNum` describes nine levels, and a `num` points a list at one.
Renderers disagree about whether `num`s sharing an `abstractNum` share a count
-- Word restarts on a `startOverride`, macOS's Quick Look counts straight on
regardless -- so, as Google Docs' own export does, every ordered list gets an
`abstractNum` of its own that starts where its markdown says. Bullets and
checkboxes don't count, so one definition serves all lists of each.
"""

import enum

from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.text.paragraph import Paragraph

from rules.markdown.md2docx.ooxml import element

_LEVELS = 9
_STEP = 720  # twips: every level indents a further 0.5in
_HANGING = 360  # twips: the glyph hangs 0.25in left of the text
_BULLETS = ("●", "○", "■")
_NUMBER_FORMATS = ("decimal", "lowerLetter", "lowerRoman")


class ListKind(enum.Enum):
    """The kinds of Markdown list that get their own Word numbering."""

    BULLET = "bullet"
    ORDERED = "ordered"
    TASK_OPEN = "task_open"
    TASK_DONE = "task_done"


_TASK_GLYPHS = {ListKind.TASK_OPEN: "☐", ListKind.TASK_DONE: "☑"}


def text_indent(level: int) -> int:
    """Where the text of a list item at `level` starts, in twips.

    Plain twips rather than a python-docx `Length`, which holds EMUs and would
    write the wrong number into a `w:ind` attribute.
    """
    return _STEP * (level + 1)


def apply(paragraph: Paragraph, num_id: int, level: int) -> None:
    """Make `paragraph` an item of list `num_id`, nested `level` deep."""
    properties = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    properties.get_or_add_ilvl().val = level
    properties.get_or_add_numId().val = num_id


class Numbering:
    """The document's list definitions, added on first use."""

    def __init__(self, document: DocxDocument) -> None:
        """Attach to the numbering part of *document*."""
        self._numbering = document.part.numbering_part.element
        self._shared: dict[ListKind, int] = {}

    def new_list(self, *, level: int = 0, start: int = 1) -> int:
        """A numbered list of its own, counting from `start` at `level`."""
        return self._add(ListKind.ORDERED, level=level, start=start)

    def shared(self, kind: ListKind) -> int:
        """The one list every bullet (or checkbox) list of `kind` belongs to."""
        if kind not in self._shared:
            self._shared[kind] = self._add(kind, level=0, start=1)
        return self._shared[kind]

    def _add(self, kind: ListKind, *, level: int, start: int) -> int:
        """Add an `abstractNum` and a `num` pointing at it; return the num id."""
        taken = [
            int(value)
            for value in self._numbering.xpath("w:abstractNum/@w:abstractNumId")
        ]
        abstract_id = max(taken, default=-1) + 1
        definition = element(
            "w:abstractNum",
            [
                element("w:multiLevelType", val="hybridMultilevel"),
                *(
                    _level(each, kind, start if each == level else 1)
                    for each in range(_LEVELS)
                ),
            ],
            abstractNumId=abstract_id,
        )
        # The schema puts every abstractNum ahead of every num, and Word holds
        # a document to it.
        first_num = self._numbering.find(qn("w:num"))
        if first_num is None:
            self._numbering.append(definition)
        else:
            first_num.addprevious(definition)
        return int(self._numbering.add_num(abstract_id).numId)


def _level(level: int, kind: ListKind, start: int) -> BaseOxmlElement:
    if kind is ListKind.ORDERED:
        number_format, text = _NUMBER_FORMATS[level % 3], f"%{level + 1}."
    elif kind is ListKind.BULLET:
        number_format, text = "bullet", _BULLETS[level % 3]
    else:
        number_format, text = "bullet", _TASK_GLYPHS[kind]
    return element(
        "w:lvl",
        [
            element("w:start", val=start),
            element("w:numFmt", val=number_format),
            element("w:lvlText", val=text),
            element("w:lvlJc", val="left"),
            element(
                "w:pPr",
                [element("w:ind", left=text_indent(level), hanging=_HANGING)],
            ),
            element("w:rPr", [element("w:u", val="none")]),
        ],
        ilvl=level,
    )
