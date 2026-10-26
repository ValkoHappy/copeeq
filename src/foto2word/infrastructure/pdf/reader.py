"""A digital PDF read by code, without a model: every character with its place, typeface and size
is in the file, so lines, paragraphs, indents and spacing are measured, not guessed.

What Word does when it lays text out is undone here: a line ends where the next word no longer
fits (else the paragraph ended), a paragraph's lines share their left edge but the first, a
justified line reaches the right edge. Lines drawn on the page that cross make tables (see
tables.py), the text inside each cell is read the same way; the other lines stay lines. The same
reading will later serve photos, whose characters a reader of the picture provides instead.
"""

import ctypes
import re
from dataclasses import dataclass, replace
from io import BytesIO
from itertools import pairwise

import pypdfium2
import pypdfium2.raw as pdfium

from foto2word.domain.document import (
    Alignment,
    Block,
    CellBorders,
    CellPadding,
    Document,
    DocumentTypeGuess,
    ImageBlock,
    ImagePlacement,
    Orientation,
    PageGeometry,
    ParagraphBlock,
    ParagraphLayout,
    Run,
    ShapeBlock,
    SpacerBlock,
    TableBlock,
    TableCell,
    TableRow,
    TabStop,
    VerticalAlignment,
)
from foto2word.infrastructure.pdf.tables import Grid, GridCell, Rule, find_grids

_PT_PER_MM = 72 / 25.4
_SAME_LINE = 0.35
"""Characters whose baselines are closer than this share of their size are on one line."""
_TAB_GAP = 2.5
"""A gap wider than this many font sizes inside a line is a tab, not a space."""
_EDGE = 1.5
"""Points of play when two edges count as the same."""
_ASCENT = 0.78
"""Where the baseline sits in a line, as a share of the line's height (Times, Arial)."""
_LINE_FACTORS = {"calibri": 1.22, "cambria": 1.172, "verdana": 1.215, "tahoma": 1.207}
_LINE_FACTOR = 1.15
_ITALIC_FLAG = 0x40
_PDFIUM_HYPHEN = 0x02
"""How pdfium gives a hyphen where a word breaks at a line's end: one Word put in, or one the
word has ('Бурова-Петрова'); which, the PDF does not say."""
_SPACE = 0x20
_BOLD_WEIGHT = 600
_FACES = {
    "timesnewroman": "Times New Roman",
    "couriernew": "Courier New",
    "arialnarrow": "Arial Narrow",
    "segoeui": "Segoe UI",
}
_THIN = 3.0
"""A drawn shape thinner than this many points is a line."""
_SHORT = 2.0
_BOTTOM_PT = 14.0
"""A small bottom margin: the explicit page breaks end the pages where the PDF's do, the
margin must not end them earlier when our lines come out a little taller."""
_CELL_PAD_PT = 1.9 * _PT_PER_MM
"""Word's own space between a cell's left line and its text."""


@dataclass(slots=True)
class _Char:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    base: float
    size: float
    font: str
    bold: bool
    italic: bool
    color: str | None
    background: str | None = None
    """Colour behind the character (a highlighter mark), RRGGBB."""
    underline: bool = False
    hyphen: bool = False
    """A hyphen where a word broke at the line's end: the word goes on below."""


@dataclass(slots=True)
class _Line:
    chars: list[_Char]
    page: int

    @property
    def x0(self) -> float:
        return self.chars[0].x0

    @property
    def x1(self) -> float:
        return max(c.x1 for c in self.chars if c.text.strip()) if self.text.strip() else self.x0

    @property
    def base(self) -> float:
        return sum(c.base for c in self.chars) / len(self.chars)

    @property
    def size(self) -> float:
        sizes = [c.size for c in self.chars if c.text.strip()] or [self.chars[0].size]
        return max(set(sizes), key=sizes.count)

    @property
    def text(self) -> str:
        return "".join(c.text for c in self.chars)

    def first_word(self) -> float:
        """Width of the line's first word: whether it would have fit on the line above."""
        end = next((c.x1 for c in self.chars[1:] if c.text.isspace()), None)
        word = [c for c in self.chars if end is None or c.x1 <= end]
        return max(c.x1 for c in word) - self.x0 if word else 0.0


@dataclass(slots=True)
class _Text:
    """Lines of one paragraph, and where its last line ends below."""

    lines: list[_Line]

    @property
    def top(self) -> float:
        return self.lines[0].base - _ASCENT * _height(self.lines)

    @property
    def bottom(self) -> float:
        return self.lines[-1].base + (1 - _ASCENT) * _height(self.lines)


@dataclass(frozen=True, slots=True)
class PdfReading:
    document: Document
    images: dict[str, bytes]
    """Pixels of the pictures by the id of their ImageBlock (RenderExtras.images)."""


@dataclass(slots=True)
class PageContent:
    """What a page holds, wherever it was read from: a PDF's own text and drawing, or a picture
    of the page read by OCR and by its ink. Points from the page's top left corner."""

    width: float
    height: float
    chars: list[_Char]
    rules: list[Rule]
    pictures: list[ImageBlock]


def read_pdf(pdf: bytes) -> PdfReading:
    """The document a digital PDF shows, as our model: pages, paragraphs, tables, their runs and
    layout, the other lines drawn on each page (rules, lines to fill in) and the pictures, where
    they are."""
    source = pypdfium2.PdfDocument(pdf)
    images: dict[str, bytes] = {}
    pages = []
    try:
        for number in range(len(source)):
            page = source[number]
            width, height = page.get_size()
            pages.append(
                PageContent(
                    width,
                    height,
                    _page_chars(page),
                    _merged(_page_rules(page)),
                    _page_pictures(page, number + 1, images),
                )
            )
    finally:
        source.close()
    return PdfReading(assemble(pages), images)


def assemble(contents: list[PageContent]) -> Document:
    """The document the pages' characters, lines and pictures make (see the module's notes)."""
    width, height = (contents[0].width, contents[0].height) if contents else (595.0, 842.0)
    pages = []
    for number, content in enumerate(contents, start=1):
        grids = find_grids(content.rules)
        used = {id(rule) for grid in grids for rule in grid.rules}
        loose = [rule for rule in content.rules if id(rule) not in used]
        rules = [rule for rule in loose if not _underlines(rule, content.chars)]
        pages.append((number, content.chars, [*rules, *(r for g in grids for r in g.rules)], grids))
    body_lines = {
        number: _lines([c for c in chars if not any(_inside(c, g) for g in grids)], number)
        for number, chars, _, grids in pages
    }
    every = [line for lines in body_lines.values() for line in lines if line.text.strip()]
    if not every and not any(grids for _, _, _, grids in pages):
        return _document(width, height, left=72.0, right=72.0, top=72.0, blocks=[])
    edges = [line.x0 for line in every] + [g.x0 for *_, grids in pages for g in grids]
    left = min(edges)
    widest = max([line.x1 for line in every] + [g.x1 for *_, grids in pages for g in grids])
    right = _right_edge(body_lines, left, widest)
    for number, chars, _, grids in pages:  # columns side by side: invisible tables
        found = _column_grids(body_lines[number], left, right)
        if found:
            grids.extend(found)
            body_lines[number] = _lines(
                [c for c in chars if not any(_inside(c, g) for g in grids)], number
            )
    tops = [t.top for t in _paragraphs(body_lines.get(1, []), left, right)] + [
        g.y0 for *_, grids in pages[:1] for g in grids
    ]
    top = min(tops) if tops else 72.0
    blocks: list[Block] = []
    for (number, chars, rules, grids), content in zip(pages, contents, strict=True):
        blocks += _page_blocks(
            number,
            chars,
            rules,
            grids,
            body_lines[number],
            left=left,
            right=right,
            top=top,
            pictures=content.pictures,
        )
    return _document(width, height, left=left, right=width - right, top=top, blocks=blocks)


def _document(
    width: float, height: float, *, left: float, right: float, top: float, blocks: list[Block]
) -> Document:
    return Document(
        document_type=DocumentTypeGuess(id="other", title="", confidence=0.0),
        orientation=Orientation.LANDSCAPE if width > height else Orientation.PORTRAIT,
        page=PageGeometry(
            width_mm=round(width / _PT_PER_MM, 2),
            height_mm=round(height / _PT_PER_MM, 2),
            top_mm=round(max(top, 0.0) / _PT_PER_MM, 2),
            bottom_mm=round(_BOTTOM_PT / _PT_PER_MM, 2),
            left_mm=round(left / _PT_PER_MM, 2),
            right_mm=round(max(right, 0.0) / _PT_PER_MM, 2),
        ),
        blocks=tuple(blocks),
    )


def _page_blocks(
    number: int,
    chars: list[_Char],
    rules: list[Rule],
    grids: list[Grid],
    lines: list[_Line],
    *,
    left: float,
    right: float,
    top: float,
    pictures: list[ImageBlock],
) -> list[Block]:
    """The page's paragraphs and tables from top to bottom, each placed below the one before,
    then the page's pictures and other drawn lines where they stand on it."""
    items: list[_Text | Grid] = [*_paragraphs(lines, left, right), *grids]
    items.sort(key=lambda item: item.top if isinstance(item, _Text) else item.y0)
    blocks: list[Block] = []
    above = top
    for item in items:
        if isinstance(item, _Text):
            block_id = f"p{number}-{len(blocks)}"
            blocks.append(
                _paragraph(block_id, item, above=above, left=left, right=right, page=number)
            )
            above = item.bottom
        else:
            gap = item.y0 - above
            if gap > 0.5:  # noqa: PLR2004
                blocks.append(
                    SpacerBlock(id=f"s{number}-{len(blocks)}", page=number, height_pt=round(gap, 1))
                )
            blocks.append(_table(f"t{number}-{len(blocks)}", item, chars, left, number))
            above = item.y1
    if blocks and number > 1:  # the page starts where the PDF's does
        blocks[0] = blocks[0].model_copy(update={"page_break_before": True})
    used = {id(rule) for grid in grids for rule in grid.rules}
    shapes = [
        _shape(f"r{number}-{i}", rule, number)
        for i, rule in enumerate(r for r in rules if id(r) not in used)
    ]
    return blocks[:1] + pictures + shapes + blocks[1:]


def _middle(char: _Char) -> float:
    """The height a character stands at: the middle of its line's small letters, not of its
    own ink (a comma's ink is low and would fall into the block below, 5b009ef2)."""
    return char.base - 0.3 * char.size


def _inside(char: _Char, grid: Grid) -> bool:
    x, y = (char.x0 + char.x1) / 2, _middle(char)
    return grid.x0 <= x <= grid.x1 and grid.y0 <= y <= grid.y1


_SLACK = 30.0
"""Most points the text width may reach past the longest line when nothing pins it."""


def _right_edge(pages: dict[int, list[_Line]], left: float, widest: float) -> float:
    """Where the text area ends: no line goes past it, and every line Word wrapped would have
    taken the next word had the area been wider. Justified or right-aligned lines pin it; else
    centred lines show its middle; else the middle of what the wrapping allows."""
    wrapped = []
    pinned = False
    centres = []
    for lines in pages.values():
        for text in _paragraphs(lines, left, widest):
            align = _alignment(text.lines, left, widest)
            pinned = pinned or align in (Alignment.JUSTIFY, Alignment.RIGHT)
            if align is Alignment.CENTER:
                centres += [line.x0 + line.x1 for line in text.lines]
            wrapped += [
                above.x1 + 0.3 * above.size + below.first_word()
                for above, below in pairwise(text.lines)
            ]
    if pinned:
        return widest
    limit = min([*wrapped, widest + 2 * _SLACK])
    if centres:
        centres.sort()
        return min(max(centres[len(centres) // 2] - left, widest), limit - 0.5)
    return widest + min((limit - widest) / 2, _SLACK)


# --- characters and lines ---------------------------------------------------------------------


def _page_chars(page: pypdfium2.PdfPage) -> list[_Char]:
    _, height = page.get_size()
    text = page.get_textpage()
    handle = text.raw
    chars: list[_Char] = []
    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
    ox, oy = ctypes.c_double(), ctypes.c_double()
    loose = pdfium.FS_RECTF()
    flags = ctypes.c_int()
    name = ctypes.create_string_buffer(128)
    red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
    for index in range(text.count_chars()):
        code = pdfium.FPDFText_GetUnicode(handle, index)
        if code in (0x0D, 0x0A, 0xFFFE) or (
            pdfium.FPDFText_IsGenerated(handle, index) == 1 and code != _SPACE
        ):
            continue
        pdfium.FPDFText_GetCharBox(handle, index, left, right, bottom, top)
        # across, the character's advance (its place in the line as Word set it), not its ink:
        # a '1' or a '.' is narrow ink in a full-width cell, and gaps around it are not spaces
        pdfium.FPDFText_GetLooseCharBox(handle, index, loose)
        across = (
            (loose.left, loose.right)
            if loose.right > loose.left and pdfium.FPDFText_IsGenerated(handle, index) != 1
            else (left.value, max(right.value, left.value))  # a space pdfium put in has no cell
        )
        pdfium.FPDFText_GetCharOrigin(handle, index, ox, oy)
        pdfium.FPDFText_GetFontInfo(handle, index, name, len(name), flags)
        face = name.value.decode("latin-1", "ignore")
        colour = None
        if pdfium.FPDFText_GetFillColor(handle, index, red, green, blue, alpha):
            rgb = f"{red.value:02X}{green.value:02X}{blue.value:02X}"
            colour = None if rgb == "000000" else rgb
        chars.append(
            _Char(
                text="-" if code == _PDFIUM_HYPHEN else chr(code),
                hyphen=code == _PDFIUM_HYPHEN,
                x0=across[0],
                x1=across[1],
                top=height - top.value,
                bottom=height - bottom.value,
                base=height - oy.value,
                size=round(pdfium.FPDFText_GetFontSize(handle, index) * 2) / 2,
                font=_face(face),
                bold=pdfium.FPDFText_GetFontWeight(handle, index) >= _BOLD_WEIGHT
                or "bold" in face.lower(),
                italic=bool(flags.value & _ITALIC_FLAG) or "italic" in face.lower(),
                color=colour,
            )
        )
        if pdfium.FPDFText_IsGenerated(handle, index) == 1 and len(chars) > 1:
            # a space pdfium put in has no face of its own: it is set as the letter before it
            # (its size came out as 1 pt, and words ran together)
            chars[-1] = replace(chars[-2], text=chars[-1].text, x0=chars[-1].x0, x1=chars[-1].x1)
    return chars


def _face(name: str) -> str:
    """'ABCDEF+TimesNewRomanPS-BoldMT' -> 'Times New Roman'."""
    base = re.sub(r"^[A-Z]{6}\+", "", name).split(",")[0].split("-")[0]
    base = re.sub(r"(PSMT|PS|MT)$", "", base)
    known = _FACES.get(base.lower())
    if known:
        return known
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base) or "Times New Roman"


def _lines(chars: list[_Char], page: int) -> list[_Line]:
    """Characters gathered into lines by their baseline, each in reading order."""
    rows: list[list[_Char]] = []
    for char in sorted(chars, key=lambda c: (c.base, c.x0)):
        row = rows[-1] if rows else None
        if row is not None and abs(char.base - row[0].base) <= _SAME_LINE * max(char.size, 1.0):
            row.append(char)
        else:
            rows.append([char])
    lines = []
    for row in rows:
        ordered = sorted(row, key=lambda c: c.x0)
        while ordered and ordered[0].text.isspace():
            ordered.pop(0)
        if ordered and "".join(c.text for c in ordered).strip():
            lines.append(_Line(_spaced(ordered), page))
    return lines


_WORD_GAP = 0.2
"""Letters further apart than this share of their size, with no space between, are two
words: PDFs often leave the space out where the bold part of a line meets the plain one."""


def _spaced(chars: list[_Char]) -> list[_Char]:
    out: list[_Char] = []
    for char in chars:
        before = out[-1] if out else None
        if (
            before is not None
            and not before.text.isspace()
            and not char.text.isspace()
            and _WORD_GAP * max(before.size, char.size)
            < char.x0 - before.x1
            <= _TAB_GAP * before.size  # wider: a tab, found later
        ):
            out.append(replace(before, text=" ", x0=before.x1, x1=char.x0))
        out.append(char)
    return out


def _line_height(line: _Line) -> float:
    return line.size * _LINE_FACTORS.get(line.chars[0].font.lower(), _LINE_FACTOR)


def _height(lines: list[_Line]) -> float:
    return lines[1].base - lines[0].base if len(lines) > 1 else _line_height(lines[0])


# --- paragraphs ---------------------------------------------------------------------------------


def _paragraphs(lines: list[_Line], left: float, right: float) -> list[_Text]:
    paragraphs: list[_Text] = []
    for line in lines:
        last = paragraphs[-1] if paragraphs else None
        if last is not None and _continues(last.lines, line, left, right):
            last.lines.append(line)
        else:
            paragraphs.append(_Text([line]))
    return paragraphs


def _continues(lines: list[_Line], line: _Line, left: float, right: float) -> bool:
    """Whether Word wrapped the paragraph's last line onto this one: same page, same size,
    the usual distance below, and the line above too full for this line's first word (or
    ending in a hyphen that splits a word)."""
    above = lines[-1]
    if not _same_flow(lines, line, right):
        return False
    hyphenated = _broken(above)
    room = _room(above, line, left, right)
    if not hyphenated and room >= 0.3 * above.size + line.first_word() + _EDGE:
        return False  # the word would have fit: the line above ended its paragraph
    return len(lines) == 1 or abs(line.x0 - lines[1].x0) <= _EDGE


def _broken(line: _Line) -> bool:
    """Whether the line ends in a word broken by a hyphen: the word goes on below."""
    last = next((c for c in reversed(line.chars) if not c.text.isspace()), None)
    return last is not None and last.hyphen


def _same_flow(lines: list[_Line], line: _Line, right: float) -> bool:
    """Same page, same size, no tabs, and the line spacing the paragraph keeps."""
    above = lines[-1]
    if line.page != above.page or abs(line.size - above.size) > 0.5:  # noqa: PLR2004
        return False
    if _tabbed(above, right) or _tabbed(line, right):
        return False
    pitch = line.base - above.base
    if len(lines) > 1:
        return abs(pitch - (above.base - lines[-2].base)) <= _EDGE
    return 0 < pitch <= 1.6 * _line_height(above)


def _room(above: _Line, below: _Line, left: float, right: float) -> float:
    """How much more the line above could have taken: room on its right; on its left too when
    the two lines are right-aligned (both end at the edge, starting at different places) or
    centred (sharing a middle away from both edges)."""
    room = right - above.x1
    ragged_left = abs(above.x0 - below.x0) > _EDGE
    at_right = abs(above.x1 - right) <= _EDGE
    if ragged_left and at_right and abs(below.x1 - right) <= _EDGE:
        return above.x0 - left
    if ragged_left and at_right and above.x0 > left + 3 * _EDGE and abs(below.x1 - right) > _EDGE:
        # every line of a right-aligned paragraph ends at the edge (an indented justified
        # one shares its lines' left edge instead)
        return above.x0 - left
    middle = (above.x0 + above.x1) / 2
    centred = abs(middle - (below.x0 + below.x1) / 2) <= _EDGE and above.x0 > left + 3 * _EDGE
    return room + (above.x0 - left) if ragged_left and centred else room


def _tabbed(line: _Line, right: float) -> bool:
    return any(_tab(line, a, b, right) for a, b in pairwise(line.chars))


def _tab(line: _Line, before: _Char, char: _Char, right: float) -> bool:
    """A wide gap is a tab, unless it follows a space on a line that reaches the right edge:
    then Word stretched the spaces to justify it ('и        прилагает        следующие')."""
    if char.x0 - before.x1 <= _TAB_GAP * before.size:
        return False
    return not (before.text.isspace() and abs(line.x1 - right) <= _EDGE)


def _paragraph(
    block_id: str, text: _Text, *, above: float, left: float, right: float, page: int
) -> ParagraphBlock:
    runs, align, layout = _parts(text, above, left, right)
    return ParagraphBlock(id=block_id, page=page, runs=runs, align=align, layout=layout)


def _parts(
    text: _Text, above: float, left: float, right: float
) -> tuple[tuple[Run, ...], Alignment, ParagraphLayout]:
    """Runs, alignment and layout of a paragraph whose space starts at `above` (the bottom of
    what stands before it), between the edges `left` and `right`."""
    lines = text.lines
    first = lines[0]
    align = _alignment(lines, left, right)
    body_left = min(line.x0 for line in lines[1:]) if len(lines) > 1 else first.x0
    if align in (Alignment.CENTER, Alignment.RIGHT):
        indent, first_indent = 0.0, 0.0
    else:
        indent, first_indent = body_left - left, first.x0 - body_left
    runs, tabs = _runs(lines, left, right)
    layout = ParagraphLayout(
        space_before_pt=round(max(text.top - above, 0.0), 1),
        space_after_pt=0.0,
        line_spacing=1.0,
        line_pt=round(_height(lines), 2),
        left_indent_mm=round(indent / _PT_PER_MM, 2),
        first_line_indent_mm=round(first_indent / _PT_PER_MM, 2),
        right_indent_mm=0.0,
        tabs=tabs,
    )
    return runs, align, layout


def _alignment(lines: list[_Line], left: float, right: float) -> Alignment:
    middle = (left + right) / 2
    if all(abs((line.x0 + line.x1) / 2 - middle) <= 2 * _EDGE for line in lines) and all(
        line.x0 > left + 3 * _EDGE for line in lines
    ):
        return Alignment.CENTER
    if all(abs(line.x1 - right) <= _EDGE for line in lines) and lines[0].x0 > left + 3 * _EDGE:
        return Alignment.RIGHT
    full = [abs(line.x1 - right) <= _EDGE for line in lines[:-1]]
    if any(f and _stretched(line) for f, line in zip(full, lines, strict=False)) and all(
        # a line of one long word ('город»,____') is not stretched, and spoils nothing
        reaches or " " not in line.text.strip()
        for reaches, line in zip(full, lines, strict=False)
    ):
        return Alignment.JUSTIFY
    return Alignment.LEFT


_NATURAL_SPACE = 0.33
"""Gaps between words wider than this share of the size are stretched (a space is 0.25-0.28)."""


def _stretched(line: _Line) -> bool:
    """Whether Word widened the line's spaces to reach the edge: a line that merely happens to
    be the longest one is not justified."""
    gaps = []
    for before, char in pairwise(line.chars):
        if before.text.isspace() and not char.text.isspace():
            start = next(
                (c.x1 for c in reversed(line.chars[: line.chars.index(before)]) if c.text.strip()),
                None,
            )
            if start is not None:
                gaps.append(char.x0 - start)
    return bool(gaps) and sum(gaps) / len(gaps) > _NATURAL_SPACE * line.size


def _runs(
    lines: list[_Line], left: float, right: float
) -> tuple[tuple[Run, ...], tuple[TabStop, ...]]:
    """The paragraph's text in runs of one look; a wide gap in a line is a tab to where the
    text goes on (a date at the right of 'Исх. №')."""
    runs: list[Run] = []
    tabs: list[TabStop] = []
    for number, line in enumerate(lines):
        if number and not _broken(lines[number - 1]):
            _append(runs, " ", line.chars[0])
        for position, char in enumerate(line.chars):
            if position and _tab(line, line.chars[position - 1], char, right):
                tabs.append(TabStop(position_mm=round((char.x0 - left) / _PT_PER_MM, 2)))
                _append(runs, "\t", char)
            _append(runs, char.text, char)
    return tuple(runs), tuple(tabs)


def _append(runs: list[Run], text: str, char: _Char) -> None:
    look = {
        "bold": char.bold,
        "italic": char.italic,
        "size_pt": char.size,
        "font": char.font,
        "color": char.color,
        "background": char.background,
        "underline": char.underline,
    }
    if runs and all(getattr(runs[-1], k) == v for k, v in look.items()):
        runs[-1] = runs[-1].model_copy(update={"text": runs[-1].text + text})
    else:
        runs.append(Run(text=text, **look))


_UNDER = 0.4
"""An underline lies at most this share of the size below the baseline."""
_COVERED = 0.8


def _underlines(rule: Rule, chars: list[_Char]) -> bool:
    """Whether the line underlines the characters just above it, which it then marks; a line
    that goes on well past them is a line to write on, and stays."""
    if not rule.horizontal or rule.width > 1.5:  # noqa: PLR2004 - a thick bar is a rule
        return False
    above = [
        c
        for c in chars
        if rule.x0 - 1 <= (c.x0 + c.x1) / 2 <= rule.x1 + 1
        and c.base - 0.5 <= rule.y0 <= c.base + _UNDER * c.size
    ]
    letters = [c for c in above if c.text.strip()]
    if not letters:
        return False
    covered = max(c.x1 for c in letters) - min(c.x0 for c in letters)
    if covered < _COVERED * (rule.x1 - rule.x0):
        return False
    for char in above:
        char.underline = True
    return True


_MIN_COLUMN_LINES = 2
"""A column has at least this many lines of its own beside the other one."""
_MIN_COLUMN_PT = 60.0
"""And is at least this wide: list numbers beside their items make a narrow strip."""


def _segments(line: _Line) -> list[tuple[float, float]]:
    """The line's pieces of text split at its tabs: (start, end) of each."""
    pieces: list[tuple[float, float]] = []
    start = line.chars[0].x0
    for before, char in pairwise(line.chars):
        if char.x0 - before.x1 > _TAB_GAP * before.size:
            pieces.append((start, before.x1))
            start = char.x0
    pieces.append((start, line.x1))
    return [(a, b) for a, b in pieces if b > a]


def _column_grids(lines: list[_Line], left: float, right: float) -> list[Grid]:
    """Blocks of text in two columns: a gap down the page that no line crosses, with lines of
    text on both sides of it that stand beside each other."""
    ordered = sorted(lines, key=lambda line: line.base)
    found: list[Grid] = []
    used: set[int] = set()
    candidates = sorted(
        {round((a[1] + b[0]) / 2, 1) for line in ordered for a, b in pairwise(_segments(line))}
    )
    for gutter in candidates:
        run: list[_Line] = []
        for line in [*ordered, None]:
            crosses = line is None or any(a < gutter < b for a, b in _segments(line))
            near = line is not None and (
                not run or line.base - run[-1].base <= 2.5 * _line_height(run[-1])
            )
            if line is not None and not crosses and near and id(line) not in used:
                run.append(line)
                continue
            grid = _column_grid(run, gutter, left, right)
            if grid is not None:
                found.append(grid)
                used.update(id(line) for line in run)
            run = [line] if line is not None and not crosses and id(line) not in used else []
    return found


def _column_grid(run: list[_Line], gutter: float, left: float, right: float) -> Grid | None:
    on_left = [line for line in run if line.x0 < gutter]
    on_right = [line for line in run if any(b > gutter for _, b in _segments(line))]
    if len(on_left) < _MIN_COLUMN_LINES or len(on_right) < _MIN_COLUMN_LINES:
        return None
    pieces = [piece for line in run for piece in _segments(line)]
    left_side = [piece for piece in pieces if piece[1] <= gutter]
    right_side = [piece for piece in pieces if piece[0] >= gutter]
    for side in (left_side, right_side):  # list numbers beside their items are not a column
        if not side or max(b for _, b in side) - min(a for a, _ in side) < _MIN_COLUMN_PT:
            return None
    if not any(line.x0 < gutter < line.x1 for line in run) and not _beside(on_left, on_right):
        return None
    top = min(min(c.top for c in line.chars) for line in run) - 1.0
    bottom = max(max(c.bottom for c in line.chars) for line in run) + 1.0
    hidden = CellBorders(top=False, bottom=False, left=False, right=False)
    x0, x1 = min(left, *(line.x0 for line in run)), max(right, *(line.x1 for line in run))
    cells = [
        GridCell(0, 0, 1, 1, x0, top, gutter, bottom, hidden),
        GridCell(0, 1, 1, 1, gutter, top, x1, bottom, hidden),
    ]
    return Grid(xs=[x0, gutter, x1], ys=[top, bottom], cells=cells)


def _beside(on_left: list[_Line], on_right: list[_Line]) -> bool:
    """Whether some line of one column stands at the height of a line of the other."""
    return any(
        abs(a.base - b.base) < _line_height(a) for a in on_left for b in on_right if a is not b
    )


# --- tables -------------------------------------------------------------------------------------


def _table(block_id: str, grid: Grid, chars: list[_Char], left: float, page: int) -> TableBlock:
    rows: list[list[TableCell]] = [[] for _ in range(len(grid.ys) - 1)]
    found = {
        id(cell): [
            c
            for c in chars
            if cell.x0 <= (c.x0 + c.x1) / 2 < cell.x1 and cell.y0 <= _middle(c) < cell.y1
        ]
        for cell in grid.cells
    }
    pad = _padding(grid, found)
    for cell in grid.cells:
        inside = found[id(cell)]
        longest = max((c.x1 for c in inside if c.text.strip()), default=cell.x0)
        # the text reaches at least as far as its longest line: Word wrapped nothing earlier
        text_left, text_right = cell.x0 + pad, max(cell.x1 - pad, min(longest + 0.5, cell.x1))
        paragraphs = _paragraphs(_lines(inside, page), text_left, text_right)
        runs: list[Run] = []
        layouts: list[ParagraphLayout] = []
        aligns: list[Alignment] = []
        above = cell.y0
        for paragraph in paragraphs:
            if runs:
                runs.append(Run(text="\n", size_pt=paragraph.lines[0].size))
            part_runs, align, layout = _parts(paragraph, above, text_left, text_right)
            runs += part_runs
            layouts.append(layout)
            aligns.append(align)
            above = paragraph.bottom
        rows[cell.row].append(
            TableCell(
                runs=tuple(runs),
                col_span=cell.col_span,
                row_span=cell.row_span,
                borders=cell.borders,
                v_align=VerticalAlignment.TOP,
                layout=layouts[0] if layouts else None,
                line_layouts=tuple(layouts) if len(layouts) > 1 else (),
                line_aligns=tuple(aligns) if len(aligns) > 1 else (),
                align=aligns[0] if aligns else None,
                size_pt=paragraphs[0].lines[0].size if paragraphs else 1.0,
                hide_mark=not paragraphs,
                padding=CellPadding(
                    top_mm=0.0,
                    bottom_mm=0.0,
                    left_mm=round(pad / _PT_PER_MM, 2),
                    right_mm=round((cell.x1 - text_right) / _PT_PER_MM, 2),
                )
                if text_right > cell.x1 - pad
                else None,
            )
        )
    widths = [b - a for a, b in pairwise(grid.xs)]
    return TableBlock(
        id=block_id,
        page=page,
        rows=tuple(
            TableRow(cells=tuple(cells), height_mm=round((b - a) / _PT_PER_MM, 2))
            for cells, (a, b) in zip(rows, pairwise(grid.ys), strict=True)
        ),
        column_widths=tuple(round(w / _PT_PER_MM, 2) for w in widths),
        width_mm=round(sum(widths) / _PT_PER_MM, 2),
        indent_mm=round((grid.x0 - left) / _PT_PER_MM, 2),
        padding=CellPadding(
            top_mm=0.0,
            bottom_mm=0.0,
            left_mm=round(pad / _PT_PER_MM, 2),
            right_mm=round(pad / _PT_PER_MM, 2),
        ),
    )


def _padding(grid: Grid, found: dict[int, list[_Char]]) -> float:
    """The space between a cell's left line and its text, as the table's left-aligned cells
    show it (the smallest such gap): Word's 1.9 mm unless the original set its own."""
    gaps = [
        min(c.x0 for c in chars if c.text.strip()) - cell.x0
        for cell in grid.cells
        if (chars := found[id(cell)]) and any(c.text.strip() for c in chars)
    ]
    if not gaps:
        return _CELL_PAD_PT
    return max(0.0, min(*gaps, _CELL_PAD_PT))


# --- pictures -----------------------------------------------------------------------------------

_TINY = 4.0
"""Pictures smaller than this many points on a side are specks, not pictures."""


def _page_pictures(
    page: pypdfium2.PdfPage, number: int, images: dict[str, bytes]
) -> list[ImageBlock]:
    """The page's pictures as drawn (masks applied), floating behind the text at their place."""
    _, height = page.get_size()
    found = []
    for index, obj in enumerate(page.get_objects(filter=[pdfium.FPDF_PAGEOBJ_IMAGE])):
        left, bottom, right, top = obj.get_bounds()
        if right - left < _TINY or top - bottom < _TINY:
            continue
        try:
            picture = obj.get_bitmap(render=True).to_pil()
        except pypdfium2.PdfiumError:
            continue
        data = BytesIO()
        picture.save(data, format="PNG")
        block_id = f"i{number}-{index}"
        images[block_id] = data.getvalue()
        found.append(
            ImageBlock(
                id=block_id,
                page=number,
                width_mm=round((right - left) / _PT_PER_MM, 2),
                height_mm=round((top - bottom) / _PT_PER_MM, 2),
                floating=ImagePlacement(
                    horizontal_from="page",
                    x_mm=round(left / _PT_PER_MM, 2),
                    vertical_from="page",
                    y_mm=round((height - top) / _PT_PER_MM, 2),
                    wrap="none",
                    behind_text=True,
                ),
            )
        )
    return found


# --- drawn lines --------------------------------------------------------------------------------


def _page_rules(page: pypdfium2.PdfPage) -> list[Rule]:
    _, height = page.get_size()
    rules: list[Rule] = []
    width = ctypes.c_float()
    fill_mode, stroked = ctypes.c_int(), ctypes.c_int()
    red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
    for obj in page.get_objects(filter=[pdfium.FPDF_PAGEOBJ_PATH]):
        left, bottom, right, top = obj.get_bounds()
        pdfium.FPDFPath_GetDrawMode(obj.raw, fill_mode, stroked)
        if stroked.value:
            pdfium.FPDFPageObj_GetStrokeWidth(obj.raw, width)
            pdfium.FPDFPageObj_GetStrokeColor(obj.raw, red, green, blue, alpha)
        elif fill_mode.value:
            pdfium.FPDFPageObj_GetFillColor(obj.raw, red, green, blue, alpha)
        else:
            continue
        rgb = f"{red.value:02X}{green.value:02X}{blue.value:02X}"
        if rgb == "FFFFFF" or alpha.value == 0:
            continue  # unseen on a white page
        colour = None if rgb == "000000" else rgb
        w, h = right - left, top - bottom
        if stroked.value and w > _THIN and h > _THIN:
            continue  # a frame: later, as a rectangle
        if h <= _THIN and w >= _SHORT:
            y = height - (top + bottom) / 2
            thick = max(width.value, 0.25) if stroked.value else h
            rules.append(Rule(left, y, right, y, thick, colour))
        elif w <= _THIN and h >= _SHORT:
            x = (left + right) / 2
            thick = max(width.value, 0.25) if stroked.value else w
            rules.append(Rule(x, height - top, x, height - bottom, thick, colour))
    return rules


def _merged(rules: list[Rule]) -> list[Rule]:
    """Pieces of one line joined: Word draws a table's border cell by cell."""
    out: list[Rule] = []
    for rule in sorted(
        rules,
        key=lambda r: (
            r.horizontal,
            round(r.y0 if r.horizontal else r.x0, 1),
            r.x0 if r.horizontal else r.y0,
        ),
    ):
        last = out[-1] if out else None
        if (
            last is not None
            and last.horizontal == rule.horizontal
            and last.color == rule.color
            and abs(last.width - rule.width) < 0.3  # noqa: PLR2004
            and (
                (rule.horizontal and abs(last.y0 - rule.y0) < 0.3 and rule.x0 <= last.x1 + 0.5)  # noqa: PLR2004
                or (
                    not rule.horizontal
                    and abs(last.x0 - rule.x0) < 0.3  # noqa: PLR2004
                    and rule.y0 <= last.y1 + 0.5
                )
            )
        ):
            last.x1, last.y1 = max(last.x1, rule.x1), max(last.y1, rule.y1)
        else:
            out.append(rule)
    return out


def _shape(block_id: str, rule: Rule, page: int) -> ShapeBlock:
    return ShapeBlock(
        id=block_id,
        page=page,
        geometry="line",
        width_mm=round((rule.x1 - rule.x0) / _PT_PER_MM, 2),
        height_mm=round((rule.y1 - rule.y0) / _PT_PER_MM, 2),
        floating=ImagePlacement(
            horizontal_from="page",
            x_mm=round(rule.x0 / _PT_PER_MM, 2),
            vertical_from="page",
            y_mm=round(rule.y0 / _PT_PER_MM, 2),
            wrap="none",
        ),
        line_pt=round(rule.width, 2),
        color=rule.color,
    )
