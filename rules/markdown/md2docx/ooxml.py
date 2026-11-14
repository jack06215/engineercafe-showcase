"""Small helpers for the WordprocessingML python-docx has no API for.

OOXML is order-sensitive: Word refuses a paragraph whose `w:pPr` holds `w:shd`
before `w:pBdr`, even though each element on its own is valid. python-docx only
places the children it models, so anything else is inserted here at the spot
the schema's sequence gives it rather than appended.
"""

from collections.abc import Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement

# Child sequences from ECMA-376 part 1: CT_PPr, CT_TblPr and CT_TrPr.
PPR_ORDER = (
    "w:pStyle",
    "w:keepNext",
    "w:keepLines",
    "w:pageBreakBefore",
    "w:framePr",
    "w:widowControl",
    "w:numPr",
    "w:suppressLineNumbers",
    "w:pBdr",
    "w:shd",
    "w:tabs",
    "w:suppressAutoHyphens",
    "w:kinsoku",
    "w:wordWrap",
    "w:overflowPunct",
    "w:topLinePunct",
    "w:autoSpaceDE",
    "w:autoSpaceDN",
    "w:bidi",
    "w:adjustRightInd",
    "w:snapToGrid",
    "w:spacing",
    "w:ind",
    "w:contextualSpacing",
    "w:mirrorIndents",
    "w:suppressOverlap",
    "w:jc",
    "w:textDirection",
    "w:textAlignment",
    "w:textboxTightWrap",
    "w:outlineLvl",
    "w:divId",
    "w:cnfStyle",
    "w:rPr",
    "w:sectPr",
    "w:pPrChange",
)
TBLPR_ORDER = (
    "w:tblStyle",
    "w:tblpPr",
    "w:tblOverlap",
    "w:bidiVisual",
    "w:tblStyleRowBandSize",
    "w:tblStyleColBandSize",
    "w:tblW",
    "w:jc",
    "w:tblCellSpacing",
    "w:tblInd",
    "w:tblBorders",
    "w:shd",
    "w:tblLayout",
    "w:tblCellMar",
    "w:tblLook",
    "w:tblCaption",
    "w:tblDescription",
    "w:tblPrChange",
)
TRPR_ORDER = (
    "w:cnfStyle",
    "w:divId",
    "w:gridBefore",
    "w:gridAfter",
    "w:wBefore",
    "w:wAfter",
    "w:cantSplit",
    "w:trHeight",
    "w:tblHeader",
    "w:tblCellSpacing",
    "w:jc",
    "w:hidden",
    "w:ins",
    "w:del",
    "w:trPrChange",
)


def element(
    tag: str, children: Sequence[BaseOxmlElement] = (), **attrs: str | int
) -> BaseOxmlElement:
    """Build `<tag w:key="value" ...>children</tag>`.

    Attribute names are given without their `w:` prefix, which every attribute
    this package writes shares.
    """
    node = OxmlElement(
        tag, attrs={qn(f"w:{key}"): str(value) for key, value in attrs.items()}
    )
    for child in children:
        node.append(child)
    return node


def insert_ordered(
    parent: BaseOxmlElement, child: BaseOxmlElement, order: Sequence[str]
) -> BaseOxmlElement:
    """Put `child` into `parent` where `order` says it belongs.

    An existing child with the same tag is replaced, so this also works as a
    setter.
    """
    tags = [qn(tag) for tag in order]
    rank = tags.index(child.tag)
    existing = parent.find(child.tag)
    if existing is not None:
        parent.remove(existing)
    for sibling in parent:
        if sibling.tag in tags and tags.index(sibling.tag) > rank:
            sibling.addprevious(child)
            return child
    parent.append(child)
    return child
