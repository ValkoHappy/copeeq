"""Real .docx -> DocModel. Gives ground truth for eval cases without hand labelling.

Word documents made by people are messy: place and date pushed apart with tabs or runs of
spaces, manual and automatic numbering, borderless tables for layout, empty paragraphs for
spacing. The importer maps these habits onto DocModel blocks; it is deterministic and
best-effort, so every rule is small and tested.
"""

import colorsys
import re
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal, cast, overload

import docx
from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_LINE_SPACING
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.oxml.table import CT_Row, CT_Tbl, CT_Tc
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.section import Section, _Footer, _Header
from docx.shared import Length
from docx.styles.style import CharacterStyle, ParagraphStyle
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.parfmt import ParagraphFormat
from docx.text.run import Run as DocxRun
from docx.types import ProvidesStoryPart
from lxml import etree  # type: ignore[import-untyped]

from foto2word.domain.document import (
    Alignment,
    ArrowEnd,
    Block,
    BorderLine,
    CellBorders,
    CellImage,
    CellPadding,
    Document,
    DocumentTypeGuess,
    EmptyLine,
    FontFace,
    Footnote,
    FootnoteParagraph,
    HeadingBlock,
    ImageBlock,
    ImagePlacement,
    InlinePicture,
    ListItemBlock,
    NestedTable,
    Orientation,
    PageGeometry,
    PageNumbers,
    ParagraphBlock,
    ParagraphLayout,
    Run,
    SectionStart,
    ShapeBlock,
    ShapeGeometry,
    SpacerBlock,
    SpacerSize,
    SpacingRule,
    TableBlock,
    TableCell,
    TablePosition,
    TableRow,
    TabStop,
    TextBoxBlock,
    VerticalAlignment,
)

_JC = {
    "left": Alignment.LEFT,
    "start": Alignment.LEFT,
    "center": Alignment.CENTER,
    "right": Alignment.RIGHT,
    "end": Alignment.RIGHT,
    "both": Alignment.JUSTIFY,
    "distribute": Alignment.JUSTIFY,
}
"""w:jc values; newer Word writes start/end, which python-docx cannot read."""


def _jc(element: BaseOxmlElement) -> Alignment | None:
    """Alignment set directly on a paragraph or a style (its w:pPr/w:jc), if any."""
    jc = element.find(f"{qn('w:pPr')}/{qn('w:jc')}")
    return _JC.get(jc.get(qn("w:val")) or "") if jc is not None else None


_MANUAL_MARKER = re.compile(
    r"^[^\S\n]*(?!\d{1,2}\.\d{1,2}\.\d{2,4}\b)"  # a date such as 25.08.2023 is not a marker;
    # blanks may come first, a line break may not: that line is an empty one of its own
    r"((?:\d+\.)+\d*|\d+\)|[а-яa-z]\))\s+(?=\S)"
)
_GAP = re.compile(r"\t+| {4,}")
_HEADING_MAX_CHARS = 140
_ROMAN_LOWER = "абвгдежзиклмнопрстуфхцчшщэюя"


AD_PHRASES = ("правовой портал ppt.ru", "больше форм и образцов документов")
"""Advertising lines of the template site. Company names like «Ppt.ru» in samples are content."""


def _strip_ads(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in AD_PHRASES)


@dataclass(slots=True)
class _Numbering:
    """Turns Word auto-numbering (numPr) into the visible marker, e.g. '1.', 'а)', '•'."""

    formats: dict[tuple[str, int], tuple[str, str]] = field(default_factory=dict)
    indents: dict[tuple[str, int], tuple[float, float]] = field(default_factory=dict)
    """(left, first line) in mm from the level definition; negative first line = hanging."""
    counters: dict[tuple[str, int], int] = field(default_factory=dict)
    looks: dict[tuple[str, int], tuple[str | None, float | None]] = field(default_factory=dict)
    """Typeface and size of the marker from the level definition."""
    starts: dict[tuple[str, int], int] = field(default_factory=dict)
    lists: dict[str, str] = field(default_factory=dict)
    """numId -> abstractNumId: lists made from one definition count on together."""
    restarts: dict[tuple[str, int], int] = field(default_factory=dict)
    """startOverride of a numId: that list starts its level again from this value."""
    legal: set[tuple[str, int]] = field(default_factory=set)
    """Levels with isLgl: every number in their marker is written in digits."""
    started: set[str] = field(default_factory=set)
    gaps: dict[tuple[str, int], str] = field(default_factory=dict)
    pictures: set[tuple[str, int]] = field(default_factory=set)
    """Levels whose bullet is a picture (lvlPicBulletId): Word does not draw the sign."""
    """What follows the marker when the level says (w:suff): a space or nothing."""

    @classmethod
    def from_document(cls, document: DocxDocument) -> "_Numbering":
        numbering = cls()
        try:
            root = document.part.numbering_part.element
        except (KeyError, NotImplementedError):
            return numbering
        abstract = {a.get(qn("w:abstractNumId")): a for a in root.findall(qn("w:abstractNum"))}
        for num in root.findall(qn("w:num")):
            ref = num.find(qn("w:abstractNumId"))
            definition = abstract.get(ref.get(qn("w:val"))) if ref is not None else None
            link = definition.find(qn("w:numStyleLink")) if definition is not None else None
            if link is not None:  # its levels are those of the list defining the style
                linked = (
                    a
                    for a in abstract.values()
                    if (own := a.find(qn("w:styleLink"))) is not None
                    and own.get(qn("w:val")) == link.get(qn("w:val"))
                )
                definition = next(linked, definition)
            if definition is None:
                continue
            num_id = num.get(qn("w:numId"))
            numbering.lists[num_id] = ref.get(qn("w:val"))
            for override in num.findall(qn("w:lvlOverride")):
                start = override.find(qn("w:startOverride"))
                if start is not None:
                    level = _num(override.get(qn("w:ilvl")))
                    numbering.restarts[(num_id, level)] = _num(start.get(qn("w:val")))
            for lvl in definition.findall(qn("w:lvl")):
                fmt, text = lvl.find(qn("w:numFmt")), lvl.find(qn("w:lvlText"))
                key = (num_id, _num(lvl.get(qn("w:ilvl"))))
                start = lvl.find(qn("w:start"))
                numbering.starts[key] = _num(start.get(qn("w:val"))) if start is not None else 1
                if lvl.find(qn("w:isLgl")) is not None:
                    numbering.legal.add(key)
                if lvl.find(qn("w:lvlPicBulletId")) is not None:
                    numbering.pictures.add(key)
                suffix = lvl.find(qn("w:suff"))
                if suffix is not None and suffix.get(qn("w:val")) in _MARKER_GAPS:
                    numbering.gaps[key] = _MARKER_GAPS[suffix.get(qn("w:val"))]
                legacy = lvl.find(qn("w:legacy"))
                if legacy is not None:  # Word 6 numbering: the text follows its own space
                    space = _num(legacy.get(qn("w:legacySpace")) or 0)
                    numbering.gaps[key] = " " if space else ""
                numbering.formats[key] = (
                    fmt.get(qn("w:val")) if fmt is not None else "decimal",
                    text.get(qn("w:val")) if text is not None else "%1.",
                )
                indent = lvl.find(f"{qn('w:pPr')}/{qn('w:ind')}")
                if indent is not None:
                    numbering.indents[key] = _indent_mm(indent)
                fonts = lvl.find(f"{qn('w:rPr')}/{qn('w:rFonts')}")
                size = lvl.find(f"{qn('w:rPr')}/{qn('w:sz')}")
                numbering.looks[key] = (
                    fonts.get(qn("w:ascii")) if fonts is not None else None,
                    _num(size.get(qn("w:val"))) / _HALF_POINTS if size is not None else None,
                )
        return numbering

    def look(self, paragraph: Paragraph) -> tuple[str | None, float | None]:
        """The marker's own typeface and size, if its level sets them."""
        key = self._level(paragraph)
        return self.looks.get(key, (None, None)) if key is not None else (None, None)

    @staticmethod
    def _level(paragraph: Paragraph) -> tuple[str, int] | None:
        num_pr = _num_pr(paragraph)
        if num_pr is None:
            return None
        num_id_el, ilvl_el = num_pr.find(qn("w:numId")), num_pr.find(qn("w:ilvl"))
        num_id = num_id_el.get(qn("w:val")) if num_id_el is not None else "0"
        level = _num(ilvl_el.get(qn("w:val"))) if ilvl_el is not None else 0
        return None if num_id == "0" else (num_id, level)

    def gap(self, paragraph: Paragraph) -> str:
        """What Word puts after the marker: a tab unless the level says otherwise."""
        key = self._level(paragraph)
        return self.gaps.get(key, "\t") if key is not None else "\t"

    def glyph(self, paragraph: Paragraph) -> str | None:
        """A bullet level's sign as written in the level's typeface; None for numbers."""
        key = self._level(paragraph)
        fmt, template = self.formats.get(key, ("decimal", "")) if key else ("decimal", "")
        return template if fmt == "bullet" and key not in self.pictures else None

    def indent(self, paragraph: Paragraph) -> tuple[float, float] | None:
        """Indents of the numbering level, which the paragraph's own w:ind overrides side by
        side: a paragraph that moves only its left edge keeps the level's hanging marker."""
        key = self._level(paragraph)
        level = self.indents.get(key) if key is not None else None
        own = paragraph._p.find(f"{qn('w:pPr')}/{qn('w:ind')}")
        if level is None or own is None:
            return level
        has_left = any(own.get(qn(f"w:{name}")) is not None for name in ("left", "start"))
        has_first = any(own.get(qn(f"w:{name}")) is not None for name in ("firstLine", "hanging"))
        if has_left and has_first:
            return None
        own_left, own_first = _indent_mm(own)
        return (own_left if has_left else level[0], own_first if has_first else level[1])

    def marker(self, paragraph: Paragraph) -> tuple[str, int] | None:
        key = self._level(paragraph)
        if key is None:
            return None
        num_id, level = key
        shared = self.lists.get(num_id, num_id)
        if num_id not in self.started:  # a list told to start again does so at its first item
            self.started.add(num_id)
            for (owner, at), value in self.restarts.items():
                if owner == num_id:
                    self.counters[(shared, at)] = value - 1
        for deeper in [k for k in self.counters if k[0] == shared and k[1] > level]:
            del self.counters[deeper]  # deeper levels restart under a new parent item
        count = self.counters.get((shared, level), self.starts.get(key, 1) - 1) + 1
        self.counters[(shared, level)] = count
        fmt, template = self.formats.get(key, ("decimal", "%1."))
        if fmt == "bullet":
            return _readable(template) or "•", level

        def number(match: re.Match[str]) -> str:  # '%2' is the count of the second level
            at = int(match.group(1)) - 1
            value = self.counters.get((shared, at), self.starts.get((num_id, at), 1))
            own = self.formats.get((num_id, at), ("decimal", ""))[0]
            return _format_number(value, "decimal" if key in self.legal else own)

        return re.sub(r"%([1-9])", number, template), level


_MARKER_GAPS = {"tab": "\t", "space": " ", "nothing": ""}


def _num(value: str | int | None) -> int:
    """A whole number as Word writes it; some writers put '359.99999999999994' or '0.0'."""
    return round(float(value or 0))


def _indent_mm(indent: BaseOxmlElement) -> tuple[float, float]:
    def twips(*names: str) -> int:
        values = (indent.get(qn(f"w:{name}")) for name in names)
        return _num(next((v for v in values if v is not None), "0"))

    left = twips("left", "start")
    first_line = twips("firstLine") - twips("hanging")
    return round(left / _TWIPS_PER_MM, 2), round(first_line / _TWIPS_PER_MM, 2)


def _num_pr(paragraph: Paragraph) -> BaseOxmlElement | None:
    """numPr of the paragraph itself, or inherited from its style chain ('List Number')."""
    own = paragraph._p.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
    if own is not None:
        return cast(BaseOxmlElement, own)
    style = _paragraph_style(paragraph)
    while style is not None:
        inherited = style.element.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
        if inherited is not None:
            return cast(BaseOxmlElement, inherited)
        style = style.base_style
    return None


def _format_number(n: int, fmt: str) -> str:
    if fmt in ("lowerLetter", "russianLower"):
        letters = _ROMAN_LOWER if fmt == "russianLower" else "abcdefghijklmnopqrstuvwxyz"
        return letters[(n - 1) % len(letters)]
    if fmt in ("upperLetter", "russianUpper"):
        return _format_number(n, fmt.replace("upper", "lower").replace("Upper", "Lower")).upper()
    if fmt == "lowerRoman":
        return _roman(n).lower()
    if fmt == "upperRoman":
        return _roman(n)
    return str(n)


def _roman(n: int) -> str:
    table = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    out = ""
    for value, letters in table:
        while n >= value:
            out, n = out + letters, n - value
    return out


_DEFAULT_SIZE_PT = 11.0
_UNSET_SIZE_PT = 10.0
"""What Word shows when no level sets a size at all (OOXML: 20 half-points); files made by
Word 2007+ set 11 pt in their defaults, older ones often set nothing."""
_FULL_WIDTH_PCT = 100
_TOGGLES = frozenset(("bold", "italic", "all_caps", "small_caps", "strike", "double_strike"))
_HALF_POINTS = 2
_TWIPS_PER_PT = 20
_AUTO_LINE = 240
"""Word stores 'auto' line spacing in 240ths of a line."""
_LINE_HEIGHT_FACTOR = 1.15
"""Approximate height of a single line relative to the font size, for exact line spacing."""
_LINE_FACTORS = {
    "times new roman": 1.15,
    "arial": 1.15,
    "calibri": 1.22,
    "cambria": 1.172,
    "segoe ui": 1.33,
    "verdana": 1.215,
    "tahoma": 1.207,
    "georgia": 1.136,
    "courier new": 1.133,
}
"""Word's single line (ascent + descent + gap of the typeface) in font sizes."""


def _line_factor(font: str | None) -> float:
    return _LINE_FACTORS.get((font or "").lower(), _LINE_HEIGHT_FACTOR)


class _Formatting:
    """Resolves the formatting a paragraph or run actually shows.

    Word's order: the run or paragraph itself, its style chain, the style of the table it sits
    in, the default paragraph style ('Normal'), the document defaults.
    """

    def __init__(self, document: DocxDocument) -> None:
        self._document = document
        self._theme_faces: dict[str, str | None] = {}
        defaults = document.styles.element.find(qn("w:docDefaults"))
        self._size = _UNSET_SIZE_PT
        self._after_pt = 0.0
        self._line = 1.0
        self._font: str | None = None
        self._table_style: ParagraphStyle | None = None
        self._chains: dict[tuple[str | None, str | None], list[ParagraphStyle]] = {}
        own = defaults.find(f"{qn('w:pPrDefault')}/{qn('w:pPr')}") if defaults is not None else None
        self._default_format: ParagraphFormat | None = None
        if own is not None:  # read as a paragraph of its own: the last step of every chain
            holder = OxmlElement("w:p")
            holder.append(deepcopy(own))
            self._default_format = ParagraphFormat(holder)
        compat = document.settings.element.find(qn("w:compat"))
        override = (
            compat.find(
                f"{qn('w:compatSetting')}"
                f"[@{qn('w:name')}='overrideTableStyleFontSizeAndJustification']"
            )
            if compat is not None
            else None
        )
        # without it Word lets a table style's font size, down to the document defaults, win
        # over 'Normal' when Normal is 11 or 12 pt (ed34515b: 11 pt cells, Normal 12 pt; at
        # 10 or 14 pt Normal wins: measured on the corpus, as users report it)
        normal = document.styles.default(WD_STYLE_TYPE.PARAGRAPH)
        normal_size = normal.font.size if normal is not None else None
        self._table_beats_normal = (
            (override is None or override.get(qn("w:val")) not in ("1", "true"))
            and normal_size is not None
            and normal_size.pt in (11, 12)
        )
        self._table_styled = False
        self.spacing_rule = (
            SpacingRule.SUM
            if compat is not None
            and compat.find(qn("w:doNotUseHTMLParagraphAutoSpacing")) is not None
            else SpacingRule.LARGER
        )
        if defaults is None or defaults.find(qn("w:pPrDefault")) is None:
            # none set: Word's own (measured: 8 pt after, 1.08 lines, whatever the version)
            self._after_pt, self._line = _WORD_AFTER_PT, _WORD_LINE
        if defaults is None:
            return
        fonts = defaults.find(f"{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:rFonts')}")
        if fonts is not None:
            self._font = fonts.get(qn("w:ascii")) or _theme_font(document, fonts)
        size = defaults.find(f"{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:sz')}")
        if size is not None:
            self._size = _num(size.get(qn("w:val"))) / _HALF_POINTS
        spacing = defaults.find(f"{qn('w:pPrDefault')}/{qn('w:pPr')}/{qn('w:spacing')}")
        if spacing is None:
            return
        if spacing.get(qn("w:after")) is not None:
            self._after_pt = _num(spacing.get(qn("w:after"))) / _TWIPS_PER_PT
        rule = spacing.get(qn("w:lineRule"))
        if spacing.get(qn("w:line")) is not None and rule in (None, "auto"):
            self._line = _num(spacing.get(qn("w:line"))) / _AUTO_LINE

    def use_words_defaults(self) -> None:
        self._after_pt, self._line = _WORD_AFTER_PT, _WORD_LINE

    @contextmanager
    def inside(self, table: Table) -> Iterator[None]:
        """Paragraphs read within this block also inherit the table style."""
        outer, self._table_style = self._table_style, table.style
        outer_styled = self._table_styled
        self._table_styled = table._tbl.find(f"{qn('w:tblPr')}/{qn('w:tblStyle')}") is not None
        try:
            yield
        finally:
            self._table_style = outer
            self._table_styled = outer_styled

    def _styles(self, paragraph: Paragraph) -> list[ParagraphStyle]:
        """The paragraph's style chain, 'Normal', then its table's (measured: what 'Normal' sets
        itself wins over the table style, which wins over the document defaults) — cached:
        python-docx looks a style up by scanning all styles, and a big form has thousands of cell
        paragraphs."""
        p_style = paragraph._p.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
        key = (
            p_style.get(qn("w:val")) if p_style is not None else None,
            self._table_style.style_id if self._table_style is not None else None,
        )
        chain = self._chains.get(key)
        if chain is None:
            own = list(_chain(_paragraph_style(paragraph)))
            table = list(_chain(self._table_style))
            default = [st for st in own if st.element.get(qn("w:default")) in ("1", "true")]
            chain = [st for st in own if st not in default] + default + table
            self._chains[key] = chain
        return chain

    def run_font(self, run: DocxRun, paragraph: Paragraph) -> str | None:
        """The run's own typeface, its character style's, else its paragraph style's; at each
        step a theme font wins over a named one, as in Word. Cyrillic is set in the 'hAnsi'
        face, plain Latin in the 'ascii' one: the text decides which of the two counts."""
        styles: list[CharacterStyle | ParagraphStyle] = [
            *_chain(_run_style(run)),
            *self._styles(paragraph),
        ]
        side = "hAnsi" if any(ord(c) > _ASCII_END for c in run.text) else "ascii"
        for element in (run._r, *(style.element for style in styles)):
            fonts = element.find(f"{qn('w:rPr')}/{qn('w:rFonts')}")
            if fonts is None:
                continue
            theme = fonts.get(qn(f"w:{side}Theme"))
            if theme is not None:
                if theme not in self._theme_faces:
                    self._theme_faces[theme] = _theme_font(self._document, theme)
                return self._theme_faces[theme] or self._font
            if fonts.get(qn(f"w:{side}")):
                return str(fonts.get(qn(f"w:{side}")))
        return self._font

    def flag(self, run: DocxRun, paragraph: Paragraph, name: str) -> bool:
        """Bold, italic, underline, ...: the run's own, else its character style's and its
        paragraph's. Bold, italic, capitals and strike-through toggle in Word: set in both the
        character style and the paragraph style, they cancel out (277a1330's normal text)."""
        value = getattr(run.font, name)
        if value is not None:
            return bool(value)
        char = next(
            (v for s in _chain(_run_style(run)) if (v := getattr(s.font, name)) is not None), None
        )
        para = next(
            (v for s in self._styles(paragraph) if (v := getattr(s.font, name)) is not None), None
        )
        if name in _TOGGLES:
            return bool(char) != bool(para)
        return bool(char if char is not None else para)

    @staticmethod
    def same_style_spacing(first: Paragraph, second: Paragraph) -> bool:
        return _style_id(first) == _style_id(second)

    def contextual(self, paragraph: Paragraph) -> bool:
        """'Don't add space between paragraphs of the same style', own or from the style."""
        for element in (paragraph._p, *(style.element for style in self._styles(paragraph))):
            found = element.find(f"{qn('w:pPr')}/{qn('w:contextualSpacing')}")
            if found is not None:
                return found.get(qn("w:val")) not in ("0", "false", "off")
        return False

    def page_break_before(self, paragraph: Paragraph) -> bool:
        return bool(self._resolved(paragraph, "page_break_before"))

    def letter_spacing(self, run: DocxRun, paragraph: Paragraph) -> float | None:
        """Character spacing: the run's own, its character style's, else the paragraph's."""
        styles: list[CharacterStyle] = [*_chain(_run_style(run)), *self._styles(paragraph)]
        for element in (run._r, *(style.element for style in styles)):
            spacing = element.find(f"{qn('w:rPr')}/{qn('w:spacing')}")
            if spacing is not None and spacing.get(qn("w:val")) is not None:
                value = _num(spacing.get(qn("w:val"))) / _TWIPS_PER_PT
                return value or None
        return None

    def kerning(self, run: DocxRun, paragraph: Paragraph) -> float | None:
        """Kerning from this size up: the run's own, its character style's, its paragraph's,
        else the document's default."""
        value = self._inherited(run, paragraph, "w:kern")
        return _num(value) / _HALF_POINTS or None if value is not None else None

    def scale(self, run: DocxRun, paragraph: Paragraph) -> int | None:
        """Width of the letters in per cent (w:w), found as kerning is; None for 100."""
        value = self._inherited(run, paragraph, "w:w")
        return None if value is None or _num(value) in (0, _FULL_WIDTH_PCT) else _num(value)

    def _inherited(self, run: DocxRun, paragraph: Paragraph, tag: str) -> str | None:
        """The w:val of a run property: the run's own, its character style's, its paragraph's,
        else the document's default."""
        styles: list[CharacterStyle] = [*_chain(_run_style(run)), *self._styles(paragraph)]
        defaults = self._document.styles.element.find(f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}")
        sources = [run._r, *(style.element for style in styles)]
        if defaults is not None:
            sources.append(defaults)
        for element in sources:
            found = element.find(f"{qn('w:rPr')}/{qn(tag)}")
            if found is not None and found.get(qn("w:val")) is not None:
                return str(found.get(qn("w:val")))
        return None

    def run_size(self, run: DocxRun, paragraph: Paragraph) -> float:
        """The run's own size, its character style's, else its paragraph's."""
        sources: list[DocxRun | CharacterStyle] = [run, *_chain(_run_style(run))]
        sizes = (st.font.size for st in sources)
        own = next((size for size in sizes if size is not None), None)
        return float(own.pt) if own is not None else self._style_size(paragraph)

    def mark_font(self, paragraph: Paragraph) -> str | None:
        """Typeface of the paragraph mark: what an empty paragraph is set in."""
        fonts = paragraph._p.find(f"{qn('w:pPr')}/{qn('w:rPr')}/{qn('w:rFonts')}")
        if fonts is not None and fonts.get(qn("w:ascii")):
            return str(fonts.get(qn("w:ascii")))
        names = (st.font.name for st in self._styles(paragraph))
        return next((str(n) for n in names if n), self._font)

    def named_mark_font(self, paragraph: Paragraph) -> str | None:
        """The face of the paragraph mark, written out: its own, its paragraph style's, else the
        document's default; a theme font as the original's theme names it (measured: an empty
        line of a theme mark is as tall as one of that face). Our file's theme is another one,
        so the face is always named."""
        found = [
            paragraph._p.find(f"{qn('w:pPr')}/{qn('w:rPr')}/{qn('w:rFonts')}"),
            *(st.element.find(f"{qn('w:rPr')}/{qn('w:rFonts')}") for st in self._styles(paragraph)),
        ]
        for fonts in found:
            if fonts is None:
                continue
            theme = fonts.get(qn("w:asciiTheme"))
            if theme is not None:
                if theme not in self._theme_faces:
                    self._theme_faces[theme] = _theme_font(self._document, theme)
                return self._theme_faces[theme] or self._font
            if fonts.get(qn("w:ascii")):
                return str(fonts.get(qn("w:ascii")))
        return self._font

    def mark_size(self, paragraph: Paragraph) -> float:
        """Font size of the paragraph mark: what an empty paragraph is as tall as."""
        size = paragraph._p.find(f"{qn('w:pPr')}/{qn('w:rPr')}/{qn('w:sz')}")
        if size is not None and size.get(qn("w:val")):
            return _num(size.get(qn("w:val"))) / _HALF_POINTS
        return self._style_size(paragraph)

    def _style_size(self, paragraph: Paragraph) -> float:
        sizes = (st.font.size for st in self._size_styles(paragraph))
        return next((float(v.pt) for v in sizes if v is not None), self._size)

    def _size_styles(self, paragraph: Paragraph) -> list[ParagraphStyle]:
        """The styles a font size comes from: in a table of a style of its own that sets no
        size, without 'Normal' when the document defaults set one (see _table_beats_normal).
        A size of the table style itself still loses to Normal's (b6f33956, f0af2606)."""
        chain = self._styles(paragraph)
        if (
            self._table_style is None
            or not self._table_styled
            or not self._table_beats_normal
            or self._size == _UNSET_SIZE_PT
            or any(st.font.size is not None for st in _chain(self._table_style))
        ):
            return chain
        return [
            st
            for st in chain
            if not (
                st.type == WD_STYLE_TYPE.PARAGRAPH
                and st.element.get(qn("w:default")) in ("1", "true")
            )
        ]

    def gap_pt(
        self, above: Paragraph | None, empty: list[Paragraph], below: Paragraph | None
    ) -> float:
        """Height of one spacing-free paragraph that reproduces a run of empty paragraphs.

        By default Word does not add up the spacing of neighbouring paragraphs, it takes the
        larger of 'after' and the next 'before' (see SpacingRule). The neighbours keep their own
        spacing when re-rendered, so it is subtracted here.
        """

        def combined(after: float, before: float) -> float:
            return after + before if self.spacing_rule is SpacingRule.SUM else max(after, before)

        def between(
            first: Paragraph | None, after: float, second: Paragraph | None, before: float
        ) -> float:
            if first is not None and second is not None and self.same_style_spacing(first, second):
                after = 0.0 if self.contextual(first) else after
                before = 0.0 if self.contextual(second) else before
            return combined(after, before)

        layouts = [self.layout(p, self.mark_size(p)) for p in empty]
        after_above = self._spacing(above, "after")
        before_below = self._spacing(below, "before")
        total = between(above, after_above, empty[0], layouts[0].space_before_pt or 0.0)
        for index, (paragraph, layout) in enumerate(zip(empty, layouts, strict=True)):
            line = self.mark_size(paragraph) * _line_factor(self.mark_font(paragraph))
            lines = 1 + _line_breaks(paragraph)  # an empty line with a break in it is two lines
            total += line * (layout.line_spacing or 1.0) * lines
            following = empty[index + 1] if index + 1 < len(empty) else below
            before = (
                layouts[index + 1].space_before_pt or 0.0
                if index + 1 < len(empty)
                else before_below
            )
            total += between(paragraph, layout.space_after_pt or 0.0, following, before)
        # the paragraph above loses its 'after' to the rule (see _Flow), the one below keeps all
        dropped = (
            above is not None
            and self.contextual(above)
            and self.same_style_spacing(above, empty[0])
        )
        return total - (0.0 if dropped else after_above) - before_below

    def _spacing(self, paragraph: Paragraph | None, side: str) -> float:
        if paragraph is None:
            return 0.0
        layout = self.layout(paragraph, _DEFAULT_SIZE_PT)
        value = layout.space_after_pt if side == "after" else layout.space_before_pt
        return value or 0.0

    def alignment(self, paragraph: Paragraph) -> Alignment:
        """Own alignment, else the inherited one (styles, then the document's defaults); Word's
        default is left."""
        elements = [paragraph._p, *(style.element for style in self._styles(paragraph))]
        if self._default_format is not None:
            elements.append(self._default_format._element)
        found = (_jc(element) for element in elements)
        return next((value for value in found if value is not None), Alignment.LEFT)

    def _resolved(self, paragraph: Paragraph, name: str) -> object:
        value = getattr(paragraph.paragraph_format, name)
        for style in self._styles(paragraph):
            if value is not None:
                break
            value = getattr(style.paragraph_format, name)
        if value is None and self._default_format is not None:
            value = getattr(self._default_format, name)
        return value

    def run_color(self, run: DocxRun) -> str | None:
        """The run's own colour, else its character style's (a hyperlink's blue), else its
        paragraph style's (a heading's blue); a theme colour as the theme paints it."""
        palette = _palette(self._document)
        paragraph = run._parent
        paragraph_styles = (
            _chain(_paragraph_style(paragraph)) if isinstance(paragraph, Paragraph) else ()
        )
        styles = (*_chain(_run_style(run)), *paragraph_styles)
        for element in (run._r, *(style.element for style in styles)):
            colour = element.find(f"{qn('w:rPr')}/{qn('w:color')}")
            if colour is not None:
                value = _word_colour(colour, palette)
                return None if value is None or value in ("000000", "AUTO") else value
        return None

    def layout(self, paragraph: Paragraph, size_pt: float) -> ParagraphLayout:
        def resolved(name: str) -> object:
            return self._resolved(paragraph, name)

        line, rule = self._line_spacing(paragraph)
        line_pt = None
        if line is None:
            line_spacing = self._line
        elif isinstance(line, Length):
            line_spacing = round(line.pt / (size_pt * _LINE_HEIGHT_FACTOR), 2)
            line_pt = round(line.pt, 2)
        else:
            line_spacing = float(cast(float, line))
        return ParagraphLayout(
            space_before_pt=_or_given(
                _list_auto_spacing(paragraph, "before"), _pt(resolved("space_before"), 0.0)
            ),
            space_after_pt=_or_given(
                _list_auto_spacing(paragraph, "after"), _pt(resolved("space_after"), self._after_pt)
            ),
            line_spacing=line_spacing,
            line_pt=line_pt,
            line_at_least=rule == WD_LINE_SPACING.AT_LEAST,
            first_line_indent_mm=_mm(resolved("first_line_indent")),
            left_indent_mm=_mm(resolved("left_indent")),
            right_indent_mm=_mm(resolved("right_indent")),
            tabs=self.tabs(paragraph),
            borders=self._borders(paragraph),
            shading=self._shading(paragraph),
            keep_next=bool(resolved("keep_with_next")),
            keep_lines=bool(resolved("keep_together")),
            mark_size_pt=self.mark_size(paragraph),
            mark_font=self.named_mark_font(paragraph),
            frame=_frame(paragraph),
            off_grid=self._off_grid(paragraph),
            no_hyphens=self._flag_on(paragraph, "w:suppressAutoHyphens"),
        )

    def _flag_on(self, paragraph: Paragraph, tag: str) -> bool:
        """An on/off paragraph property: the nearest of the paragraph, its styles, the
        document's defaults; off when none says."""
        elements = [paragraph._p, *(style.element for style in self._styles(paragraph))]
        if self._default_format is not None:
            elements.append(self._default_format._element)
        for element in elements:
            flag = element.find(f"{qn('w:pPr')}/{qn(tag)}")
            if flag is not None:
                return flag.get(qn("w:val")) not in ("0", "false", "off")
        return False

    def _off_grid(self, paragraph: Paragraph) -> bool:
        """'Snap to grid' switched off: the nearest w:snapToGrid of the paragraph or its styles."""
        for element in (paragraph._p, *(style.element for style in self._styles(paragraph))):
            snap = element.find(f"{qn('w:pPr')}/{qn('w:snapToGrid')}")
            if snap is not None:
                return snap.get(qn("w:val")) in ("0", "false", "off")
        return False

    def _line_spacing(self, paragraph: Paragraph) -> tuple[object, object]:
        """Line spacing and its rule, both from the nearest place that sets the spacing."""
        formats = [
            paragraph.paragraph_format,
            *(s.paragraph_format for s in self._styles(paragraph)),
        ]
        found = next((f for f in formats if f.line_spacing is not None), None)
        return (None, None) if found is None else (found.line_spacing, found.line_spacing_rule)

    def _borders(self, paragraph: Paragraph) -> CellBorders | None:
        """Paragraph lines (w:pBdr): the paragraph's own, else its style's."""
        elements = [paragraph._p, *(style.element for style in self._styles(paragraph))]
        found = (e.find(f"{qn('w:pPr')}/{qn('w:pBdr')}") for e in elements)
        p_bdr = next((b for b in found if b is not None), None)
        if p_bdr is None:
            return None
        edges = _edge_lines(p_bdr, _palette(self._document))
        borders = CellBorders(
            **{side: edges.get(side) is not None for side in _SIDES},
            lines=tuple((side, line) for side in _SIDES if (line := edges.get(side)) is not None),
        )
        return None if borders == _NO_BORDERS else borders

    def _shading(self, paragraph: Paragraph) -> str | None:
        """Paragraph background (w:shd): the paragraph's own, else its style's."""
        elements = [paragraph._p, *(style.element for style in self._styles(paragraph))]
        found = (e.find(qn("w:pPr")) for e in elements)
        return next(
            (_fill(p) for p in found if p is not None and p.find(qn("w:shd")) is not None), None
        )

    def tabs(self, paragraph: Paragraph) -> tuple[TabStop, ...]:
        """Tab stops of the style chain, then the paragraph's own: 'clear' removes one."""
        elements = [*(s.element for s in reversed(self._styles(paragraph))), paragraph._p]
        stops: dict[int, TabStop] = {}
        for element in elements:
            for tab in element.findall(f"{qn('w:pPr')}/{qn('w:tabs')}/{qn('w:tab')}"):
                position = _num(tab.get(qn("w:pos")) or 0)
                kind = tab.get(qn("w:val")) or "left"
                if kind == "clear":
                    stops.pop(position, None)
                elif kind != "bar":
                    stops[position] = TabStop(
                        position_mm=round(position / _TWIPS_PER_MM, 2),
                        align=_TAB_ALIGN.get(kind, "left"),
                        leader=_TAB_LEADER.get(tab.get(qn("w:leader")) or "none", "none"),
                    )
        return tuple(stops[p] for p in sorted(stops))


def _theme_font(document: DocxDocument, fonts: BaseOxmlElement | str) -> str | None:
    """Typeface behind a theme font name ('minorHAnsi', 'majorBidi', ...) in the document theme
    (Calibri, Cambria...); for a script the theme leaves empty, Word's own default."""
    theme = fonts if isinstance(fonts, str) else fonts.get(qn("w:asciiTheme"))
    if theme is None:
        return None
    kind = "majorFont" if theme.startswith("major") else "minorFont"
    script = "cs" if theme.endswith("Bidi") else "ea" if theme.endswith("EastAsia") else "latin"
    for rel in document.part.rels.values():
        if rel.reltype.endswith("/theme"):
            a = "http://schemas.openxmlformats.org/drawingml/2006/main"
            root = parse_xml(rel.target_part.blob)
            face = root.find(f".//{{{a}}}{kind}/{{{a}}}{script}")
            if face is not None and face.get("typeface"):
                return str(face.get("typeface"))
            return _EMPTY_THEME_SCRIPT.get(script)
    return None


def _palette(document: DocxDocument) -> dict[str, str]:
    """The document theme's colours by Word's names ('text1', 'accent1', ...), as RRGGBB."""
    for rel in document.part.rels.values():
        if rel.reltype.endswith("/theme"):
            return _palette_of(rel.target_part.blob)
    return {}


@cache
def _palette_of(theme: bytes) -> dict[str, str]:
    scheme = parse_xml(theme).find(f".//{_A}clrScheme")
    found: dict[str, str] = {}
    for element in scheme if scheme is not None else []:
        exact, system = element.find(f"{_A}srgbClr"), element.find(f"{_A}sysClr")
        value = exact.get("val") if exact is not None else None
        value = value or (system.get("lastClr") if system is not None else None)
        if value:
            found[element.tag.split("}")[1]] = str(value).upper()
    return {word: found[name] for word, name in _THEME_NAMES.items() if name in found}


_THEME_NAMES = {
    "text1": "dk1", "dark1": "dk1", "background1": "lt1", "light1": "lt1",
    "text2": "dk2", "dark2": "dk2", "background2": "lt2", "light2": "lt2",
    "accent1": "accent1", "accent2": "accent2", "accent3": "accent3",
    "accent4": "accent4", "accent5": "accent5", "accent6": "accent6",
    "hyperlink": "hlink", "followedHyperlink": "folHlink",
}  # fmt: skip


def _word_colour(element: BaseOxmlElement, palette: dict[str, str]) -> str | None:
    """RRGGBB of a w:color (or a border): a theme colour lightened or darkened as Word does,
    else the colour written down; None for 'auto'."""
    base = palette.get(element.get(qn("w:themeColor")) or "")
    if base is None:
        written = element.get(qn("w:color")) or element.get(qn("w:val"))
        return None if not written or written.lower() == "auto" else written.upper()
    hue, lightness, saturation = colorsys.rgb_to_hls(
        *(int(base[i : i + 2], 16) / 255 for i in (0, 2, 4))
    )
    tint, shade = element.get(qn("w:themeTint")), element.get(qn("w:themeShade"))
    if tint:  # towards white, on the lightness as Word does
        lightness = lightness * int(tint, 16) / 255 + 1 - int(tint, 16) / 255
    if shade:  # towards black
        lightness *= int(shade, 16) / 255
    channels = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "".join(f"{round(c * 255):02X}" for c in channels)


_ASCII_END = 0x7F
_EMPTY_THEME_SCRIPT = {"cs": "Arial"}
"""What Word draws for a theme's empty complex-script font (measured: 'minorBidi' text in Arial)."""

_WORD_AFTER_PT = 8.0
_WORD_LINE = 259 / 240
"""Word's paragraph defaults for a file that sets none (no w:pPrDefault)."""
_AUTO_SPACING_PT = 14.0
"""Word's 'auto' paragraph spacing (HTML-like styles such as 'Normal (Web)')."""


def _or_given(auto: float | None, given: float) -> float:
    return given if auto is None else auto


def _list_auto_spacing(paragraph: Paragraph, side: str) -> float | None:
    """Auto spacing, but none between two items of a list (Word lays them out as a browser
    lays out <li>: the space is around the list, not between its items)."""
    auto = _auto_spacing(paragraph, side)
    if auto is None:
        return None
    neighbour = paragraph._p.getprevious() if side == "before" else paragraph._p.getnext()
    beside = (
        Paragraph(neighbour, paragraph._parent)
        if neighbour is not None and neighbour.tag == qn("w:p")
        else None
    )
    own = _list_id(paragraph)
    same_list = own is not None and beside is not None and _list_id(beside) == own
    return 0.0 if same_list else auto  # two lists side by side keep it between them


def _list_id(paragraph: Paragraph) -> str | None:
    """The list a paragraph is an item of (w:numId), its own or its style's."""
    sources = [paragraph._p]
    with suppress(KeyError, ValueError):
        sources += [s.element for s in _chain(_paragraph_style(paragraph))]
    for source in sources:
        number = source.find(f"{qn('w:pPr')}/{qn('w:numPr')}/{qn('w:numId')}")
        if number is not None:  # 0: numbering taken off, not a list
            value = str(number.get(qn("w:val")) or "0")
            return None if value == "0" else value
    return None


def _auto_spacing(paragraph: Paragraph, side: str) -> float | None:
    """'beforeAutospacing'/'afterAutospacing': the nearest explicit value wins, so a paragraph's
    '0' switches off what its style turns on."""
    attribute = qn(f"w:{side}Autospacing")
    elements = [paragraph._p]
    style = _paragraph_style(paragraph)
    while style is not None:
        elements.append(style.element)
        style = style.base_style
    styles = paragraph.part.package.main_document_part.styles.element
    defaults = styles.find(f"{qn('w:docDefaults')}/{qn('w:pPrDefault')}")
    if defaults is not None:  # last: the document's defaults (HTML-made files turn it on there)
        elements.append(defaults)
    for element in elements:
        spacing = element.find(f"{qn('w:pPr')}/{qn('w:spacing')}")
        value = spacing.get(attribute) if spacing is not None else None
        if value is not None:
            return _AUTO_SPACING_PT if value in ("1", "true", "on") else None
    return None


_TAB_ALIGN: dict[str, Literal["left", "center", "right", "decimal"]] = {
    "left": "left",
    "start": "left",
    "center": "center",
    "right": "right",
    "end": "right",
    "decimal": "decimal",
}
_TAB_LEADER: dict[str, Literal["none", "dot", "underscore", "hyphen"]] = {
    "dot": "dot",
    "middleDot": "dot",
    "underscore": "underscore",
    "heavy": "underscore",
    "hyphen": "hyphen",
}


def _pt(value: object, default: float) -> float:
    return round(float(value.pt), 1) if isinstance(value, Length) else default


def _mm(value: object) -> float:
    return round(float(value.mm), 2) if isinstance(value, Length) else 0.0


class DocxImporter:
    def __init__(self, document_type_id: str = "other", title: str = "") -> None:
        self._type = DocumentTypeGuess(
            id=document_type_id, title=title or "Документ", confidence=1.0
        )

    def load(self, path: Path) -> Document:
        return self.convert(docx.Document(str(path)))

    def convert(self, source: DocxDocument) -> Document:
        """The document model; the pixels of its image blocks are left in `images`."""
        styled = any(  # before python-docx makes up a styles part of its own for a file without
            rel.reltype == RT.STYLES for rel in source.part.rels.values()
        )
        _unwrap_content_controls(source)
        if not source.element.sectPr_lst:  # no page set: Word takes its default page
            source.element.body.append(parse_xml(_WORD_DEFAULT_PAGE))
        _fill_page_defaults(source)
        self.images: dict[str, bytes] = {}
        self._footnote_order: list[int] = []
        self._footnote_text_number = 0
        self._flow_around: dict[
            BaseOxmlElement, tuple[BaseOxmlElement | None, BaseOxmlElement | None]
        ] = {}
        self._formatting = _Formatting(source)
        if not styled:  # Word's own paragraph defaults, as for a file that sets none
            self._formatting.use_words_defaults()
        self._source = source
        numbering = _Numbering.from_document(source)
        self._numbering = numbering
        blocks = self._blocks(_flow(source.element.body, source), numbering, "b")
        first = source.sections[0]._sectPr
        if blocks and (columns := _section_start(first)).columns > 1:
            # the first section in columns: no break before it, only its layout
            blocks[0] = blocks[0].model_copy(
                update={"section": columns.model_copy(update={"new_page": False, "page": None})}
            )
        if blocks and self._starts_with_auto_spacing(source):
            blocks[0] = _without_space_before(blocks[0])

        section = source.sections[0]
        first_page = section.different_first_page_header_footer
        header = section.first_page_header if first_page else section.header
        footer = section.first_page_footer if first_page else section.footer
        return Document(
            document_type=self._type,
            orientation=_orientation(section),
            page=_geometry(section),
            page_numbers=self._page_numbers(section),
            spacing_rule=self._formatting.spacing_rule,
            compat_mode=_compat_mode(source),
            compat_switches=_compat_switches(source),
            compat_settings=_compat_settings(source),
            default_tab_pt=_default_tab(source),
            hyphenation=_hyphenation(source),
            language=_language(source),
            page_background=_page_background(source),
            fonts=_font_faces(source),
            footnotes=self._footnotes(source),
            blocks=tuple(blocks),
            header=tuple(self._margin(header, numbering, "h")),
            footer=tuple(self._margin(footer, numbering, "f")),
        )

    def _blocks(
        self,
        items: "Iterator[_Item]",
        numbering: _Numbering,
        prefix: str,
        *,
        keep_trailing_gap: bool = False,
    ) -> list[Block]:
        flow = _Flow(self, numbering, prefix)
        breaks = _PageBreaks(self._source.element.body)
        for item in items:
            if isinstance(item, Table):
                flow.add_table(item)
                continue
            if isinstance(item, _TextBox):
                flow.add_text_box(item)
                continue
            if isinstance(item, _Shape):
                flow.add_shape(item)
                continue
            split = breaks.after_pictures(item)  # pictures, a page break, then its text
            if breaks.before(item, self._formatting.page_break_before(item)) and not split:
                flow.page_break()
            elif breaks.column_before(item):
                flow.column_break()
            if not _strip_ads(item.text):
                flow.add_paragraph(item, break_after_floating=split)
            section = breaks.next_section(item)
            if section is not None:
                flow.section(_section_start(section))
            elif breaks.after(item):
                flow.page_break()
            elif breaks.column_after(item):
                flow.column_break()
        return flow.finish(keep_trailing_gap=keep_trailing_gap)

    def _margin(self, part: _Header | _Footer, numbering: _Numbering, prefix: str) -> list[Block]:
        """Header or footer content; the page number line is kept as Document.page_numbers."""
        if part.is_linked_to_previous:
            return []
        # the empty lines at the end take room too, once the header has anything in it
        blocks = self._blocks(_margin_items(part), numbering, prefix, keep_trailing_gap=True)
        first = next(iter(_margin_items(part)), None)
        if blocks and isinstance(first, Paragraph) and _auto_spacing(first, "before"):
            blocks[0] = _without_space_before(blocks[0])  # as at the top of the body
        flow = [  # a framed paragraph (a page number in a frame) stands aside, out of the flow
            c
            for c in part._element
            if c.tag == qn("w:tbl")
            or (c.tag == qn("w:p") and c.find(f"{qn('w:pPr')}/{qn('w:framePr')}") is None)
        ]
        single = len(flow) == 1
        framed = any(  # a frame hangs from the line after it: that line takes its room
            c.tag == qn("w:p") and c.find(f"{qn('w:pPr')}/{qn('w:framePr')}") is not None
            for c in part._element
        )
        bare = single and not framed and not _formatted_empty_line(part)
        if bare and all(isinstance(b, SpacerBlock) for b in blocks):
            return []  # Word lets the text start above a header of one bare empty line
        return blocks

    def _page_numbers(self, section: Section) -> PageNumbers | None:
        """The paragraph of a header or footer that holds a PAGE field."""
        parts = (("top", section.header), ("bottom", section.footer))
        for position, part in parts:
            if part.is_linked_to_previous:
                continue
            for paragraph in part.paragraphs:
                if _has_page_field(paragraph):
                    frame = dict(_frame(paragraph) or ())
                    return PageNumbers(
                        position="top" if position == "top" else "bottom",
                        align=_FRAME_ALIGN.get(frame.get("xAlign", ""))  # a number in a frame
                        or self._formatting.alignment(paragraph),  # stands where the frame does
                        frame=_frame(paragraph),
                        first_page=self._numbered_first_page(section, position),
                        **self._number_look(paragraph),
                    )
        return None

    def _number_look(self, paragraph: Paragraph) -> dict[str, object]:
        """Size, face and spacing of the page number's line, as the original sets them."""
        formatting = self._formatting
        first = paragraph.runs[0] if paragraph.runs else None
        size = formatting.run_size(first, paragraph) if first is not None else None
        return {
            "size_pt": size,
            "font": formatting.run_font(first, paragraph) if first is not None else None,
            "layout": formatting.layout(paragraph, size or _DEFAULT_SIZE_PT),
        }

    @staticmethod
    def _numbered_first_page(section: Section, position: str) -> bool:
        """A title page has its own header and footer: without one of its own it stays empty."""
        if not section.different_first_page_header_footer:
            return True
        part = section.first_page_header if position == "top" else section.first_page_footer
        return not part.is_linked_to_previous and any(map(_has_page_field, part.paragraphs))

    def _starts_with_auto_spacing(self, source: DocxDocument) -> bool:
        """Like HTML, Word drops the auto spacing above the very first paragraph."""
        first = next(iter(self._body(source)), None)
        return isinstance(first, Paragraph) and bool(_auto_spacing(first, "before"))

    @staticmethod
    def _body(source: DocxDocument) -> "Iterator[_Item]":
        yield from _flow(source.element.body, source)

    def _framed(self, paragraph: Paragraph, block_id: str) -> ParagraphBlock:
        """A paragraph in a frame at a fixed place: its text as it is, in its frame."""
        runs = self._runs(paragraph, pictures=True)
        size = runs[0].size_pt if runs and runs[0].size_pt else _DEFAULT_SIZE_PT
        return ParagraphBlock(
            id=block_id,
            runs=runs,
            align=self._formatting.alignment(paragraph),
            layout=self._formatting.layout(paragraph, size),
        )

    def _paragraph(
        self, paragraph: Paragraph, numbering: _Numbering, block_id: str, seen_heading: bool
    ) -> Block:
        text = paragraph.text
        align = self._formatting.alignment(paragraph)
        runs = self._runs(paragraph, pictures=True)
        size = runs[0].size_pt if runs and runs[0].size_pt else _DEFAULT_SIZE_PT
        layout = self._formatting.layout(paragraph, size)

        auto = numbering.marker(paragraph)  # first: every numbered line counts
        if auto is not None:
            marker, level = auto
            indent = numbering.indent(paragraph)
            if indent is not None:
                left, first_line = indent
                layout = layout.model_copy(
                    update={"left_indent_mm": left, "first_line_indent_mm": first_line}
                )
            marker_font, marker_size = numbering.look(paragraph)
            glyph = numbering.glyph(paragraph)
            return ListItemBlock(
                id=block_id,
                marker=marker,
                level=level,
                runs=runs,
                layout=layout,
                align=align,
                marker_font=marker_font,
                marker_size_pt=marker_size,
                marker_glyph=glyph,
                marker_gap=numbering.gap(paragraph),
            )
        manual = _MANUAL_MARKER.match("".join(r.text for r in runs))
        if manual and align is not Alignment.CENTER:
            marker = manual.group(1)
            return ListItemBlock(
                id=block_id,
                marker=marker,
                runs=_cut_prefix(runs, manual.end()),
                layout=layout,
                align=align,
            )

        bold = bool(runs) and all(r.bold for r in runs if r.text.strip())
        short = len(text.strip()) <= _HEADING_MAX_CHARS
        if align is Alignment.CENTER and short and (bold or text.strip().isupper()):
            return HeadingBlock(
                id=block_id, level=2 if seen_heading else 1, runs=runs, align=align, layout=layout
            )
        return ParagraphBlock(id=block_id, runs=runs, align=align, layout=layout)

    def _runs(self, paragraph: Paragraph, *, pictures: bool = False) -> tuple[Run, ...]:
        """The paragraph's runs; with `pictures`, a picture standing in the line is a run of
        its own where it stands (cells keep theirs apart, as CellImage)."""
        runs: list[Run] = []
        fields = _field_runs(paragraph)
        for run in _all_runs(paragraph, equations=True):
            if not isinstance(run, DocxRun):  # an equation where it stands
                runs.append(Run(text=_math_text(run), math=etree.tostring(run, encoding="unicode")))
                continue
            mark = self._footnote_mark(run, paragraph)
            if mark is not None:
                runs.append(mark)
                continue
            if pictures:
                runs += self._inline_pictures(run, paragraph)
            runs += [
                Run(text=_vml_text(drawing), vml=_vml_as_written(pict, drawing))
                for pict in run._r.findall(qn("w:pict"))
                if (drawing := _inline_vml(pict)) is not None
            ]
            text = _run_text(run)
            if not text:
                continue
            if self._formatting.flag(run, paragraph, "all_caps"):  # Word shows it in capitals
                text = text.upper()
            font = run.font
            current = Run(
                text=text,
                bold=self._formatting.flag(run, paragraph, "bold"),
                italic=self._formatting.flag(run, paragraph, "italic"),
                underline=self._formatting.flag(run, paragraph, "underline"),
                strike=self._formatting.flag(run, paragraph, "strike"),
                superscript=bool(font.superscript),
                subscript=bool(font.subscript),
                size_pt=self._formatting.run_size(run, paragraph),
                color=self._formatting.run_color(run),
                font=self._formatting.run_font(run, paragraph),
                spacing_pt=self._formatting.letter_spacing(run, paragraph),
                kern_pt=self._formatting.kerning(run, paragraph),
                scale_pct=self._formatting.scale(run, paragraph),
                background=_run_background(run),
                field=fields.get(run._r),
                clear=_clear_of(run._r, paragraph),
            )
            if runs and runs[-1].model_copy(update={"text": ""}) == current.model_copy(
                update={"text": ""}
            ):
                runs[-1] = runs[-1].model_copy(update={"text": runs[-1].text + text})
            else:
                runs.append(current)
        if runs:  # trim spaces at the end; a line break there still takes a line in Word
            # Spaces and tabs at the start stay: old blanks push a line to the right with them.
            # Tabs at the end stay too: Word gives them room, and tabs past the right edge take
            # a line of their own (a leader tab draws the last blank of a fill line). So do
            # blanks that are underlined or tinted: they are the line to write on.
            tail = _BLANKS.replace("\t", "")
            if not (runs[-1].underline or runs[-1].background):
                runs[-1] = runs[-1].model_copy(update={"text": runs[-1].text.rstrip(tail)})
        return _with_breaks_inside(tuple(r for r in runs if r.text or r.picture or r.vml))

    def _inline_pictures(self, run: DocxRun, paragraph: Paragraph) -> list[Run]:
        """Pictures standing in the line inside this run; their pixels go to `images`."""
        found: list[Run] = []
        for picture in _pictures_in(run._r):
            part = paragraph.part.related_parts.get(picture.rel_id)
            if picture.floating is not None or part is None:
                continue  # a floating one is a block of its own; a linked one has no pixels
            image_id = f"inline-image-{len(self.images) + 1}"
            self.images[image_id] = part.blob
            inline = InlinePicture(
                image_id=image_id,
                width_mm=picture.width_mm,
                height_mm=picture.height_mm,
                crop=picture.crop,
            )
            found.append(Run(text="", picture=inline))
        return found

    def _footnote_mark(self, run: DocxRun, paragraph: Paragraph) -> Run | None:
        """A footnote reference in the text, or the number at the start of a note."""
        reference = run._r.find(qn("w:footnoteReference"))
        own = run._r.find(qn("w:footnoteRef"))
        if reference is None and own is None:
            return None
        if reference is not None:
            number = _num(reference.get(qn("w:id")) or 0)
            self._footnote_order.append(number)
            text = str(len(self._footnote_order))
        else:
            number, text = 0, str(self._footnote_text_number)
        return Run(
            text=text,
            superscript=True,
            size_pt=self._formatting.run_size(run, paragraph),
            font=self._formatting.run_font(run, paragraph),
            footnote=number,
        )

    def _footnotes(self, source: DocxDocument) -> tuple[Footnote, ...]:
        """The notes the text refers to, in the order of their marks."""
        part = next(
            (
                p
                for p in source.part.package.iter_parts()
                if str(p.partname) == "/word/footnotes.xml"
            ),
            None,
        )
        if part is None or not self._footnote_order:
            return ()
        notes = {
            _num(n.get(qn("w:id")) or 0): n for n in parse_xml(part.blob).findall(qn("w:footnote"))
        }
        found = []
        for order, number in enumerate(self._footnote_order, start=1):
            note = notes.get(number)
            if note is None:
                continue
            self._footnote_text_number = order
            paragraphs = []
            for p in note.findall(qn("w:p")):
                paragraph = Paragraph(p, source._body)
                runs = self._runs(paragraph)
                size = next((r.size_pt for r in runs if r.size_pt), None) or _DEFAULT_SIZE_PT
                paragraphs.append(
                    FootnoteParagraph(
                        runs=runs,
                        layout=self._formatting.layout(paragraph, size),
                        align=self._formatting.alignment(paragraph),
                    )
                )
            found.append(Footnote(id=number, paragraphs=tuple(paragraphs)))
        return tuple(found)

    def _table(self, table: Table, block_id: str) -> TableBlock | None:
        tbl = table._tbl
        self._note_flow(tbl)
        widths = _grid_widths_mm(tbl)
        borders = _TableBorders(tbl, self._source)
        n_rows, n_cols = len(tbl.tr_lst), len(widths)
        properties = _TableProperties(tbl, table.style)
        base = properties.padding() or _padding_mm(_DEFAULT_PADDING_TWIPS)
        rows: list[TableRow] = []
        for row_index, tr in enumerate(tbl.tr_lst):
            cells: list[TableCell] = []
            column = _grid_before(tr)
            for tc in tr.tc_lst:
                span = tc.grid_span
                v_merge = tc.tcPr.find(qn("w:vMerge")) if tc.tcPr is not None else None
                if v_merge is not None and v_merge.get(qn("w:val")) in (None, "continue"):
                    column += span
                    continue  # covered by the row span of a cell above
                rest = self._merged_rest(tc)
                row_span = 1 + len(rest)
                edges = {
                    "last_row": row_index + row_span >= n_rows,
                    "first_col": column == 0,
                    "last_col": column + span >= n_cols,
                }
                lines = borders.of(tc, first_row=row_index == 0, **edges)
                if rest:  # a merged cell's bottom line is its last row's (6488ab1f)
                    lines = _with_bottom(lines, borders.of(rest[-1], first_row=False, **edges))
                cells.append(
                    self._cell(table, tc, span, rest, lines).model_copy(
                        update={"padding": _cell_padding(tc, base)}
                    )
                )
                column += span
            # a row of merged continuations only stays: the spans above count it, and it has
            # a height of its own
            if tr.tc_lst:
                height, exact = _row_height(tr)
                rows.append(
                    TableRow(
                        cells=tuple(cells),
                        height_mm=height,
                        exact_height=exact,
                        skip=_grid_before(tr),
                    )
                )
        if not rows:
            return None  # an empty table with nothing to see still takes room: it stays
        all_borders = [c.borders for r in rows for c in r.cells]
        grid = all(b == CellBorders() for b in all_borders)
        invisible = all(b == _NO_BORDERS for b in all_borders)
        if grid or invisible:
            rows = [_without_borders(r) for r in rows]
        return TableBlock(
            id=block_id,
            rows=tuple(rows),
            header_rows=0,
            column_widths=tuple(widths) if widths else None,
            width_mm=round(sum(widths), 2) if widths else None,
            grid=grid,
            align=properties.align(),
            indent_mm=properties.indent_mm(),
            padding=properties.padding(),
            cell_spacing_mm=properties.cell_spacing_mm(),
            autofit=properties.autofit(),
            position=_position(tbl),
        )

    def _cell(
        self, table: Table, tc: CT_Tc, col_span: int, rest: list[CT_Tc], borders: CellBorders
    ) -> TableCell:
        # Empty paragraphs stay as line breaks: they are what makes a blank cell tall.
        paragraphs: list[Paragraph] = []
        nested: list[NestedTable] = []
        for child in tc.iterchildren(qn("w:p"), qn("w:tbl")):
            if child.tag == qn("w:tbl"):
                inner = Table(cast(CT_Tbl, child), table)
                with self._formatting.inside(inner):
                    block = self._table(inner, f"nested-{len(nested)}")
                if block is not None:
                    nested.append(NestedTable(after_line=len(paragraphs), table=block))
            elif not _strip_ads((paragraph := Paragraph(child, table)).text):
                paragraphs.append(paragraph)
        paragraphs = paragraphs or [Paragraph(p, table) for p in tc.p_lst[:1]]
        runs: list[Run] = []
        for index, cell_paragraph in enumerate(paragraphs):
            if index:
                runs.append(Run(text="\n", size_pt=self._formatting.mark_size(cell_paragraph)))
            auto = self._numbering.marker(cell_paragraph)
            if auto is not None:  # a numbered line in a cell: its number, then a tab, as Word
                font, size = self._numbering.look(cell_paragraph)
                own = self._runs(cell_paragraph)
                mark = size or (
                    own[0].size_pt if own else self._formatting.mark_size(cell_paragraph)
                )
                glyph = self._numbering.glyph(cell_paragraph)
                gap = self._numbering.gap(cell_paragraph) if own else ""  # nothing after it
                if glyph is not None:  # a bullet: its own sign in its own typeface
                    runs.append(Run(text=f"{glyph}{gap}", size_pt=mark, font=font))
                else:
                    symbol = auto[0] == "•"  # a picture bullet: a dot in the text face
                    runs.append(
                        Run(text=f"{auto[0]}{gap}", size_pt=mark, font=None if symbol else font)
                    )
            runs += self._runs(cell_paragraph)
        written = [p for p in paragraphs if p.text.strip()]
        first = written[0] if written else paragraphs[0]
        texts = [r for r in runs if r.text.strip()]
        size = texts[0].size_pt if texts and texts[0].size_pt else self._formatting.mark_size(first)
        v_align = tc.tcPr.find(qn("w:vAlign")) if tc.tcPr is not None else None
        turned = tc.tcPr.find(qn("w:textDirection")) if tc.tcPr is not None else None
        direction = turned.get(qn("w:val")) if turned is not None else None
        return TableCell(
            runs=tuple(runs),
            align=self._formatting.alignment(first),
            col_span=col_span,
            row_span=1 + len(rest),
            borders=borders,
            v_align=_V_ALIGN.get(v_align.get(qn("w:val"))) if v_align is not None else None,
            layout=self._cell_line_layout(first, size, paragraphs),
            line_layouts=self._line_layouts(paragraphs, size),
            line_aligns=self._line_aligns(paragraphs),
            images=self._cell_images(paragraphs),
            size_pt=size,
            hide_mark=tc.tcPr is not None and tc.tcPr.find(qn("w:hideMark")) is not None,
            shading=_fill(tc.tcPr),
            text_direction=direction if direction not in (None, "lrTb", "tb") else None,
            tables=tuple(nested),
            rest_sizes_pt=tuple(
                self._formatting.mark_size(Paragraph(other.p_lst[0], table))
                for other in rest
                if other.p_lst
            ),
        )

    def _cell_images(self, paragraphs: list[Paragraph]) -> tuple[CellImage, ...]:
        """Pictures of the cell's lines; their pixels go to `images` like those of blocks."""
        found: list[CellImage] = []
        for line, paragraph in enumerate(paragraphs):
            for picture in _pictures(paragraph):
                part = paragraph.part.related_parts.get(picture.rel_id)
                if part is None:
                    continue
                image_id = f"cell-image-{len(self.images) + 1}"
                self.images[image_id] = part.blob
                found.append(
                    CellImage(
                        line=line,
                        image_id=image_id,
                        width_mm=picture.width_mm,
                        height_mm=picture.height_mm,
                        floating=picture.floating,
                        crop=picture.crop,
                    )
                )
        return tuple(found)

    def _note_flow(self, tbl: BaseOxmlElement) -> None:
        """The paragraph before and after each paragraph of the table as the document reads,
        the lines just outside the table included (a nested table keeps the outer reading)."""
        outside = (tbl.getprevious(), tbl.getnext())
        flow = [
            outside[0] if outside[0] is not None and outside[0].tag == qn("w:p") else None,
            *tbl.iter(qn("w:p")),
            outside[1] if outside[1] is not None and outside[1].tag == qn("w:p") else None,
        ]
        for index in range(1, len(flow) - 1):
            self._flow_around.setdefault(flow[index], (flow[index - 1], flow[index + 1]))

    def _cell_line_layout(
        self, paragraph: Paragraph, size: float, paragraphs: list[Paragraph]
    ) -> ParagraphLayout:
        """A cell line's spacing and indents; a numbered line hangs its number as its level.
        Like at the top of the page, Word drops auto spacing at the top and bottom of a cell."""
        layout = self._formatting.layout(paragraph, size)
        update: dict[str, float | None] = {}
        if paragraph is paragraphs[0] and _auto_spacing(paragraph, "before"):
            update["space_before_pt"] = 0.0
        if paragraph is paragraphs[-1] and _auto_spacing(paragraph, "after"):
            update["space_after_pt"] = 0.0
        if self._formatting.contextual(paragraph):  # no spacing next to its own style
            # the neighbours are the paragraphs before and after it as the document reads,
            # across cell and row edges: the cell above, the line before the table (measured)
            above, below = self._flow_around.get(paragraph._p, (None, None))
            if above is not None and _style_of(above) == _style_id(paragraph):
                update["space_before_pt"] = 0.0
            if below is not None and _style_of(below) == _style_id(paragraph):
                update["space_after_pt"] = 0.0
        indent = self._numbering.indent(paragraph)
        if indent is not None:
            update["left_indent_mm"], update["first_line_indent_mm"] = indent
        return layout.model_copy(update=update) if update else layout

    def _line_layouts(
        self, paragraphs: list[Paragraph], size: float
    ) -> tuple[ParagraphLayout, ...]:
        """Each paragraph's spacing and indents, kept only when they are not all alike."""
        layouts = tuple(self._cell_line_layout(p, size, paragraphs) for p in paragraphs)
        return layouts if len(set(layouts)) > 1 else ()

    def _line_aligns(self, paragraphs: list[Paragraph]) -> tuple[Alignment, ...]:
        """Each paragraph's alignment, kept only when they are not all alike."""
        aligns = tuple(self._formatting.alignment(p) for p in paragraphs)
        return aligns if len(set(aligns)) > 1 else ()

    @staticmethod
    def _merged_rest(tc: CT_Tc) -> list[CT_Tc]:
        """The cells below that a vertically merged cell continues into."""
        tc_pr = tc.tcPr
        v_merge = tc_pr.find(qn("w:vMerge")) if tc_pr is not None else None
        if v_merge is None or v_merge.get(qn("w:val")) != "restart":
            return []
        rest: list[CT_Tc] = []
        row = tc.getparent()
        column = _grid_before(row) + sum(c.grid_span for c in row.tc_lst[: row.tc_lst.index(tc)])
        for next_row in row.itersiblings(qn("w:tr")):
            col, found = _grid_before(next_row), None
            for cell in next_row.tc_lst:
                if col == column:
                    found = cell
                    break
                col += cell.grid_span
            merge = (
                found.tcPr.find(qn("w:vMerge"))
                if found is not None and found.tcPr is not None
                else None
            )
            if found is None or merge is None or merge.get(qn("w:val")) == "restart":
                break
            rest.append(found)
        return rest


def _grid_before(tr: CT_Row) -> int:
    """Grid columns a row leaves empty before its first cell (w:gridBefore)."""
    before = tr.find(f"{qn('w:trPr')}/{qn('w:gridBefore')}")
    return _num(before.get(qn("w:val")) or 0) if before is not None else 0


def _run_background(run: DocxRun) -> str | None:
    """A highlighter colour, else the run's own shading."""
    properties = run._r.rPr
    marker = properties.find(qn("w:highlight")) if properties is not None else None
    if marker is not None:
        colour = _HIGHLIGHTS.get(marker.get(qn("w:val")) or "none")
        if colour is not None:
            return colour
    return _fill(properties)


_HIGHLIGHTS = {
    "black": "000000", "blue": "0000FF", "cyan": "00FFFF", "green": "00FF00",
    "magenta": "FF00FF", "red": "FF0000", "yellow": "FFFF00", "darkBlue": "000080",
    "darkCyan": "008080", "darkGreen": "008000", "darkMagenta": "800080", "darkRed": "800000",
    "darkYellow": "808000", "darkGray": "808080", "lightGray": "C0C0C0",
}  # fmt: skip
"""Word's highlighter colours; 'white' and 'none' leave the page as it is."""


def _fill(properties: BaseOxmlElement | None) -> str | None:
    """The background colour a w:shd sets, as RRGGBB; None for none or white."""
    shading = properties.find(qn("w:shd")) if properties is not None else None
    if shading is None:
        return None
    if shading.get(qn("w:val")) == "solid":  # the pattern colour covers it all
        colour = shading.get(qn("w:color")) or "auto"
        return "000000" if colour == "auto" else colour.upper()
    fill = (shading.get(qn("w:fill")) or "auto").upper()
    return None if fill in ("AUTO", "FFFFFF") else fill


def _with_breaks_inside(runs: tuple[Run, ...]) -> tuple[Run, ...]:
    """A line break that is a run of its own joins its neighbour: in a cell (TableCell.runs) a
    run of just a newline starts a new paragraph, while this one breaks the line inside it."""
    joined: list[Run] = []
    pending = ""
    clear: Literal["all", "left", "right"] | None = None
    for run in runs:
        if run.text == "\n":
            if joined and joined[-1].picture is None:
                joined[-1] = joined[-1].model_copy(
                    update={"text": joined[-1].text + "\n", "clear": run.clear or joined[-1].clear}
                )
            else:
                pending += "\n"
                clear = clear or run.clear
            continue
        if pending and run.picture is not None:  # a picture carries no text: the break stays
            joined += [Run(text=pending, clear=clear), run]
        elif pending:
            joined.append(
                run.model_copy(update={"text": pending + run.text, "clear": clear or run.clear})
            )
        else:
            joined.append(run)
        pending = ""
        clear = None
    if pending:  # nothing but breaks: keep them, they still take lines
        return runs
    return tuple(joined)


_WORD_DEFAULT_PAGE = (
    '<w:sectPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="850" w:bottom="1134" '
    'w:left="1701" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
)
"""The page Word gives a document that sets none: A4, margins 3 / 1.5 / 2 / 2 cm (measured)."""


def _fill_page_defaults(source: DocxDocument) -> None:
    """A section that leaves out its size is Letter, one that leaves out its margins gets the
    default ones (measured in Word: unlike a document with no section at all, which is A4)."""
    defaults = parse_xml(_WORD_DEFAULT_PAGE)
    letter = parse_xml(f'<w:pgSz xmlns:w="{_W_NS[1:-1]}" w:w="12240" w:h="15840"/>')
    for sect_pr in source.element.sectPr_lst:
        if sect_pr.find(qn("w:pgMar")) is None:
            sect_pr.insert(0, deepcopy(defaults.find(qn("w:pgMar"))))
        if sect_pr.find(qn("w:pgSz")) is None:
            sect_pr.insert(0, deepcopy(letter))


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_FRACTION = re.compile(r"-?\d+\.\d+")


def _plain_text(root: BaseOxmlElement) -> None:
    """A raw line feed or carriage return inside w:t (as PHPWord writes) breaks no line in
    Word: a space, as it is shown; only w:br and w:cr break a line."""
    for text in root.iter(qn("w:t")):
        if text.text and _RAW_BREAK.search(text.text):
            text.text = _RAW_BREAK.sub(" ", text.text)


_RAW_BREAK = re.compile(r"\r\n|[\r\n]")


def _whole_numbers(root: BaseOxmlElement) -> None:
    """'359.99999999999994' where Word writes whole twips, rounded as Word reads it."""
    for element in root.iter():
        for name, value in element.attrib.items():
            if name.startswith(_W_NS) and _FRACTION.fullmatch(value):
                element.set(name, str(round(float(value))))


def _unwrap_content_controls(source: DocxDocument) -> None:
    """Content controls (w:sdt) in the body, headers and footers give way to what they hold, in
    place, as Word shows it: python-docx walks past them and their text would be lost.
    Fractions in Word's numbers are rounded first: python-docx reads them as whole numbers."""
    stories = (qn("w:document"), qn("w:hdr"), qn("w:ftr"))
    hidden = _hidden_styles(source)
    for part in source.part.package.iter_parts():
        root = getattr(part, "_element", None)
        if root is not None:
            _whole_numbers(root)
            _plain_text(root)
        if root is None or root.tag not in stories:
            continue
        for control in list(root.iter(qn("w:sdt"))):
            parent = control.getparent()
            content = control.find(qn("w:sdtContent"))
            for child in list(content) if content is not None else []:
                control.addprevious(child)
            parent.remove(control)
        # smart tags and custom XML wrap runs the same way: '127015, г.' marked as an address
        for tag in list(root.iter(qn("w:smartTag"), qn("w:customXml"))):
            for child in list(tag):
                if child.tag not in (qn("w:smartTagPr"), qn("w:customXmlPr")):
                    tag.addprevious(child)
            tag.getparent().remove(tag)
        _wrap_stray_content(root)
        _accept_changes(root)
        _drop_hidden(root, hidden)


_STRAY = (qn("w:br"), qn("w:cr"), qn("w:tab"), qn("w:t"))


def _wrap_stray_content(root: BaseOxmlElement) -> None:
    """A break, tab or text written straight in the paragraph, outside any run (web exports
    do it; Word shows them), goes in a run of its own with the formatting of the run before
    (58a67267: '<w:p>…</w:r><w:br/><w:br/><w:r>…' lost its empty lines between clauses)."""
    for paragraph in root.iter(qn("w:p")):
        for child in list(paragraph):
            if child.tag not in _STRAY:
                continue
            run = OxmlElement("w:r")
            before = child.getprevious()
            properties = (
                before.find(qn("w:rPr")) if before is not None and before.tag == qn("w:r") else None
            )
            if properties is not None:
                run.append(deepcopy(properties))
            child.addprevious(run)
            run.append(child)


def _line_breaks(paragraph: Paragraph) -> int:
    """Line breaks (not page or column breaks) in the paragraph's text. A break that clears the
    paragraph's own floating pictures is the picture's (ImageBlock.clear), not a line."""
    floating = any(p.floating is not None for p in _pictures(paragraph))
    return sum(
        1
        for brk in paragraph._p.iter(qn("w:br"), qn("w:cr"))
        if brk.get(qn("w:type")) in (None, "textWrapping")
        and not any(a.tag in _INSIDE_DRAWINGS for a in brk.iterancestors())
        and not (floating and brk.get(qn("w:clear")) in ("all", "left", "right"))
    )


def _vanishes(properties: BaseOxmlElement | None) -> bool | None:
    """True or False when these run properties say whether the text is hidden, else None."""
    mark = properties.find(qn("w:vanish")) if properties is not None else None
    if mark is None:
        return None
    return (mark.get(qn("w:val")) or "true").lower() not in ("0", "false", "off")


def _hidden_styles(source: DocxDocument) -> set[str]:
    """Ids of the styles whose text is hidden, by their own word or their base style's."""
    try:
        styles = source.styles.element
    except (KeyError, ValueError):
        return set()
    own: dict[str, bool | None] = {}
    based: dict[str, str] = {}
    for style in styles.iter(qn("w:style")):
        sid = style.get(qn("w:styleId")) or ""
        own[sid] = _vanishes(style.find(qn("w:rPr")))
        base = style.find(qn("w:basedOn"))
        if base is not None:
            based[sid] = base.get(qn("w:val")) or ""

    def hidden(sid: str, depth: int = 0) -> bool:
        if own.get(sid) is not None or sid not in based or depth > 20:  # noqa: PLR2004
            return bool(own.get(sid))
        return hidden(based[sid], depth + 1)

    return {sid for sid in own if hidden(sid)}


def _drop_hidden(root: BaseOxmlElement, hidden_styles: set[str]) -> None:
    """Hidden text and pictures (w:vanish) go: Word neither shows nor prints them. A run's own
    word wins, then its character style's, then its paragraph style's. Parts of a field stay,
    or the field would break."""
    for run in list(root.iter(qn("w:r"))):
        if run.find(qn("w:fldChar")) is not None:
            continue
        properties = run.find(qn("w:rPr"))
        verdict = _vanishes(properties)
        if verdict is None and properties is not None:
            style = properties.find(qn("w:rStyle"))
            if style is not None and style.get(qn("w:val")) in hidden_styles:
                verdict = True
        if verdict is None:
            paragraph = next((a for a in run.iterancestors() if a.tag == qn("w:p")), None)
            style = (
                paragraph.find(f"{qn('w:pPr')}/{qn('w:pStyle')}") if paragraph is not None else None
            )
            verdict = style is not None and style.get(qn("w:val")) in hidden_styles
        if verdict and run.getparent() is not None:
            run.getparent().remove(run)
    for paragraph in list(root.iter(qn("w:p"))):  # a hidden mark with nothing left to show:
        if _empty_hidden_paragraph(paragraph, hidden_styles):  # the line is gone too
            paragraph.getparent().remove(paragraph)


def _empty_hidden_paragraph(paragraph: BaseOxmlElement, hidden_styles: set[str]) -> bool:
    properties = paragraph.find(qn("w:pPr"))
    if properties is None or properties.find(qn("w:sectPr")) is not None:
        return False
    verdict = _vanishes(properties.find(qn("w:rPr")))
    if verdict is None:
        style = properties.find(qn("w:pStyle"))
        verdict = style is not None and style.get(qn("w:val")) in hidden_styles
    if not verdict or any(True for _ in paragraph.iter(qn("w:t"), qn("w:drawing"), qn("w:pict"))):
        return False
    breaks = [
        b for b in paragraph.iter(qn("w:br")) if b.get(qn("w:type")) in (None, "textWrapping")
    ]
    if breaks:  # each visible break ends a line Word shows; only the mark's own line is hidden:
        breaks[-1].getparent().remove(breaks[-1])  # an empty line with one break fewer
        marks = properties.find(qn("w:rPr"))  # (c9ad5c61: a line between two tables)
        for mark in marks.findall(qn("w:vanish")) if marks is not None else ():
            marks.remove(mark)
        return False
    cell = paragraph.getparent()
    if cell.tag == qn("w:tc") and len(cell.findall(qn("w:p"))) == 1:
        return False  # a cell keeps one
    tables = (paragraph.getprevious(), paragraph.getnext())
    if all(
        t is not None
        and t.tag == qn("w:tbl")
        and t.find(f"{qn('w:tblPr')}/{qn('w:tblpPr')}") is None
        for t in tables
    ):  # two tables in the flow would join: Word keeps them apart by a line of almost nothing
        _hairline(properties)
        return False
    return True


def _hairline(properties: BaseOxmlElement) -> None:
    """The paragraph becomes a visible line 1 pt high with no space around (measured: what a
    hidden empty line between two tables takes in Word)."""
    marks = properties.find(qn("w:rPr"))
    if marks is not None:
        for mark in marks.findall(qn("w:vanish")):
            marks.remove(mark)
    for old in properties.findall(qn("w:spacing")):
        properties.remove(old)
    spacing = OxmlElement(
        "w:spacing",
        {qn("w:before"): "0", qn("w:after"): "0", qn("w:line"): "20", qn("w:lineRule"): "exact"},
    )
    properties.insert_element_before(
        spacing, "w:ind", "w:contextualSpacing", "w:jc", "w:outlineLvl", "w:rPr", "w:pPrChange"
    )


def _accept_changes(root: BaseOxmlElement) -> None:
    """Tracked changes as the final document reads: insertions stay, deletions go."""
    for change in list(root.iter(qn("w:del"), qn("w:moveFrom"))):
        if change.getparent() is not None and change.getparent().tag != qn("w:rPr"):
            change.getparent().remove(change)
    for change in list(root.iter(qn("w:ins"), qn("w:moveTo"))):
        parent = change.getparent()
        if parent is None or parent.tag in (qn("w:rPr"), qn("w:trPr")):
            continue  # a mark on properties, not text
        for child in list(change):
            change.addprevious(child)
        parent.remove(change)


@overload
def _all_runs(paragraph: Paragraph) -> list[DocxRun]: ...


@overload
def _all_runs(paragraph: Paragraph, *, equations: bool) -> list[DocxRun | BaseOxmlElement]: ...


def _all_runs(
    paragraph: Paragraph, *, equations: bool = False
) -> list[DocxRun] | list[DocxRun | BaseOxmlElement]:
    """Runs including those inside hyperlinks and simple fields, which Paragraph.runs leaves
    out; with `equations`, Word's equations (m:oMath, m:oMathPara) where they stand."""
    runs: list[DocxRun | BaseOxmlElement] = []
    for child in paragraph._p:
        if child.tag == qn("w:r"):
            runs.append(DocxRun(child, paragraph))
        elif child.tag in (qn("w:hyperlink"), qn("w:fldSimple")):
            runs += [DocxRun(r, paragraph) for r in child.findall(qn("w:r"))]
        elif equations and child.tag in _EQUATIONS:
            runs.append(child)
    return runs


_MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
_EQUATIONS = (f"{_MATH}oMath", f"{_MATH}oMathPara")


def _math_text(equation: BaseOxmlElement) -> str:
    return "".join(t.text or "" for t in equation.iter(f"{_MATH}t"))


def _has_equation(paragraph: Paragraph) -> bool:
    return any(child.tag in _EQUATIONS for child in paragraph._p)


_FIELD_KINDS: dict[str, Literal["page", "pages"]] = {"PAGE": "page", "NUMPAGES": "pages"}


def _field_runs(paragraph: Paragraph) -> dict[BaseOxmlElement, Literal["page", "pages"]]:
    """Runs that show the result of a page number or page count field, by run element."""
    found: dict[BaseOxmlElement, Literal["page", "pages"]] = {}
    state, code = None, ""
    for element in paragraph._p.iter(qn("w:r"), qn("w:fldSimple")):
        if element.tag == qn("w:fldSimple"):
            words = (element.get(qn("w:instr")) or "").split()
            kind = _FIELD_KINDS.get(words[0]) if words else None
            if kind is not None:
                found.update(dict.fromkeys(element.findall(qn("w:r")), kind))
            continue
        for child in element:
            if child.tag == qn("w:fldChar"):
                state = {"begin": "code", "separate": "result"}.get(
                    child.get(qn("w:fldCharType")) or ""
                )
                code = "" if state == "code" else code
            elif child.tag == qn("w:instrText") and state == "code":
                code += child.text or ""
            elif child.tag == qn("w:t") and state == "result":
                kind = _FIELD_KINDS.get(code.split()[0] if code.split() else "")
                if kind is not None:
                    found[element] = kind
    return found


_TWIPS_PER_MM = 1440 / 25.4
_BLANKS = " 	 "
_NO_BORDERS = CellBorders(top=False, bottom=False, left=False, right=False)
_SIDES = ("top", "bottom", "left", "right")
_INVISIBLE = ("nil", "none")
_WHITE = "FFFFFF"


_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


class _PageBreaks:
    """Where the original starts a new page: a manual page break, 'page break before', or the
    end of a section when the next one starts on a new page (not 'continuous')."""

    def __init__(self, body: BaseOxmlElement) -> None:
        ends = [p for p in body.iterchildren(qn("w:p")) if p.find(_SECTION_END) is not None]
        sections = list(body.iter(qn("w:sectPr")))
        # keyed by the elements themselves: kept alive, lxml hands out the same objects again
        self._next: dict[BaseOxmlElement, BaseOxmlElement] = dict(
            zip(ends, sections[1:], strict=False)
        )

    @staticmethod
    def _page_break(paragraph: Paragraph, kind: str = "page") -> tuple[bool, bool]:
        """Whether the paragraph holds a page (or column) break, and whether text comes
        before it."""
        text_before = False
        for element in paragraph._p.iter(qn("w:t"), qn("w:br")):
            if element.tag == qn("w:br") and element.get(qn("w:type")) == kind:
                return True, text_before
            text_before = text_before or bool(element.text and element.text.strip())
        return False, False

    @staticmethod
    def after_pictures(paragraph: Paragraph) -> bool:
        """Floating pictures come before the page break and text only after it: the pictures
        stay on the page before (a sample picture, then the next page's caption)."""
        floating = False
        for element in paragraph._p.iter(qn("w:t"), qn("w:br"), qn("w:drawing")):
            if element.tag == qn("w:drawing"):
                floating = floating or element.find(f"{_WP}anchor") is not None
            elif element.tag == qn("w:br"):
                if element.get(qn("w:type")) == "page":
                    return floating and bool(paragraph.text.strip())
            elif element.text and element.text.strip():
                return False
        return False

    def before(self, paragraph: Paragraph, break_before: bool) -> bool:
        has_break, text_before = self._page_break(paragraph)
        return break_before or (has_break and not text_before and bool(paragraph.text.strip()))

    def after(self, paragraph: Paragraph) -> bool:
        has_break, text_before = self._page_break(paragraph)
        return has_break and (text_before or not paragraph.text.strip())

    def column_before(self, paragraph: Paragraph) -> bool:
        """A break before any text or picture, even in an empty paragraph: Word sets the whole
        paragraph, its spacing and its line, in the next column (9144a589)."""
        has_break, content_before = self._column_break(paragraph)
        return has_break and not content_before

    def column_after(self, paragraph: Paragraph) -> bool:
        has_break, content_before = self._column_break(paragraph)
        return has_break and content_before

    @staticmethod
    def _column_break(paragraph: Paragraph) -> tuple[bool, bool]:
        """Whether the paragraph holds a column break, and whether text or a picture comes
        before it: a picture there stays in the column before (67884356)."""
        content_before = False
        for element in paragraph._p.iter(qn("w:t"), qn("w:br"), qn("w:drawing"), qn("w:pict")):
            if element.tag == qn("w:br"):
                if element.get(qn("w:type")) == "column":
                    return True, content_before
            elif element.tag == qn("w:t"):
                content_before = content_before or bool(element.text and element.text.strip())
            else:
                content_before = True
        return False, False

    def next_section(self, paragraph: Paragraph) -> BaseOxmlElement | None:
        """The properties of the section this paragraph's section break starts."""
        return self._next.get(paragraph._p)


_SECTION_END = f"{qn('w:pPr')}/{qn('w:sectPr')}"


def _section_start(sect_pr: BaseOxmlElement) -> SectionStart:
    """How a section starts and how it is laid out, from its w:sectPr."""
    kind = sect_pr.find(qn("w:type"))
    cols = sect_pr.find(qn("w:cols"))
    count = _num(cols.get(qn("w:num")) or 1) if cols is not None else 1
    space = cols.get(qn("w:space")) if cols is not None else None
    own = (
        tuple(
            (
                round(_num(col.get(qn("w:w")) or 0) / _TWIPS_PER_MM, 2),
                round(_num(col.get(qn("w:space")) or 0) / _TWIPS_PER_MM, 2),
            )
            for col in cols.findall(qn("w:col"))
        )
        if cols is not None and cols.get(qn("w:equalWidth")) in ("0", "false")
        else ()
    )
    return SectionStart(
        new_page=kind is None or kind.get(qn("w:val")) != "continuous",
        columns=max(count, len(own), 1),
        column_gap_mm=round(float(space) / _TWIPS_PER_MM, 2) if space else 12.5,
        column_widths_mm=own,
        page=_sect_geometry(sect_pr),
    )


@dataclass(frozen=True, slots=True)
class _TextBox:
    """A text box floating at a fixed place: its content, frame and position."""

    content: BaseOxmlElement
    shape: BaseOxmlElement
    placement: ImagePlacement
    width_mm: float
    height_mm: float


@dataclass(frozen=True, slots=True)
class _Shape:
    """A line or a rectangle floating at a fixed place."""

    geometry: ShapeGeometry
    placement: ImagePlacement
    width_mm: float
    height_mm: float
    flip_h: bool
    flip_v: bool
    line_pt: float
    color: str | None = None
    head: ArrowEnd = "none"
    tail: ArrowEnd = "none"
    fill: str | None = None
    path: str | None = None
    vml: str | None = None


_Item = Paragraph | Table | _TextBox | _Shape
_GEOMETRY: dict[str, ShapeGeometry] = {
    "line": "line", "straightConnector1": "line", "rect": "rect", "roundRect": "roundRect",
    "ellipse": "ellipse", "triangle": "triangle", "diamond": "diamond",
    "flowChartDecision": "diamond", "flowChartProcess": "rect",
    "flowChartAlternateProcess": "roundRect", "flowChartTerminator": "roundRect",
    "rightArrow": "rightArrow", "leftArrow": "leftArrow", "upArrow": "upArrow",
    "downArrow": "downArrow",
}  # fmt: skip


def _flow(container: BaseOxmlElement, source: ProvidesStoryPart) -> Iterator[_Item]:
    """Paragraphs, tables and floating text boxes in reading order.

    A text box is stored twice (DrawingML and a VML fallback for old Word); only the first
    copy is read. A box anchored at a place of its own stays a box; any other is read into the
    flow where it is anchored.
    """
    for element in container.iterchildren():
        if element.tag == qn("w:tbl"):
            yield Table(element, source)
        elif element.tag == qn("w:p"):
            for box in element.iter(qn("w:txbxContent")):
                if any(a.tag == _FALLBACK for a in box.iterancestors()):
                    continue
                if _inside_box(box, element):
                    continue  # a box in a box: read with the outer one
                floating = _text_box(box)
                if floating is not None:
                    yield floating
                else:
                    yield from _flow(box, source)
            paragraph = Paragraph(element, source)
            if _frame(paragraph) is not None:  # drawn from inside its frame: kept there
                yield paragraph
                yield from _shapes(element)
                yield from _vml_lines(element)
                yield from _vml_drawings(element)
            else:
                yield from _shapes(element)
                yield from _vml_lines(element)
                yield from _vml_drawings(element)
                yield paragraph


def _shapes(paragraph: BaseOxmlElement) -> Iterator[_Shape]:
    """Lines and rectangles without text anchored in this paragraph (not in a box or group)."""
    for shape in paragraph.iter(f"{_WPS}wsp"):
        if shape.find(f"{_WPS}txbx") is not None or any(
            a.tag in (_FALLBACK, qn("w:txbxContent")) for a in shape.iterancestors()
        ):
            continue
        geometry = shape.find(f"{_WPS}spPr/{_A}prstGeom")
        free = shape.find(f"{_WPS}spPr/{_A}custGeom")
        kind: ShapeGeometry | None = (
            _GEOMETRY.get(geometry.get("prst") or "")
            if geometry is not None
            else ("custom" if free is not None else None)
        )
        drawing = next((a for a in shape.iterancestors() if a.tag == qn("w:drawing")), None)
        if kind is None or drawing is None:
            continue
        frame = shape.find(f"{_WPS}spPr/{_A}xfrm")
        if any(a.tag == f"{_WPG}wgp" for a in shape.iterancestors()):
            piece = _in_group(shape, frame, drawing)
            if piece is None:
                continue
            placement, width_mm, height_mm = piece
        else:
            anchored = _placement(drawing)
            extent = next(drawing.iter(f"{_WP}extent"), None)
            if anchored is None or extent is None:
                continue
            placement = anchored
            width_mm = round(_num(extent.get("cx") or 0) / _EMU_PER_MM, 2)
            height_mm = round(_num(extent.get("cy") or 0) / _EMU_PER_MM, 2)
        line = shape.find(f"{_WPS}spPr/{_A}ln")
        fill = _shape_fill(shape)
        unlined = line is not None and line.find(f"{_A}noFill") is not None
        if fill is None and (unlined or (line is None and kind == "custom")):
            continue  # nothing drawn
        yield _Shape(
            kind,
            placement,
            width_mm,
            height_mm,
            frame is not None and frame.get("flipH") in ("1", "true"),
            frame is not None and frame.get("flipV") in ("1", "true"),
            0.0
            if unlined or (line is None and fill is not None)
            else round(_num(line.get("w") or 9525) / _EMU_PER_PT, 2)
            if line is not None
            else 0.75,
            *_line_look(line),
            fill,
            etree.tostring(free, encoding="unicode") if kind == "custom" else None,
        )


def _shape_fill(shape: BaseOxmlElement) -> str | None:
    """RRGGBB of a shape's own solid fill (not a theme's)."""
    colour = shape.find(f"{_WPS}spPr/{_A}solidFill/{_A}srgbClr")
    return (colour.get("val") or "").upper() or None if colour is not None else None


def _in_group(
    piece: BaseOxmlElement, frame: BaseOxmlElement | None, drawing: BaseOxmlElement
) -> tuple[ImagePlacement, float, float] | None:
    """Where a piece of a group floats on its own: its frame in the group's units, carried out
    through each group around it to the group's anchor. None for a group in the line of text
    or aligned rather than placed (no point to start from)."""
    placement = _placement(drawing)
    extent = next(drawing.iter(f"{_WP}extent"), None)
    if (
        frame is None
        or placement is None
        or extent is None
        or placement.x_mm is None
        or placement.y_mm is None
    ):
        return None
    x, y, cx, cy = _xfrm(frame)
    root = None
    for group in piece.iterancestors(f"{_WPG}grpSp", f"{_WPG}wgp"):
        own = group.find(f"{_WPG}grpSpPr/{_A}xfrm")
        if own is None:
            return None
        off_x, off_y, ext_x, ext_y = _xfrm(own)
        child = own.find(f"{_A}chOff")
        child_ext = own.find(f"{_A}chExt")
        ch_x, ch_y = (_num(child.get(k) or 0) for k in ("x", "y")) if child is not None else (0, 0)
        ch_cx, ch_cy = (
            (_num(child_ext.get(k) or 0) for k in ("cx", "cy"))
            if child_ext is not None
            else (ext_x, ext_y)
        )
        scale_x = ext_x / ch_cx if ch_cx else 1.0
        scale_y = ext_y / ch_cy if ch_cy else 1.0
        x, y = off_x + (x - ch_x) * scale_x, off_y + (y - ch_y) * scale_y
        cx, cy = cx * scale_x, cy * scale_y
        root = (off_x, off_y, ext_x, ext_y)
        if group.tag == f"{_WPG}wgp":
            break
    if root is None:
        return None
    # the outermost group fills the anchor's box
    page_x = _num(extent.get("cx") or 0) / root[2] if root[2] else 1.0
    page_y = _num(extent.get("cy") or 0) / root[3] if root[3] else 1.0
    moved = placement.model_copy(
        update={
            "x_mm": round(placement.x_mm + (x - root[0]) * page_x / _EMU_PER_MM, 2),
            "y_mm": round(placement.y_mm + (y - root[1]) * page_y / _EMU_PER_MM, 2),
        }
    )
    return moved, round(cx * page_x / _EMU_PER_MM, 2), round(cy * page_y / _EMU_PER_MM, 2)


def _xfrm(frame: BaseOxmlElement) -> tuple[float, float, float, float]:
    offset, size = frame.find(f"{_A}off"), frame.find(f"{_A}ext")
    x, y = (_num(offset.get(k) or 0) for k in ("x", "y")) if offset is not None else (0, 0)
    cx, cy = (_num(size.get(k) or 0) for k in ("cx", "cy")) if size is not None else (0, 0)
    return x, y, cx, cy


def _group_pictures(drawing: BaseOxmlElement) -> "list[_Picture]":
    """The pictures of a group, each at its own place and size."""
    found: list[_Picture] = []
    filled = [  # a shape filled with a picture draws that picture
        shape
        for shape in drawing.iter(f"{_WPS}wsp")
        if shape.find(f"{_WPS}spPr/{_A}blipFill") is not None
    ]
    for picture in [*drawing.iter(f"{_PIC}pic"), *filled]:
        if any(a.tag == _FALLBACK for a in picture.iterancestors()):
            continue
        blip = next(picture.iter(f"{_A}blip"), None)
        rel_id = blip.get(f"{_R}embed") if blip is not None else None
        properties = f"{_PIC}spPr" if picture.tag == f"{_PIC}pic" else f"{_WPS}spPr"
        piece = _in_group(picture, picture.find(f"{properties}/{_A}xfrm"), drawing)
        if rel_id is None or piece is None:
            continue
        placement, width_mm, height_mm = piece
        found.append(_Picture(rel_id, width_mm or None, height_mm or None, placement))
    return found


_PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"


def _line_look(line: BaseOxmlElement | None) -> tuple[str | None, ArrowEnd, ArrowEnd]:
    """Colour and arrow heads of a DrawingML line."""
    if line is None:
        return None, "none", "none"
    colour = line.find(f"{_A}solidFill/{_A}srgbClr")
    value = (colour.get("val") or "").upper() if colour is not None else ""
    ends = [line.find(f"{_A}{name}") for name in ("headEnd", "tailEnd")]
    kinds: list[ArrowEnd] = [
        _ARROWS.get(end.get("type") or "", "none") if end is not None else "none" for end in ends
    ]
    return (value if value not in ("", "000000") else None), kinds[0], kinds[1]


_ARROWS: dict[str, ArrowEnd] = {
    "triangle": "triangle", "stealth": "stealth", "arrow": "arrow", "diamond": "diamond",
    "oval": "oval",
    # VML names
    "block": "triangle", "classic": "stealth", "open": "arrow",
}  # fmt: skip


def _frame(paragraph: Paragraph) -> tuple[tuple[str, str], ...] | None:
    """The paragraph's frame at a fixed place (w:framePr), attributes as written: its style's,
    overridden one by one by its own (as Word reads them: a style's 'from the text' stays)."""
    try:
        styles = list(_chain(_paragraph_style(paragraph)))
    except (KeyError, ValueError):  # a part without styles
        styles = []
    found: dict[str, str] = {}
    sources = [*(style.element.find(qn("w:pPr")) for style in reversed(styles)), paragraph._p.pPr]
    framed = False
    for properties in sources:
        frame = properties.find(qn("w:framePr")) if properties is not None else None
        if frame is not None:
            framed = True
            found |= {name.split("}")[1]: str(value) for name, value in frame.attrib.items()}
    return tuple(found.items()) if framed else None


_FRAME_ALIGN = {
    "left": Alignment.LEFT, "center": Alignment.CENTER, "right": Alignment.RIGHT,
    "inside": Alignment.LEFT, "outside": Alignment.RIGHT,
}  # fmt: skip


def _shares_frame(paragraph: Paragraph) -> bool:
    """Its frame is its neighbour's too: Word draws them as one frame of several lines."""
    frame = _frame(paragraph)
    for neighbour in (paragraph._p.getprevious(), paragraph._p.getnext()):
        if (
            neighbour is not None
            and neighbour.tag == qn("w:p")
            and _frame(Paragraph(neighbour, paragraph._parent)) == frame
        ):
            return True
    return False


def _vml_lines(paragraph: BaseOxmlElement) -> Iterator[_Shape]:
    """Old-style (VML) lines floating at a fixed place: from one point to another. Kept as
    written too: Word places the text around them its own way."""
    for line in paragraph.iter(f"{_V}line"):
        if any(a.tag in (_FALLBACK, f"{_V}group") for a in line.iterancestors()):
            continue  # in a group the ends are in the group's own units
        if (line.get("stroked") or "t").lower() in ("f", "false"):
            continue
        placement = _vml_placement(line)
        ends = [
            [_vml_length_pt(v) * _MM_PER_PT for v in (line.get(k) or "0,0").split(",")[:2]]
            for k in ("from", "to")
        ]
        if placement is None or any(len(end) != 2 for end in ends):  # noqa: PLR2004
            continue
        (x0, y0), (x1, y1) = ends
        placement = placement.model_copy(
            update={"x_mm": round(min(x0, x1), 2), "y_mm": round(min(y0, y1), 2)}
        )
        backwards = (x1 - x0) * (y1 - y0) < 0
        weight = _vml_length_pt(line.get("strokeweight")) or 0.75
        stroke = line.find(f"{_V}stroke")
        arrows: list[ArrowEnd] = [
            _ARROWS.get(stroke.get(name) or "", "none") if stroke is not None else "none"
            for name in ("startarrow", "endarrow")
        ]
        colour = (line.get("strokecolor") or "").strip().lstrip("#").split(" ")[0].upper()
        yield _Shape(
            "line",
            placement,
            round(abs(x1 - x0), 2),
            round(abs(y1 - y0), 2),
            backwards,
            False,
            round(weight, 2),
            colour if re.fullmatch(r"[0-9A-F]{6}", colour) and colour != "000000" else None,
            arrows[0],
            arrows[1],
            vml=_vml_as_written(line.getparent(), line)
            if line.getparent().tag == qn("w:pict")
            else None,
        )


def _vml_drawings(paragraph: BaseOxmlElement) -> Iterator[_Shape]:
    """Old-style (VML) drawings floating at a fixed place, without text or pictures in them: the
    lines and boxes a PDF converter draws, a group of them, a frame. Kept as they are (w:pict):
    Word places the text around them its own way."""
    for pict in paragraph.iter(qn("w:pict")):
        if any(a.tag in (_FALLBACK, qn("w:txbxContent")) for a in pict.iterancestors()):
            continue
        shape = next((c for c in pict if c.tag != f"{_V}shapetype"), None)
        if shape is None or shape.tag.removeprefix(_V) not in _VML_DRAWN:
            continue  # a line is read as one (_vml_lines); a control or nothing
        if shape.tag == f"{_V}shape" and shape.get("path") is None and shape.get("type") is None:
            continue
        if next(shape.iter(f"{_V}textbox", f"{_V}imagedata"), None) is not None:
            continue  # a text box or a picture: read as such
        style = {
            key.strip(): value.strip()
            for key, _, value in (p.partition(":") for p in (shape.get("style") or "").split(";"))
        }
        placement = _vml_placement(shape)
        if placement is None:
            continue
        stroked = (shape.get("stroked") or "t").lower() not in ("f", "false")
        filled = (shape.get("filled") or "t").lower() not in ("f", "false")
        fill = _vml_colour(shape.get("fillcolor"), "FFFFFF") if filled else None
        if not stroked and fill is None and shape.tag != f"{_V}group":
            continue  # nothing drawn
        colour = _vml_colour(shape.get("strokecolor"), "000000")
        flip = style.get("flip", "")
        yield _Shape(
            _VML_DRAWN[shape.tag.removeprefix(_V)],
            placement,
            round(_vml_length_pt(style.get("width")) * _MM_PER_PT, 2),
            round(_vml_length_pt(style.get("height")) * _MM_PER_PT, 2),
            "x" in flip,
            "y" in flip,
            round(_vml_length_pt(shape.get("strokeweight")) or 0.75, 2) if stroked else 0.0,
            colour if colour != "000000" else None,
            fill=fill,
            vml=_vml_as_written(pict, shape),
        )


def _inline_vml(pict: BaseOxmlElement) -> BaseOxmlElement | None:
    """The drawing of an old-style w:pict standing in the line, without a picture or a text box
    in it (those are read as such); None for anything else."""
    shape = next((c for c in pict if c.tag != f"{_V}shapetype"), None)
    if shape is None or shape.tag.removeprefix(_V) not in (*_VML_DRAWN, "line"):
        return None
    if shape.tag == f"{_V}shape" and shape.get("path") is None and shape.get("type") is None:
        return None
    if next(shape.iter(f"{_V}textbox", f"{_V}imagedata"), None) is not None:
        return None
    if any(a.tag in (_FALLBACK, qn("w:txbxContent")) for a in pict.iterancestors()):
        return None
    return shape if _vml_placement(shape) is None else None


def _vml_text(shape: BaseOxmlElement) -> str:
    """What WordArt says (v:textpath), else nothing."""
    path = next(shape.iter(f"{_V}textpath"), None)
    return (path.get("string") or "") if path is not None else ""


def _vml_as_written(pict: BaseOxmlElement, shape: BaseOxmlElement) -> str:
    """The w:pict as it is, with the shape type it names when that is defined elsewhere."""
    copy = deepcopy(pict)
    kind = (shape.get("type") or "").lstrip("#")
    defined = {t.get("id") for t in copy.iter(f"{_V}shapetype")}
    if kind and kind not in defined:
        types = pict.getroottree().getroot().iter(f"{_V}shapetype")
        found = next((t for t in types if t.get("id") == kind), None)
        if found is not None:
            copy.insert(0, deepcopy(found))
    return re.sub(r' o:gfxdata="[^"]*"', "", etree.tostring(copy, encoding="unicode"))


_VML_DRAWN: dict[str, ShapeGeometry] = {
    "shape": "custom", "group": "custom", "polyline": "custom",
    "rect": "rect", "oval": "ellipse", "roundrect": "roundRect",
}  # fmt: skip
"""Old-style drawings kept as written, by their tag in the VML namespace."""
_VML_NAMES = {
    "black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000",
    "blue": "0000FF", "yellow": "FFFF00", "gray": "808080", "silver": "C0C0C0",
}  # fmt: skip


def _vml_colour(value: str | None, default: str) -> str:
    """RRGGBB of a VML colour (#rrggbb, #rgb or a name); the default for one not known."""
    colour = (value or "").strip().split(" ")[0].lower()
    if colour in _VML_NAMES:
        return _VML_NAMES[colour]
    colour = colour.lstrip("#")
    if re.fullmatch(r"[0-9a-f]{3}", colour):
        colour = "".join(c * 2 for c in colour)
    return colour.upper() if re.fullmatch(r"[0-9a-f]{6}", colour) else default


def _inside_box(box: BaseOxmlElement, paragraph: BaseOxmlElement) -> bool:
    for ancestor in box.iterancestors():
        if ancestor is paragraph:
            return False
        if ancestor.tag == qn("w:txbxContent"):
            return True
    return False


def _text_box(content: BaseOxmlElement) -> _TextBox | None:
    """The floating box around this text box content; None when it sits in the line of text
    or at a place we do not keep."""
    shape = next((a for a in content.iterancestors() if a.tag == f"{_WPS}wsp"), None)
    drawing = next((a for a in content.iterancestors() if a.tag == qn("w:drawing")), None)
    if shape is None or drawing is None:
        return _vml_text_box(content)
    if any(a.tag == f"{_WPG}wgp" for a in shape.iterancestors()):
        piece = _in_group(shape, shape.find(f"{_WPS}spPr/{_A}xfrm"), drawing)
        return _TextBox(content, shape, *piece) if piece is not None else None
    placement = _placement(drawing)
    extent = next(drawing.iter(f"{_WP}extent"), None)
    if placement is None or extent is None:
        return None
    return _TextBox(
        content,
        shape,
        placement,
        round(_num(extent.get("cx") or 0) / _EMU_PER_MM, 2),
        round(_num(extent.get("cy") or 0) / _EMU_PER_MM, 2),
    )


def _without_borders(row: TableRow) -> TableRow:
    cells = tuple(c.model_copy(update={"borders": None}) for c in row.cells)
    return row.model_copy(update={"cells": cells})


def _grid_widths_mm(tbl: CT_Tbl) -> list[float]:
    grid = tbl.find(qn("w:tblGrid"))
    if grid is None:
        return []
    widths = [_num(c.get(qn("w:w")) or 0) / _TWIPS_PER_MM for c in grid.findall(qn("w:gridCol"))]
    return [round(w, 2) for w in widths] if all(widths) else []


_POSITION = {
    "horzAnchor": "horizontal_anchor",
    "vertAnchor": "vertical_anchor",
    "tblpXSpec": "x_align",
    "tblpYSpec": "y_align",
}
_POSITION_TWIPS = {
    "tblpX": "x_mm",
    "tblpY": "y_mm",
    "leftFromText": "gap_left_mm",
    "rightFromText": "gap_right_mm",
    "topFromText": "gap_top_mm",
    "bottomFromText": "gap_bottom_mm",
}


def _position(tbl: CT_Tbl) -> TablePosition | None:
    """A floating table's place (w:tblpPr), as Word stores it."""
    element = tbl.tblPr.find(qn("w:tblpPr")) if tbl.tblPr is not None else None
    if element is None:
        return None
    values: dict[str, object] = {
        key: element.get(qn(f"w:{name}"))
        for name, key in _POSITION.items()
        if element.get(qn(f"w:{name}")) is not None
    }
    for name, key in _POSITION_TWIPS.items():
        raw = element.get(qn(f"w:{name}"))
        if raw is not None:
            values[key] = round(_num(raw) / _TWIPS_PER_MM, 2)
    return TablePosition.model_validate(values)


def _ruled(borders: CellBorders | None) -> bool:
    return borders is not None and any((borders.top, borders.bottom, borders.left, borders.right))


def _row_height(tr: CT_Row) -> tuple[float | None, bool]:
    """Height in mm and whether it is exact (without a rule Word takes it as 'at least')."""
    tr_pr = tr.find(qn("w:trPr"))
    height = tr_pr.find(qn("w:trHeight")) if tr_pr is not None else None
    if height is None or height.get(qn("w:val")) is None:
        return None, False
    exact = height.get(qn("w:hRule")) == "exact"
    return round(_num(height.get(qn("w:val"))) / _TWIPS_PER_MM, 2), exact


_OLD_WORD = 12
"""A file that names no compatibility mode was saved by Word 2007 or older and is laid out so."""


def _compat_switches(source: DocxDocument) -> tuple[str, ...]:
    compat = source.settings.element.find(qn("w:compat"))
    if compat is None:
        return ()
    return tuple(
        child.tag.split("}")[1]
        for child in compat
        if child.tag != qn("w:compatSetting")
        and child.get(qn("w:val")) not in ("0", "false", "off")
    )


def _font_faces(source: DocxDocument) -> tuple[FontFace, ...]:
    part = next(
        (p for p in source.part.package.iter_parts() if str(p.partname) == "/word/fontTable.xml"),
        None,
    )
    if part is None:
        return ()
    faces = []
    for font in parse_xml(part.blob).findall(qn("w:font")):

        def value(tag: str, font: BaseOxmlElement = font) -> str | None:
            element = font.find(qn(f"w:{tag}"))
            return element.get(qn("w:val")) if element is not None else None

        faces.append(
            FontFace(
                name=font.get(qn("w:name")) or "",
                family=value("family"),
                panose=value("panose1"),
                charset=value("charset"),
                pitch=value("pitch"),
                alt_name=value("altName"),
                signature=_signature(font.find(qn("w:sig"))),
                not_true_type=font.find(qn("w:notTrueType")) is not None,
            )
        )
    return tuple(f for f in faces if f.name)


def _signature(sig: BaseOxmlElement | None) -> tuple[tuple[str, str], ...]:
    if sig is None:
        return ()
    return tuple((name.split("}")[-1], str(value)) for name, value in sig.attrib.items())


def _language(source: DocxDocument) -> str | None:
    """The language text takes when it names none (the defaults' w:lang)."""
    lang = source.styles.element.find(
        f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:lang')}"
    )
    return lang.get(qn("w:val")) if lang is not None else None


def _hyphenation(source: DocxDocument) -> tuple[tuple[str, str], ...]:
    """The document's automatic hyphenation, when it is on: its settings as written."""
    settings = source.settings.element
    on = settings.find(qn("w:autoHyphenation"))
    if on is None or on.get(qn("w:val")) in ("0", "false", "off"):
        return ()
    names = ("autoHyphenation", "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps")
    found = ((name, settings.find(qn(f"w:{name}"))) for name in names)
    return tuple((name, str(e.get(qn("w:val")) or "1")) for name, e in found if e is not None)


def _default_tab(source: DocxDocument) -> float | None:
    step = source.settings.element.find(qn("w:defaultTabStop"))
    value = step.get(qn("w:val")) if step is not None else None
    return _num(value) / _TWIPS_PER_PT if value else None


def _page_background(source: DocxDocument) -> str | None:
    """The page colour Word shows and prints when the document asks it to."""
    background = source.element.find(qn("w:background"))
    shown = source.settings.element.find(qn("w:displayBackgroundShape")) is not None
    if background is None or not shown:
        return None
    return _word_colour(background, _palette(source))


def _compat_settings(source: DocxDocument) -> tuple[tuple[str, str], ...]:
    compat = source.settings.element.find(qn("w:compat"))
    if compat is None:
        return ()
    return tuple(
        (str(child.get(qn("w:name"))), str(child.get(qn("w:val"))))
        for child in compat.findall(qn("w:compatSetting"))
        if child.get(qn("w:name")) != "compatibilityMode"
    )


def _compat_mode(source: DocxDocument) -> int:
    setting = source.settings.element.find(
        f"{qn('w:compat')}/{qn('w:compatSetting')}[@{qn('w:name')}='compatibilityMode']"
    )
    value = setting.get(qn("w:val")) if setting is not None else None
    return int(value) if value and value.isdigit() else _OLD_WORD


def _margin_items(part: _Header | _Footer) -> "Iterator[_Item]":
    """A header's or footer's content without the page number line (Document.page_numbers)."""
    return (
        item
        for item in _flow(part._element, part)
        if not isinstance(item, Paragraph) or not _has_page_field(item)
    )


def _style_of(p: BaseOxmlElement) -> str | None:
    style = p.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return style.get(qn("w:val")) if style is not None else None


def _style_id(paragraph: Paragraph) -> str | None:
    return _style_of(paragraph._p)


def _formatted_empty_line(part: _Header | _Footer) -> bool:
    """Whether an empty line of a header or footer carries formatting of its own (alignment,
    spacing, ...): Word then keeps its room, while bare empty lines take none."""
    for paragraph in part.paragraphs:
        props = paragraph._p.pPr
        if paragraph.text.strip() or props is None or props.find(qn("w:framePr")) is not None:
            continue  # a framed line stands aside, out of the flow
        if any(child.tag not in (qn("w:pStyle"), qn("w:rPr")) for child in props):
            return True
    return False


class _TableBorders:
    """Effective cell lines: the cell's own, else the table's, else the table style's."""

    def __init__(self, tbl: CT_Tbl, document: DocxDocument) -> None:
        self._table: dict[str, BorderLine | None] = {}
        self._colours = _palette(document)
        style_id = tbl.find(f"{qn('w:tblPr')}/{qn('w:tblStyle')}")
        if style_id is not None:
            self._merge_style(document, style_id.get(qn("w:val")))
        own = tbl.find(f"{qn('w:tblPr')}/{qn('w:tblBorders')}")
        if own is not None:
            self._table |= _edge_lines(own, self._colours)

    def _merge_style(self, document: DocxDocument, style_id: str | None) -> None:
        chain = []
        styles = document.styles.element
        while style_id:
            style = next(
                (e for e in styles.findall(qn("w:style")) if e.get(qn("w:styleId")) == style_id),
                None,
            )
            if style is None:
                break
            chain.append(style)
            based = style.find(qn("w:basedOn"))
            style_id = based.get(qn("w:val")) if based is not None else None
        for style in reversed(chain):
            borders = style.find(f"{qn('w:tblPr')}/{qn('w:tblBorders')}")
            if borders is not None:
                self._table |= _edge_lines(borders, self._colours)

    def of(
        self, tc: CT_Tc, *, first_row: bool, last_row: bool, first_col: bool, last_col: bool
    ) -> CellBorders:
        own = tc.tcPr.find(qn("w:tcBorders")) if tc.tcPr is not None else None
        cell = _edge_lines(own, self._colours) if own is not None else {}
        row = tc.getparent()  # a row's own table lines (w:tblPrEx) stand in for the table's
        exception = row.find(f"{qn('w:tblPrEx')}/{qn('w:tblBorders')}") if row is not None else None
        table = (
            self._table | _edge_lines(exception, self._colours)
            if exception is not None
            else self._table
        )

        def side(name: str, outer: str, inner: str, is_outer: bool) -> BorderLine | None:
            if name in cell:
                return cell[name]
            return table.get(outer if is_outer else inner)

        found = {
            "top": side("top", "top", "insideH", first_row),
            "bottom": side("bottom", "bottom", "insideH", last_row),
            "left": side("left", "left", "insideV", first_col),
            "right": side("right", "right", "insideV", last_col),
        }
        return CellBorders(
            top=found["top"] is not None,
            bottom=found["bottom"] is not None,
            left=found["left"] is not None,
            right=found["right"] is not None,
            lines=tuple(
                (name, line)
                for name, line in found.items()
                if line is not None and line != _PLAIN_LINE
            ),
        )


def _with_bottom(lines: CellBorders, last: CellBorders) -> CellBorders:
    """The cell's lines with the bottom one of `last`."""
    return lines.model_copy(
        update={
            "bottom": last.bottom,
            "lines": tuple(x for x in lines.lines if x[0] != "bottom")
            + tuple(x for x in last.lines if x[0] == "bottom"),
        }
    )


def _edge_lines(
    element: BaseOxmlElement, palette: dict[str, str] | None = None
) -> dict[str, BorderLine | None]:
    """Each side's line, None where there is none to see."""
    edges: dict[str, BorderLine | None] = {}
    for child in element:
        name = child.tag.split("}")[1]
        name = {"start": "left", "end": "right"}.get(name, name)
        style = child.get(qn("w:val"))
        colour = (_word_colour(child, palette or {}) or "auto").upper()
        if style in _INVISIBLE or colour == _WHITE:  # white: unseen on a white page
            edges[name] = None
            continue
        edges[name] = BorderLine(
            style=style or "single",
            size=_num(child.get(qn("w:sz")) or 4),
            color=None if colour in ("AUTO", "000000") else colour,
            space_pt=_num(child.get(qn("w:space")) or 0),
        )
    return edges


_PLAIN_LINE = BorderLine()


_V_ALIGN = {
    "top": VerticalAlignment.TOP,
    "center": VerticalAlignment.CENTER,
    "bottom": VerticalAlignment.BOTTOM,
}
_DEFAULT_PADDING_TWIPS = {"top": 0, "bottom": 0, "left": 108, "right": 108}
"""Word's cell margins when neither the table nor its style sets them."""


def _chain[S: CharacterStyle](style: S | None) -> Iterator[S]:
    while style is not None:
        yield style
        style = cast("S | None", style.base_style)


class _TableProperties:
    """Table-level properties: the table's own value, else its style chain's."""

    def __init__(self, tbl: CT_Tbl, style: ParagraphStyle | None) -> None:
        self._sources = [tbl.tblPr] + [st.element.find(qn("w:tblPr")) for st in _chain(style)]

    def _find(self, tag: str) -> BaseOxmlElement | None:
        found = (src.find(qn(tag)) for src in self._sources if src is not None)
        return next((element for element in found if element is not None), None)

    def align(self) -> Alignment | None:
        jc = self._find("w:jc")
        return _JC.get(jc.get(qn("w:val")) or "") if jc is not None else None

    def indent_mm(self) -> float | None:
        return self._twips_mm("w:tblInd")

    def cell_spacing_mm(self) -> float | None:
        return self._twips_mm("w:tblCellSpacing")

    def autofit(self) -> bool:
        layout = self._find("w:tblLayout")
        return layout is None or layout.get(qn("w:type")) != "fixed"

    def _twips_mm(self, tag: str) -> float | None:
        element = self._find(tag)
        if element is None or element.get(qn("w:type")) not in (None, "dxa"):
            return None
        return round(_num(element.get(qn("w:w")) or 0) / _TWIPS_PER_MM, 2)

    def padding(self) -> CellPadding | None:
        margins = self._find("w:tblCellMar")
        if margins is None:
            return None
        twips = dict(_DEFAULT_PADDING_TWIPS)
        for side in margins:
            name = side.tag.split("}")[1]
            name = {"start": "left", "end": "right"}.get(name, name)
            if name in twips and side.get(qn("w:type")) in (None, "dxa"):
                twips[name] = _num(side.get(qn("w:w")) or 0)
        return _padding_mm(twips)


def _padding_mm(twips: dict[str, int]) -> CellPadding:
    return CellPadding(**{f"{k}_mm": round(v / _TWIPS_PER_MM, 2) for k, v in twips.items()})


_LOGICAL_SIDES = {"start": "left", "end": "right"}


def _cell_padding(tc: CT_Tc, base: CellPadding) -> CellPadding | None:
    """A cell's own margins (w:tcMar) over the table's: only the sides it sets change."""
    margins = tc.tcPr.find(qn("w:tcMar")) if tc.tcPr is not None else None
    if margins is None:
        return None
    values = base.model_dump()
    for side in margins:
        name = side.tag.split("}")[1]
        key = f"{_LOGICAL_SIDES.get(name, name)}_mm"
        if key in values and side.get(qn("w:type")) in (None, "dxa"):
            values[key] = round(_num(side.get(qn("w:w")) or 0) / _TWIPS_PER_MM, 2)
    return CellPadding(**values)


def _has_page_field(paragraph: Paragraph) -> bool:
    """A line that shows the page number and nothing else (Document.page_numbers); a line
    with words or the page count around it ('Страница 1 из 4') keeps its own fields."""
    if paragraph.text.strip() and not paragraph.text.strip().isdigit():
        return False
    element = paragraph._p
    simple = (f.get(qn("w:instr")) or "" for f in element.iter(qn("w:fldSimple")))
    complex_ = (t.text or "" for t in element.iter(qn("w:instrText")))
    return any(code.split()[:1] == ["PAGE"] for code in (*simple, *complex_))


_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_V = "{urn:schemas-microsoft-com:vml}"
_EMU_PER_MM = 36000
_WPS = "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}"
_WPG = "{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}"
_EMU_PER_PT = 12700
_VML_SIZE = re.compile(r"(width|height):\s*([\d.]+[a-z]*)")


@dataclass(frozen=True, slots=True)
class _Picture:
    rel_id: str
    width_mm: float | None
    height_mm: float | None
    floating: ImagePlacement | None = None
    crop: tuple[float, float, float, float] | None = None
    effect: tuple[int, int, int, int] | None = None


def _effect(drawing: BaseOxmlElement) -> tuple[int, int, int, int] | None:
    """Room kept around a picture in the line for its shadow or glow (wp:effectExtent), EMU."""
    inline = drawing.find(f"{_WP}inline")
    extent = inline.find(f"{_WP}effectExtent") if inline is not None else None
    if extent is None:
        return None
    sides = tuple(_num(extent.get(side) or 0) for side in ("l", "t", "r", "b"))
    return (sides[0], sides[1], sides[2], sides[3]) if any(sides) else None


def _clear_of(
    element: BaseOxmlElement, paragraph: Paragraph
) -> Literal["all", "left", "right"] | None:
    """How a line break in the run or paragraph clears floating objects (f8e56995: the text
    below a floating table). The paragraph's own floating pictures carry it themselves
    (ImageBlock.clear)."""
    value = next(
        (b.get(qn("w:clear")) for b in element.iter(qn("w:br")) if b.get(qn("w:clear")) in _CLEARS),
        None,
    )
    if value is None or any(p.floating is not None for p in _pictures(paragraph)):
        return None
    return cast(Literal["all", "left", "right"], value)


_CLEARS = ("all", "left", "right")


def _clears_floats(paragraph: Paragraph) -> bool:
    """A line break here sends the text after it below the floating pictures (w:clear)."""
    return any(
        br.get(qn("w:clear")) in ("all", "left", "right") for br in paragraph._p.iter(qn("w:br"))
    )


def _pictures(paragraph: Paragraph) -> list[_Picture]:
    """Embedded pictures of a paragraph: DrawingML (Word 2007+) or VML (older files)."""
    return _pictures_in(paragraph._p)


def _inside_other(item: BaseOxmlElement, element: BaseOxmlElement) -> bool:
    """Whether `item` sits in a text box's content or a fallback copy within `element`."""
    for ancestor in item.iterancestors():
        if ancestor is element:
            return False
        if ancestor.tag in (qn("w:txbxContent"), _FALLBACK):
            return True
    return False


def _pictures_in(element: BaseOxmlElement) -> list[_Picture]:
    """Embedded pictures inside this element (a paragraph or one of its runs)."""
    found: list[_Picture] = []
    for drawing in element.iter(qn("w:drawing")):
        if _inside_other(drawing, element):
            continue  # in a text box or a fallback copy: not this paragraph's own
        if next(drawing.iter(f"{_WPG}wgp"), None) is not None:
            found += _group_pictures(drawing)
            continue
        blip = next(drawing.iter(f"{_A}blip"), None)
        extent = next(drawing.iter(f"{_WP}extent"), None)
        rel_id = blip.get(f"{_R}embed") if blip is not None else None
        if rel_id is None:
            continue  # a text box or a shape, not a picture
        size = (
            [round(_num(extent.get(axis) or 0) / _EMU_PER_MM, 2) for axis in ("cx", "cy")]
            if extent is not None
            else [None, None]
        )
        found.append(
            _Picture(
                rel_id,
                size[0] or None,
                size[1] or None,
                _placement(drawing),
                _crop(drawing),
                _effect(drawing),
            )
        )
    for shape in element.iter(f"{_V}shape"):
        data = next(shape.iter(f"{_V}imagedata"), None)
        rel_id = data.get(f"{_R}id") if data is not None else None
        if rel_id is None or _inside_other(shape, element):
            continue
        style = dict(_VML_SIZE.findall(shape.get("style") or ""))
        width, height = (_vml_length_pt(style.get(k)) for k in ("width", "height"))
        found.append(
            _Picture(
                rel_id,
                round(width * _MM_PER_PT, 2) if width else None,
                round(height * _MM_PER_PT, 2) if height else None,
                _vml_placement(shape),
            )
        )
    return found


_INSIDE_DRAWINGS = frozenset(
    (
        qn("w:drawing"),
        qn("w:pict"),
        qn("w:txbxContent"),
        _FALLBACK.replace("Fallback", "AlternateContent"),
    )
)


def _leads(paragraph: Paragraph) -> list[str]:
    """The blanks before each inline picture of a line of pictures, in reading order: the
    spaces or tabs that set them apart on the line, and line breaks above the first one."""
    leads: list[str] = []
    blank = ""
    for run in paragraph._p.iter(qn("w:r")):
        if any(a.tag in _INSIDE_DRAWINGS for a in run.iterancestors()):
            continue  # text of a box or a shape drawn over a picture, not of the line
        inline = any(True for _ in run.iter(f"{_WP}inline")) or any(
            True for _ in run.iter(f"{_V}imagedata")
        )
        if inline:
            leads.append(blank)
            blank = ""
            continue
        for child in run:
            if child.tag == qn("w:t"):
                blank += child.text or ""
            elif child.tag == qn("w:tab"):
                blank += "\t"
            elif child.tag == qn("w:cr") or (
                child.tag == qn("w:br") and child.get(qn("w:type")) in (None, "textWrapping")
            ):
                blank += "\n"  # a line break before a picture: an empty line above it
    return leads


def _crop(drawing: BaseOxmlElement) -> tuple[float, float, float, float] | None:
    """Shares cut off the picture at its left, top, right and bottom (thousandths of a
    percent in the file); None when it is shown whole."""
    rect = next(drawing.iter(f"{_A}srcRect"), None)
    if rect is None:
        return None
    shares = tuple(_num(rect.get(side)) / 100_000 for side in ("l", "t", "r", "b"))
    return (shares[0], shares[1], shares[2], shares[3]) if any(shares) else None


_MM_PER_PT = 25.4 / 72
_VML_UNITS_PT = {"pt": 1.0, "in": 72.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "px": 0.75, "": 1.0}
_VML_FROM = {
    "horizontal": {
        "margin": "margin", "page": "page", "text": "column", "char": "character",
        "left-margin-area": "leftMargin", "right-margin-area": "rightMargin",
        "inner-margin-area": "insideMargin", "outer-margin-area": "outsideMargin",
    },
    "vertical": {
        "margin": "margin", "page": "page", "text": "paragraph", "line": "line",
        "top-margin-area": "topMargin", "bottom-margin-area": "bottomMargin",
        "inner-margin-area": "insideMargin", "outer-margin-area": "outsideMargin",
    },
}  # fmt: skip
_VML_WRAPS = {"topAndBottom": "top_and_bottom", "square": "square", "tight": "square"}
_W10 = "{urn:schemas-microsoft-com:office:word}"


def _vml_length_pt(value: str | None) -> float:
    match = re.fullmatch(r"\s*(-?[\d.]+)\s*([a-z]*)\s*", value or "")
    if match is None:
        return 0.0
    return float(match.group(1)) * _VML_UNITS_PT.get(match.group(2), 1.0)


def _vml_placement(shape: BaseOxmlElement) -> ImagePlacement | None:
    """Where an old-style (VML) picture floats: a watermark behind the text, a logo in the
    margin. None for a picture in the line of text."""
    style = {
        key.strip(): value.strip()
        for key, _, value in (part.partition(":") for part in (shape.get("style") or "").split(";"))
    }
    if style.get("position") != "absolute":
        return None
    values: dict[str, object] = {"behind_text": _vml_length_pt(style.get("z-index")) < 0}
    for axis, key, offset in (("horizontal", "x", "margin-left"), ("vertical", "y", "margin-top")):
        relative = _VML_FROM[axis].get(style.get(f"mso-position-{axis}-relative", "text"))
        if relative is not None:
            values[f"{axis}_from"] = relative
        align = style.get(f"mso-position-{axis}")
        if align in ("left", "center", "right", "inside", "outside", "top", "bottom"):
            values[f"{key}_align"] = align
        else:
            values[f"{key}_mm"] = round(_vml_length_pt(style.get(offset)) * _MM_PER_PT, 2)
    wrap = shape.find(f"{_W10}wrap")
    values["wrap"] = _VML_WRAPS.get(wrap.get("type") or "", "none") if wrap is not None else "none"
    try:
        return ImagePlacement.model_validate(values)
    except ValueError:  # a position kind we do not keep: leave the picture in the line
        return None


_WRAPS = {"wrapNone": "none", "wrapTopAndBottom": "top_and_bottom"}
_INSETS_EMU = {"lIns": 91440, "tIns": 45720, "rIns": 91440, "bIns": 45720}
"""Word's default space inside a text box (2.54 mm at the sides, 1.27 mm above and below)."""


def _box_look(shape: BaseOxmlElement, document: DocxDocument) -> dict[str, object]:
    """Rotation, fill and text placement of a text box shape."""
    look: dict[str, object] = {}
    if shape.tag in _VML_BOXES:  # an old-style box: its fill colour, white when not given
        filled = (shape.get("filled") or "t").lower() not in ("f", "false")
        colour = (shape.get("fillcolor") or "").strip().lstrip("#").split(" ")[0]
        if filled and re.fullmatch(r"[0-9a-fA-F]{6}", colour) and colour.lower() != "ffffff":
            look["fill"] = colour.upper()
        return look
    xfrm = shape.find(f"{_WPS}spPr/{_A}xfrm")
    if xfrm is not None and xfrm.get("rot"):
        look["rotation_deg"] = round(_num(xfrm.get("rot")) / 60000, 2)
    fill = shape.find(f"{_WPS}spPr/{_A}solidFill")
    if fill is not None:
        colour = _drawing_colour(fill, document)
        if colour is not None:
            look["fill"] = colour
    body = shape.find(f"{_WPS}bodyPr")
    if body is not None:
        if body.get("anchor") in ("t", "ctr", "b"):
            look["text_anchor"] = body.get("anchor")
        if body.get("vert"):
            look["text_direction"] = body.get("vert")
        if body.find(f"{_A}spAutoFit") is not None:
            look["grows"] = True
    return look


def _drawing_colour(fill: BaseOxmlElement, document: DocxDocument) -> str | None:
    """RRGGBB of a DrawingML colour: given outright, or one of the document theme's."""
    rgb = fill.find(f"{_A}srgbClr")
    if rgb is not None:
        return str(rgb.get("val")).upper()
    scheme = fill.find(f"{_A}schemeClr")
    if scheme is None:
        return None
    name = _COLOUR_MAP.get(scheme.get("val") or "", scheme.get("val") or "")
    for rel in document.part.rels.values():
        if rel.reltype.endswith("/theme"):
            colour = parse_xml(rel.target_part.blob).find(f".//{_A}clrScheme/{_A}{name}")
            if colour is None:
                return None
            exact = colour.find(f"{_A}srgbClr")
            system = colour.find(f"{_A}sysClr")
            if exact is not None:
                return str(exact.get("val")).upper()
            if system is not None and system.get("lastClr"):
                return str(system.get("lastClr")).upper()
    return None


_COLOUR_MAP = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}
"""Word's usual mapping of background/text colours onto the theme's light/dark ones."""


def _vml_text_box(content: BaseOxmlElement) -> _TextBox | None:
    """An old-style box (v:rect, v:shape with v:textbox) at a place of its own; None when it
    sits in the line of text."""
    holder = content.getparent()
    shape = holder.getparent() if holder is not None and holder.tag == f"{_V}textbox" else None
    if shape is None or shape.tag not in _VML_BOXES:
        return None
    placement = _vml_placement(shape)
    if placement is None:
        return None
    size = dict(_VML_SIZE.findall(shape.get("style") or ""))
    width, height = (_vml_length_pt(size.get(axis)) * _MM_PER_PT for axis in ("width", "height"))
    if not width or not height:
        return None
    return _TextBox(content, shape, placement, round(width, 2), round(height, 2))


_VML_BOXES = frozenset(f"{_V}{kind}" for kind in ("rect", "shape", "roundrect", "oval"))


def _framed(shape: BaseOxmlElement) -> bool:
    """Whether the box has a visible outline (a:ln without a:noFill; VML: not stroked='f')."""
    if shape.tag in _VML_BOXES:
        return (shape.get("stroked") or "t").lower() not in ("f", "false")
    line = shape.find(f"{_WPS}spPr/{_A}ln")
    return line is not None and line.find(f"{_A}noFill") is None


def _box_padding(shape: BaseOxmlElement) -> CellPadding:
    if shape.tag in _VML_BOXES:  # v:textbox inset="left,top,right,bottom", Word's defaults
        box = shape.find(f"{_V}textbox")
        given = (box.get("inset") if box is not None else None) or ""
        sides = [part.strip() for part in given.split(",")] + [""] * 4
        defaults = ("0.1in", "0.05in", "0.1in", "0.05in")
        mm = [
            round(_vml_length_pt(side or default) * _MM_PER_PT, 2)
            for side, default in zip(sides[:4], defaults, strict=True)
        ]
        return CellPadding(left_mm=mm[0], top_mm=mm[1], right_mm=mm[2], bottom_mm=mm[3])
    body = shape.find(f"{_WPS}bodyPr")
    emu = {
        name: _num(body.get(name)) if body is not None and body.get(name) else default
        for name, default in _INSETS_EMU.items()
    }
    return CellPadding(
        left_mm=round(emu["lIns"] / _EMU_PER_MM, 2),
        top_mm=round(emu["tIns"] / _EMU_PER_MM, 2),
        right_mm=round(emu["rIns"] / _EMU_PER_MM, 2),
        bottom_mm=round(emu["bIns"] / _EMU_PER_MM, 2),
    )


def _placement(drawing: BaseOxmlElement) -> ImagePlacement | None:
    """Where an anchored (floating) picture stands; None for a picture in the line of text."""
    anchor = drawing.find(f"{_WP}anchor")
    if anchor is None:
        return None
    values: dict[str, object] = {"behind_text": anchor.get("behindDoc") in ("1", "true")}
    for axis, name in (("horizontal", "positionH"), ("vertical", "positionV")):
        position = anchor.find(f"{_WP}{name}")
        if position is None:
            continue
        values[f"{axis}_from"] = position.get("relativeFrom")
        offset, align = position.find(f"{_WP}posOffset"), position.find(f"{_WP}align")
        key = "x" if axis == "horizontal" else "y"
        if offset is not None and offset.text:
            values[f"{key}_mm"] = round(_num(offset.text) / _EMU_PER_MM, 2)
        elif align is not None and align.text:
            values[f"{key}_align"] = align.text
    wrap = next(
        (child.tag.split("}")[1] for child in anchor if child.tag.split("}")[1].startswith("wrap")),
        "wrapNone",
    )
    values["wrap"] = _WRAPS.get(wrap, "square")
    values["distances_emu"] = tuple(
        _num(anchor.get(k) or 0) for k in ("distT", "distB", "distL", "distR")
    )
    try:
        return ImagePlacement.model_validate(values)
    except ValueError:  # a position kind we do not keep: leave the picture in the line
        return None


class _Flow:
    """Walks the body in reading order and turns it into blocks.

    Empty paragraphs are held back until the next block shows how much of the gap the
    neighbours already make.
    """

    def __init__(self, importer: DocxImporter, numbering: _Numbering, prefix: str = "b") -> None:
        self._importer = importer
        self._numbering = numbering
        self._prefix = prefix
        self._blocks: list[Block] = []
        self._empty: list[Paragraph] = []
        self._above: Paragraph | None = None  # the last paragraph with text; None after a table
        self._seen_heading = False
        self._breaks: set[int] = set()
        self._column_breaks: set[int] = set()
        self._last_paragraph: tuple[int, Paragraph] | None = None
        self._last_empty: tuple[int, Paragraph] | None = None
        """The last empty paragraph of the latest gap: the neighbour of what follows it."""
        self._table_end: tuple[int, BaseOxmlElement | None] | None = None
        """The latest table's block and its last line: the neighbour of the line after it."""
        self._sections: dict[int, SectionStart] = {}

    def add_table(self, table: Table) -> None:
        self._flush_spacing()
        self._above = None
        with self._importer._formatting.inside(table):
            block = self._importer._table(table, self._next_id())
        if block is not None:
            lines = list(table._tbl.iter(qn("w:p")))
            previous = self._last_paragraph
            if lines and previous is not None and previous[0] == len(self._blocks) - 1:
                self._no_space_after(previous[1], lines[0])
            elif (
                lines
                and self._last_empty is not None
                and self._last_empty[0] == len(self._blocks) - 1
            ):
                self._no_space_after_empty(self._last_empty[1], lines[0])
            self._blocks.append(block)
            self._table_end = (len(self._blocks) - 1, lines[-1] if lines else None)

    def add_paragraph(self, paragraph: Paragraph, *, break_after_floating: bool = False) -> None:
        pictures = _pictures(paragraph)
        floating = [p for p in pictures if p.floating is not None]
        if floating:  # they take no room: placed where their paragraph starts
            self._flush_spacing(paragraph)
            clear = _clears_floats(paragraph)
            for index, picture in enumerate(floating, start=1):
                self._append_image(paragraph, picture, clear=clear and index == len(floating))
            pictures = [p for p in pictures if p.floating is None]
        if break_after_floating:  # the text after the break starts the next page
            self.page_break()
        if pictures and not paragraph.text.strip():
            self._flush_spacing(paragraph)
            self._above = paragraph
            leads = _leads(paragraph)
            if len(leads) != len(pictures):  # mixed kinds of pictures: no reliable order
                leads = [""] * len(pictures)
            previous, above, start = self._last_paragraph, self._last_flowing(), len(self._blocks)
            for index, (picture, lead) in enumerate(zip(pictures, leads, strict=True)):
                self._append_image(paragraph, picture, same_line=index > 0, lead=lead)
            if len(self._blocks) > start:  # a line of pictures: a paragraph to its neighbours
                if previous is not None and previous[0] == above:
                    first = self._blocks[start]
                    first = self._contextual_spacing(previous[1], paragraph, first, above)
                    self._blocks[start] = first
                self._last_paragraph = (len(self._blocks) - 1, paragraph)
            return
        if _frame(paragraph) is not None:  # at a fixed place: no room in the flow
            self._flush_spacing(paragraph)  # the empty lines before it stay before it
            framed = self._importer._framed(paragraph, self._next_id())
            look = framed.layout
            shown = framed.runs or (look is not None and (look.borders or look.shading))
            if shown or _shares_frame(paragraph):  # an empty line of a frame of several lines
                self._blocks.append(framed)  # takes room in it; alone, it shows nothing
            return
        inline = any(_inline_vml(p) is not None for p in paragraph._p.iter(qn("w:pict")))
        if not paragraph.text.strip() and not _has_equation(paragraph) and not inline:
            self._empty.append(paragraph)
            return
        self._flush_spacing(paragraph)
        self._above = paragraph
        self._append_paragraph(paragraph)

    def add_shape(self, shape: _Shape) -> None:
        """It takes no room either: placed where its paragraph starts."""
        self._flush_spacing()  # after the empty lines above its paragraph, as in the original
        self._blocks.append(
            ShapeBlock(
                id=self._next_id(),
                geometry=shape.geometry,
                width_mm=shape.width_mm,
                height_mm=shape.height_mm,
                floating=shape.placement,
                flip_h=shape.flip_h,
                flip_v=shape.flip_v,
                line_pt=shape.line_pt,
                color=shape.color,
                head=shape.head,
                tail=shape.tail,
                fill=shape.fill,
                path=shape.path,
                vml=shape.vml,
            )
        )

    def add_text_box(self, box: _TextBox) -> None:
        """It takes no room: placed where its paragraph starts, like a floating picture."""
        self._flush_spacing()
        block_id = self._next_id()
        source = self._importer._source.part
        blocks = self._importer._blocks(  # its empty last lines count when it centres its text
            _flow(box.content, source), self._numbering, f"{block_id}.", keep_trailing_gap=True
        )
        self._blocks.append(
            TextBoxBlock(
                id=block_id,
                blocks=tuple(blocks),
                width_mm=box.width_mm,
                height_mm=box.height_mm,
                floating=box.placement,
                framed=_framed(box.shape),
                padding=_box_padding(box.shape),
                **_box_look(box.shape, self._importer._source),
            )
        )

    def page_break(self) -> None:
        """The next block starts a new page."""
        self._flush_spacing()
        self._above = None
        self._breaks.add(len(self._blocks))

    def column_break(self) -> None:
        """The next block starts the next column."""
        self._flush_spacing()
        self._above = None
        self._column_breaks.add(len(self._blocks))

    def section(self, start: SectionStart) -> None:
        """The next block starts a new section."""
        self._flush_spacing()
        self._above = None
        self._sections[len(self._blocks)] = start

    def finish(self, *, keep_trailing_gap: bool = False) -> list[Block]:
        """keep_trailing_gap: empty lines at the end still take room (in a header)."""
        closing = len(self._blocks) in self._sections and any(
            start.columns > 1 for start in self._sections.values()
        )  # a last section after text in columns: Word balances the columns before it
        if keep_trailing_gap or closing:
            self._flush_spacing()
        for index in self._column_breaks:
            if index < len(self._blocks):
                block = self._blocks[index]
                self._blocks[index] = block.model_copy(update={"column_break_before": True})
        for index in sorted(self._breaks):
            if 0 < index < len(self._blocks):
                block = self._blocks[index]
                self._blocks[index] = block.model_copy(update={"page_break_before": True})
        for index, start in self._sections.items():
            if 0 < index < len(self._blocks):
                block = self._blocks[index]
                self._blocks[index] = block.model_copy(update={"section": start})
        return self._blocks

    def _next_id(self) -> str:
        return f"{self._prefix}{len(self._blocks) + 1}"

    def _append_paragraph(self, paragraph: Paragraph) -> None:
        block = self._importer._paragraph(
            paragraph, self._numbering, self._next_id(), self._seen_heading
        )
        self._seen_heading = self._seen_heading or isinstance(block, HeadingBlock)
        previous, above = self._last_paragraph, self._last_flowing()
        if previous is not None and previous[0] == above:
            block = self._contextual_spacing(previous[1], paragraph, block, above)
        elif self._last_empty is not None and self._last_empty[0] == above:
            block = self._contextual_spacing(self._last_empty[1], paragraph, block, above)
        elif self._table_end is not None and self._table_end[0] == len(self._blocks) - 1:
            last_line = self._table_end[1]  # the table's last line is the neighbour above
            layout = getattr(block, "layout", None)
            if (
                last_line is not None
                and layout is not None
                and _style_of(last_line) == _style_id(paragraph)
                and self._importer._formatting.contextual(paragraph)
            ):
                update = {"layout": layout.model_copy(update={"space_before_pt": 0.0})}
                block = block.model_copy(update=update)
        self._blocks.append(block)
        self._last_paragraph = (len(self._blocks) - 1, paragraph)

    def _no_space_after(self, before: Paragraph, first_line: BaseOxmlElement) -> None:
        """A line just before a table loses its 'after' to the table's first line of its style,
        as between two paragraphs (measured in Word)."""
        last = self._blocks[-1]
        layout = getattr(last, "layout", None)
        same = _style_of(first_line) == _style_id(before)
        if same and layout is not None and self._importer._formatting.contextual(before):
            update = {"layout": layout.model_copy(update={"space_after_pt": 0.0})}
            self._blocks[-1] = last.model_copy(update=update)

    def _last_flowing(self) -> int:
        """Index of the last block that takes room: a shape floating between two paragraphs
        does not part them."""
        index = len(self._blocks) - 1
        while index >= 0 and isinstance(self._blocks[index], ShapeBlock):
            index -= 1
        return index

    def _no_space_after_empty(self, before: Paragraph, first_line: BaseOxmlElement) -> None:
        """As _no_space_after, for an empty line just before the table (b5f6f7e4)."""
        spacer = self._blocks[-1]
        if not isinstance(spacer, SpacerBlock) or not spacer.lines:
            return
        if _style_of(first_line) != _style_id(before):
            return
        if not self._importer._formatting.contextual(before):
            return
        last = spacer.lines[-1]
        after = last.layout.space_after_pt or 0.0
        line = last.model_copy(
            update={"layout": last.layout.model_copy(update={"space_after_pt": 0.0})}
        )
        height = spacer.height_pt - after if spacer.height_pt is not None else None
        self._blocks[-1] = spacer.model_copy(
            update={"lines": (*spacer.lines[:-1], line), "height_pt": height}
        )

    def _contextual_spacing(
        self, before: Paragraph, paragraph: Paragraph, block: Block, above: int
    ) -> Block:
        """'Don't add space between paragraphs of the same style': Word drops the spacing on
        the side of a paragraph that asks so, when its neighbour (block `above`) has its style."""
        formatting = self._importer._formatting
        if _style_id(before) != _style_id(paragraph):
            return block
        last = self._blocks[above]
        last_layout = getattr(last, "layout", None)
        if formatting.contextual(before) and last_layout is not None:
            self._blocks[above] = last.model_copy(
                update={"layout": last_layout.model_copy(update={"space_after_pt": 0.0})}
            )
        layout = getattr(block, "layout", None)
        if formatting.contextual(paragraph) and layout is not None:
            block = block.model_copy(
                update={"layout": layout.model_copy(update={"space_before_pt": 0.0})}
            )
        return block

    def _append_image(
        self,
        paragraph: Paragraph,
        picture: _Picture,
        *,
        same_line: bool = False,
        lead: str = "",
        clear: bool = False,
    ) -> None:
        part = paragraph.part.related_parts.get(picture.rel_id)
        if part is None:  # a linked, not embedded, picture: nothing to show
            return
        block_id = self._next_id()
        self._importer.images[block_id] = part.blob
        formatting = self._importer._formatting
        self._blocks.append(
            ImageBlock(
                id=block_id,
                width_mm=picture.width_mm,
                height_mm=picture.height_mm,
                align=formatting.alignment(paragraph),
                layout=formatting.layout(paragraph, formatting.mark_size(paragraph)),
                floating=picture.floating,
                crop=picture.crop,
                effect_emu=picture.effect,
                same_line=same_line,
                lead=lead,
                clear=clear,
            )
        )

    def _flush_spacing(self, following: Paragraph | None = None) -> None:
        if self._empty:  # leading empty paragraphs also push the content down
            formatting = self._importer._formatting
            height = formatting.gap_pt(self._above, self._empty, following)
            above, last = self._above, self._last_paragraph
            if (
                above is not None
                and last is not None
                and last[0] == len(self._blocks) - 1
                and last[1] is above
                and formatting.contextual(above)
                and formatting.same_style_spacing(above, self._empty[0])
            ):
                block = self._blocks[-1]
                layout = getattr(block, "layout", None)
                if layout is not None:  # no space between it and the empty lines of its style
                    self._blocks[-1] = block.model_copy(
                        update={"layout": layout.model_copy(update={"space_after_pt": 0.0})}
                    )
            self._blocks.append(
                SpacerBlock(
                    id=self._next_id(),
                    size=_spacer_size(len(self._empty)),
                    height_pt=round(height, 1),
                    lines=self._empty_lines(following),
                )
            )
            self._last_empty = (len(self._blocks) - 1, self._empty[-1])
        self._empty.clear()

    def _empty_lines(self, following: Paragraph | None) -> tuple[EmptyLine, ...]:
        """The held-back empty paragraphs as they are; between paragraphs of one style that ask
        for it, Word drops the spacing ('contextual'), so it is dropped here too."""
        formatting = self._importer._formatting
        around = [self._above, *self._empty, following]
        lines = []
        for index, paragraph in enumerate(self._empty, start=1):
            size = formatting.mark_size(paragraph)
            layout = formatting.layout(paragraph, size)
            if formatting.contextual(paragraph):
                before, after = around[index - 1], around[index + 1]
                if before is not None and formatting.same_style_spacing(before, paragraph):
                    layout = layout.model_copy(update={"space_before_pt": 0.0})
                if after is not None and formatting.same_style_spacing(paragraph, after):
                    layout = layout.model_copy(update={"space_after_pt": 0.0})
            lines.append(
                EmptyLine(
                    layout=layout,
                    size_pt=size,
                    font=formatting.mark_font(paragraph),
                    breaks=_line_breaks(paragraph),
                    clear=_clear_of(paragraph._p, paragraph),
                )
            )
        return tuple(lines)


_SYMBOLS = {
    "F0A8": "☐",
    "F06F": "☐",
    "F071": "☐",
    "F0FE": "☒",
    "F078": "☒",
    "F0FC": "✓",
    "F0FB": "✗",
    "F0B7": "•",
    "F0A7": "▪",
    "F0D8": "➢",
    "F076": "❖",
    "F02D": "−",
}
"""Wingdings/Symbol characters that forms use as check boxes, ticks and bullets."""


_SYMBOL_FONT_CODES = range(0xF000, 0xF100)
"""Where Word keeps the characters of Symbol and Wingdings."""


def _readable(sign: str) -> str:
    """A sign typed in Symbol or Wingdings as the character it shows."""
    return "".join(
        _SYMBOLS.get(f"{ord(char):04X}", "•") if ord(char) in _SYMBOL_FONT_CODES else char
        for char in sign
    )


def _cached_style(part: Any, style_id: str | None, kind: WD_STYLE_TYPE) -> Any:
    """The style python-docx would give, kept per part: it scans every style for the default
    one on each `.style` read, half the time of an import."""
    cache: dict[tuple[str | None, WD_STYLE_TYPE], Any] = part.__dict__.setdefault("_f2w_styles", {})
    key = (style_id, kind)
    if key not in cache:
        cache[key] = part.get_style(style_id, kind)
    return cache[key]


def _run_style(run: DocxRun) -> CharacterStyle:
    return cast(CharacterStyle, _cached_style(run.part, run._r.style, WD_STYLE_TYPE.CHARACTER))


def _paragraph_style(paragraph: Paragraph) -> ParagraphStyle:
    return cast(
        ParagraphStyle, _cached_style(paragraph.part, paragraph._p.style, WD_STYLE_TYPE.PARAGRAPH)
    )


def _run_text(run: DocxRun) -> str:
    """The run's text as python-docx reads it, plus symbol characters (w:sym) it skips."""
    if run._r.find(qn("w:sym")) is None:
        return str(run.text)
    parts: list[str] = []
    for child in run._r:
        if child.tag == qn("w:sym"):
            code = (child.get(qn("w:char")) or "").upper()
            parts.append(_SYMBOLS.get(code, "□"))
        elif child.tag == qn("w:t"):
            parts.append(child.text or "")
        elif child.tag == qn("w:tab"):
            parts.append("\t")
        elif child.tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
    return "".join(parts)


def _without_space_before(block: Block) -> Block:
    if isinstance(block, SpacerBlock) and block.lines:  # empty lines: the first one's
        first = block.lines[0]
        above = first.layout.space_before_pt or 0.0
        line = first.model_copy(
            update={"layout": first.layout.model_copy(update={"space_before_pt": 0.0})}
        )
        height = block.height_pt - above if block.height_pt is not None else None
        return block.model_copy(update={"lines": (line, *block.lines[1:]), "height_pt": height})
    layout = getattr(block, "layout", None)
    if not isinstance(layout, ParagraphLayout):
        return block
    return block.model_copy(update={"layout": layout.model_copy(update={"space_before_pt": 0.0})})


def _orientation(section: Section) -> Orientation:
    geometry = _geometry(section)
    landscape = geometry is not None and geometry.width_mm > geometry.height_mm
    return Orientation.LANDSCAPE if landscape else Orientation.PORTRAIT


def _geometry(section: Section) -> PageGeometry | None:
    return _sect_geometry(section._sectPr)


def _sect_geometry(sect_pr: BaseOxmlElement) -> PageGeometry | None:
    """Page size and margins read from w:pgSz/w:pgMar directly: some editors write fractional
    twips ('11905.51'), which python-docx cannot parse."""
    size, margins = sect_pr.find(qn("w:pgSz")), sect_pr.find(qn("w:pgMar"))
    if size is None or margins is None:
        return None
    values = [
        element.get(qn(f"w:{name}"))
        for element, name in (
            (size, "w"),
            (size, "h"),
            (margins, "top"),
            (margins, "bottom"),
            (margins, "left"),
            (margins, "right"),
        )
    ]
    if any(v is None for v in values):
        return None
    width, height, top, bottom, left, right = (
        round(abs(float(v or 0)) / _TWIPS_PER_MM, 2) for v in values
    )
    distances = (margins.get(qn("w:header")), margins.get(qn("w:footer")))
    header, footer = (
        round(abs(float(v)) / _TWIPS_PER_MM, 2) if v is not None else None for v in distances
    )
    frame = sect_pr.find(qn("w:pgBorders"))
    numbering = sect_pr.find(qn("w:pgNumType"))
    if numbering is not None and numbering.get(qn("w:start")) is None:
        numbering = None
    lines = _edge_lines(frame) if frame is not None else {}
    grid = sect_pr.find(qn("w:docGrid"))
    if grid is not None and grid.get(qn("w:type")) not in _GRID_TYPES:
        grid = None  # no grid: lines as their text makes them
    return PageGeometry(
        width_mm=width,
        height_mm=height,
        top_mm=top,
        bottom_mm=bottom,
        left_mm=left,
        right_mm=right,
        header_mm=header,
        footer_mm=footer,
        borders=tuple((side, line) for side, line in lines.items() if line is not None),
        borders_from_text=frame is not None and frame.get(qn("w:offsetFrom")) == "text",
        number_start=_num(numbering.get(qn("w:start"))) if numbering is not None else None,
        gutter_mm=round(abs(float(margins.get(qn("w:gutter")) or 0)) / _TWIPS_PER_MM, 2),
        exact=(float(values[2] or 0) < 0, float(values[3] or 0) < 0),
        doc_grid=tuple((etree.QName(k).localname, str(v)) for k, v in grid.attrib.items())
        if grid is not None
        else None,
    )


_GRID_TYPES = ("lines", "linesAndChars", "snapToChars")


def _spacer_size(empty_paragraphs: int) -> SpacerSize:
    """One empty paragraph is a small gap, two a medium one, three or more a large one."""
    sizes = (SpacerSize.SMALL, SpacerSize.MEDIUM, SpacerSize.LARGE)
    return sizes[min(empty_paragraphs, len(sizes)) - 1]


def _cut_prefix(runs: tuple[Run, ...], length: int) -> tuple[Run, ...]:
    out: list[Run] = []
    remaining = length
    for run in runs:
        if remaining >= len(run.text):
            remaining -= len(run.text)
            continue
        out.append(run.model_copy(update={"text": run.text[remaining:]}))
        remaining = 0
    return tuple(out)
