"""Measuring the layout of a page photo: font size, line spacing, indents, gaps, margins.

A vision model reads text well but cannot name '12 pt' or '6 pt before'. The geometry of the
text lines on the photo can: lines are found from the ink profile of the rows, and each line is
given to the block whose bbox (from the model) holds it. Works for a flat, upright page — a scan,
a rendered page or a photo after perspective correction.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from statistics import median
from typing import cast

from PIL import Image, ImageDraw

from foto2word.domain.document import (
    Alignment,
    Block,
    BoundingBox,
    Document,
    FillRowBlock,
    HeadingBlock,
    ImageBlock,
    ImagePlacement,
    ListItemBlock,
    Orientation,
    PageGeometry,
    ParagraphBlock,
    ParagraphLayout,
    RequisitesBlock,
    SpacerBlock,
    TableBlock,
    plain_text,
)
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine, anchor
from foto2word.infrastructure.layout.metrics import FAMILIES, TextMetrics

_PT_PER_MM = 72 / 25.4
_METRICS = TextMetrics()
_INK_THRESHOLD = 150
"""Grey level below which a pixel counts as ink."""
_INK_PER_EM = 0.87
"""Ink height of a typical Cyrillic text line relative to the font size: median over the 42
ppt.ru templates (0.79–0.95 at 110 dpi)."""
_CAP_TOP = 0.68
"""Height of capitals, digits and ascenders above the baseline, in font sizes."""
_X_TOP = 0.47
"""Height of lowercase letters without ascenders ('а', 'н', 'о')."""
_DESCENT = _INK_PER_EM - _CAP_TOP
"""Depth of descenders ('р', 'у', 'д') below the baseline, so a mixed line is _INK_PER_EM."""
_ASCENDERS = set("бёйЁbdfhklt()[]{}|/")
_DESCENDERS = set("руфдцщзgjpqy()[]{}|_")
"""Brackets reach above capitals and below the baseline; '_' lies at the descender line."""
_SINGLE_LINE = {"times new roman": 1.11, "arial": 1.15, "calibri": 1.22}
"""Word's single line spacing in font sizes (ascent + descent + gap of the typeface)."""
_DEFAULT_SINGLE = 1.15
"""Single line spacing relative to the font size."""
_SIZES = (8.0, 9.0, 10.0, 10.5, 11.0, 12.0, 13.0, 14.0, 16.0, 18.0, 20.0, 24.0, 28.0)
_SAME_EDGE_MM = 2.5
_MIN_GAP_PT = 3.0
_MIN_LINE_MM = 10.0
"""Narrower ink is a speck or a mark, not a text line that shows the margin."""
_BOX_SLACK = 0.02
"""How far beyond a model's bbox to look for the block's ink, as a share of the page side."""
_MIN_RULE_PX = 48
_MIN_CELL_PX = 6
"""Shortest ink that can be a table rule: about three lines of text at phone resolution."""
_UNDERLINE_SHARE = 0.15
"""A run at most two pixels thick with this much ink along the row is an underline or
'_____', not the tails of letters."""
_SNAP_PT = 1.5
_MIN_FIT_CHARS = 8
_MIN_FIT_PT = 6.0
_MAX_FIT_SHIFT_PT = 4.0
"""A fitted size this far from the ink-height estimate is a wrong reading of the lines."""
_MAX_FIT_ERROR = 0.12
_STEP_PENALTY = 0.002
"""Among equally good fits, prefer the one closest to the ink-height estimate."""
_MAX_LINE_FIT_ERROR = 0.3
"""Per-line fits: line widths spread a little and the ink height is a point off at times."""
_OTHER_FAMILY_BIAS = 0.04
_GAP_LINES = 80
_MIN_GAP_WORDS = 3
_WORD_GAP = 0.22
"""A run of empty columns this many line heights wide separates words (letters touch closer)."""
_GUESSED = FAMILIES[:2]
"""Typefaces a block may be fitted with when the document's is unknown: Calibri only when the
whole page says so, or every short line could pick it."""
_OTHER_PRIOR = 1.115
"""A typeface other than Times has its error multiplied by this: Times is far more likely."""
_TYPEFACE_MARGIN = 1.28
"""The best typeface must have this many times less error than the next one to be named.
With the prior: Arial when its error is under 0.7 of Times', Times when Arial's is over 1.15
of it. On the 42 templates: 28 named, none wrong, 14 unknown."""
_MIN_HEIGHT_CHARS = 8
_EDGE_SHARE = 0.012
"""The band along the page's edges cleared before measuring: 2.5 mm on A4."""
_MIN_INK_CHARS = 3
"""A line needs this many letters for its ink height to tell the size."""
_MIN_FONT_VOTES = 3
_FONT_AGREEMENT = 0.7
_FALLBACK_SIZE = 12.0
_UNMEASURED = -1.0
"""Marks a size that could not be measured; replaced by the document's common size."""
_MIN_POOLED_LINES = 4
_SPLIT_GAP = 0.25
_THIN_RUN = 0.45
"""A run of ink rows this much lower than a typical one, just above or below another run, is
part of that line (the tops of 'б', 'й'); two full lines are never joined."""
_RULE_SHARE = 0.85
"""A pixel column or row that is ink almost all along is a ruling line; a dense text line
stays below it."""
_OCR_PAD_PX = 3
_TAB_GAP = 1.2
"""A gap wider than this many line heights is a tab or a run of spaces, not a word space."""
_SPACE_SHARE = 0.3
"""A word space is about this share of the line's ink height."""
_HAIRLINE_PT = 1.0
"""Height left to a spacer whose gap is already in the page margin (0 would mean 'unknown')."""


@dataclass(frozen=True, slots=True)
class _Line:
    top: int
    bottom: int
    left: int
    right: int
    text: str = ""
    """What the line says, when an OCR engine read it."""
    span: int = 0
    """Width of the text itself: the ink with tab-wide gaps counted as one space (0 = the
    whole line). A line 'Город ⟶ «12» февраля' is wider than its words."""

    @property
    def text_width(self) -> int:
        return self.span or self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True, slots=True)
class _Fit:
    size: float
    family: str
    error: float
    lines: int = 1
    """How many lines the fit explains: wraps of several lines tell the typeface, one does not."""


@dataclass(frozen=True, slots=True)
class _Page:
    ink: Image.Image
    single: float
    """Single line spacing of the document's typeface, in font sizes."""
    lines: list[_Line]
    mm_per_px: float
    width_px: int
    height_px: int
    left_px: int
    right_px: int

    def mm(self, px: float) -> float:
        return px * self.mm_per_px

    def pt(self, px: float) -> float:
        return px * self.mm_per_px * _PT_PER_MM


class ProjectionLayoutEstimator:
    """Fills sizes, spacing, indents and alignment the model left empty, from the photo."""

    def __init__(self, page_width_mm: float = 210.0, page_height_mm: float = 297.0) -> None:
        self._paper = (page_width_mm, page_height_mm)

    def estimate(
        self, document: Document, pages: Sequence[PageImage], lines: Sequence[TextLine] = ()
    ) -> Document:
        """Two passes when the typeface is unknown: wrapped paragraphs tell it, then every block
        is measured with it. OCR `lines`, when given, place the blocks instead of their bboxes."""
        if not pages:
            return document
        if document.font is None and lines:
            seen = _typeface_on_photo(
                lines, [self._page(p, document.orientation, None) for p in pages]
            )
            if seen is not None:
                return _page_breaks(
                    self._estimate(document.model_copy(update={"font": seen}), pages, lines)
                )
        first = self._estimate(document, pages, lines)
        if document.font is None and first.font is not None:
            first = self._estimate(document.model_copy(update={"font": first.font}), pages, lines)
        return _page_breaks(first)

    def _estimate(
        self, document: Document, pages: Sequence[PageImage], ocr: Sequence[TextLine]
    ) -> Document:
        measured = [self._page(page, document.orientation, document.font) for page in pages]
        blocks = list(document.blocks)
        lines_of = self._assign(blocks, measured) | _from_ocr(blocks, ocr, measured)
        fits: dict[str, _Fit] = {}
        for index, block in enumerate(blocks):
            lines = lines_of.get(block.id)
            if isinstance(block, TableBlock):
                if 0 < block.page <= len(measured):
                    page = measured[block.page - 1]
                    box = block.bbox or (_box_of(lines, page) if lines else None)
                    if box is not None:
                        blocks[index] = self._table(
                            block.model_copy(update={"bbox": box}), page, ocr, document.font
                        )
            elif lines:
                page = measured[block.page - 1]
                blocks[index] = self._measure(block, lines, page, document.font, fits)
        blocks = _snap_sizes(blocks, lines_of, measured, fits)
        blocks = self._gaps(blocks, lines_of, measured)
        blocks = _floating_pictures(blocks, lines_of, measured)
        return document.model_copy(
            update={
                "blocks": tuple(blocks),
                "page": document.page or self._geometry(measured[0]),
                "font": document.font or _typeface(fits),
            }
        )

    # ------------------------------------------------------------------ the photo

    def _page(self, page: PageImage, orientation: Orientation, font: str | None) -> _Page:
        with Image.open(BytesIO(page.data)) as source:
            ink = source.convert("L").point(lambda v: 255 if v < _INK_THRESHOLD else 0)
        width, height = ink.size
        # a flattened photo keeps a sliver of the table or the sheet's shadow at its edges; no
        # text is printed that close to the edge of the paper
        edge = max(round(width * _EDGE_SHARE), 1)
        frame = ImageDraw.Draw(ink)
        frame.rectangle((0, 0, width - 1, height - 1), outline=0, width=edge)
        paper_width = self._paper[1] if orientation is Orientation.LANDSCAPE else self._paper[0]
        lines = _lines(ink)
        text = [
            line for line in lines if (line.right - line.left) * paper_width / width >= _MIN_LINE_MM
        ]
        return _Page(
            ink=ink,
            single=_SINGLE_LINE.get((font or "").lower(), _DEFAULT_SINGLE),
            lines=lines,
            mm_per_px=paper_width / width,
            width_px=width,
            height_px=height,
            # the text margins: edges of real lines, not of specks narrower than a centimetre
            left_px=min((line.left for line in text), default=0),
            right_px=max((line.right for line in text), default=width),
        )

    def _geometry(self, page: _Page) -> PageGeometry:
        top = page.mm(page.lines[0].top) if page.lines else 20.0
        width, height = page.mm(page.width_px), page.mm(page.height_px)
        return PageGeometry(
            width_mm=round(width, 1),
            height_mm=round(height, 1),
            top_mm=round(max(top - 2.0, 5.0), 1),
            bottom_mm=20.0,
            left_mm=round(page.mm(page.left_px), 1),
            right_mm=round(width - page.mm(page.right_px), 1),
        )

    @staticmethod
    def _assign(blocks: list[Block], pages: list[_Page]) -> dict[str, list[_Line]]:
        """Each text line goes to the block whose bbox holds its middle."""
        found: dict[str, list[_Line]] = {}
        for block in blocks:
            if block.bbox is None or isinstance(block, TableBlock | SpacerBlock | ImageBlock):
                continue
            if not 0 < block.page <= len(pages):
                continue
            found[block.id] = _lines_in(pages[block.page - 1], block.bbox)
        return found

    # ------------------------------------------------------------------ one block

    def _measure(
        self,
        block: Block,
        lines: list[_Line],
        page: _Page,
        family: str | None,
        fits: dict[str, _Fit],
    ) -> Block:
        # a fill row has small captions under its lines: its size is that of the first line
        sample = lines[:1] if isinstance(block, FillRowBlock) else lines
        size = _ink_size(sample, page, block.text())
        fit = _fit_size(block, lines, page, size, family)
        if fit is not None:
            fits[block.id] = fit
            size = fit.size
        elif _mostly_blanks(block.text()):
            size = _UNMEASURED  # '______' cut together with letter tails: _snap_sizes decides
        layout = ParagraphLayout(
            space_before_pt=0.0,
            space_after_pt=0.0,
            line_spacing=self._line_spacing(lines, size, page),
            first_line_indent_mm=self._first_line_indent(lines, page),
            left_indent_mm=round(max(page.mm(min(_rest(lines)) - page.left_px), 0.0), 1),
            right_indent_mm=0.0,
        )
        update: dict[str, object] = {"layout": layout}
        if isinstance(block, RequisitesBlock):
            return block.model_copy(update=update | self._requisites(lines, page, size))
        if hasattr(block, "size_pt"):
            update["size_pt"] = getattr(block, "size_pt", None) or size
        if hasattr(block, "runs"):
            runs = getattr(block, "runs", ())
            update["runs"] = tuple(
                r if r.size_pt else r.model_copy(update={"size_pt": size}) for r in runs
            )
        if hasattr(block, "align") and getattr(block, "align", None) is None:
            update["align"] = _alignment(lines, page)
            if update["align"] is Alignment.JUSTIFY and "\n" in block.text():
                # Word stretches a justified line that ends in a manual break; originals that
                # break lines by hand are set ragged
                update["align"] = Alignment.LEFT
        if isinstance(block, FillRowBlock):
            # the row starts at its first label and ends where its last line ends; the line
            # below holds centred captions, not a paragraph indent
            left = page.mm(min(line.left for line in lines) - page.left_px)
            right = page.mm(page.right_px - max(line.right for line in lines))
            update["layout"] = layout.model_copy(
                update={
                    "left_indent_mm": round(max(left, 0.0), 1),
                    "right_indent_mm": round(max(right, 0.0), 1),
                    "first_line_indent_mm": 0.0,
                    "line_spacing": 1.0,
                }
            )
            return block.model_copy(update=update)
        align = update.get("align", getattr(block, "align", None))
        if align in (Alignment.CENTER, Alignment.RIGHT):
            update["layout"] = layout.model_copy(
                update={"left_indent_mm": 0.0, "first_line_indent_mm": 0.0}
            )
        return block.model_copy(update=update)

    @staticmethod
    def _line_spacing(lines: list[_Line], size_pt: float, page: _Page) -> float:
        if len(lines) < 2:  # noqa: PLR2004
            return 1.0
        pitch = page.pt(median(b.top - a.top for a, b in pairwise(lines)))
        return round(min(max(pitch / (size_pt * page.single), 0.8), 3.0) * 20) / 20

    @staticmethod
    def _first_line_indent(lines: list[_Line], page: _Page) -> float:
        if len(lines) < 2:  # noqa: PLR2004
            return 0.0
        shift = page.mm(lines[0].left - median(line.left for line in lines[1:]))
        return round(shift, 1) if abs(shift) > _SAME_EDGE_MM else 0.0

    @staticmethod
    def _requisites(lines: list[_Line], page: _Page, size: float) -> dict[str, object]:
        lefts = [line.left for line in lines]
        rights = [line.right for line in lines]
        flush_right = (
            page.mm(max(rights) - min(rights)) < _SAME_EDGE_MM < page.mm(max(lefts) - min(lefts))
        )
        pitch = page.pt(median(b.top - a.top for a, b in pairwise(lines))) if len(lines) > 1 else 0
        between = max(pitch - size * page.single, 0.0)  # each line is its own paragraph
        layout = ParagraphLayout(
            space_before_pt=0.0,
            space_after_pt=round(between, 1) if between > _MIN_GAP_PT else 0.0,
            line_spacing=1.0,
            first_line_indent_mm=0.0,
            left_indent_mm=0.0 if flush_right else round(page.mm(min(lefts) - page.left_px), 1),
            right_indent_mm=0.0,
        )
        return {
            "layout": layout,
            "size_pt": size,
            "align": Alignment.RIGHT if flush_right else None,
        }

    @staticmethod
    def _table(
        block: TableBlock, page: _Page, ocr: Sequence[TextLine], family: str | None
    ) -> TableBlock:
        """Position, width and font size of a table, read inside its bbox with the ruling
        lines taken out (they would join all rows into one 'line'). A cell whose text is a
        whole OCR line gets its own size from the width of that line."""
        assert block.bbox is not None
        box = (
            round(block.bbox.x0 * page.width_px),
            round(block.bbox.y0 * page.height_px),
            round(block.bbox.x1 * page.width_px),
            round(block.bbox.y1 * page.height_px),
        )
        lines = _cell_lines(page.ink.crop(box))
        update: dict[str, object] = {
            "width_mm": round(page.mm(box[2] - box[0]), 1),
            "indent_mm": round(page.mm(box[0] - page.left_px), 1),
        }
        if lines:
            size = _font_size(page.pt(median(line.height for line in lines)))
            own = _cell_sizes(block, page, ocr, family)
            update["rows"] = tuple(
                row.model_copy(
                    update={
                        "cells": tuple(
                            cell.model_copy(
                                update={
                                    "size_pt": cell.size_pt or own.get((r, c), size),
                                    "runs": tuple(
                                        x
                                        if x.size_pt
                                        else x.model_copy(update={"size_pt": own.get((r, c), size)})
                                        for x in cell.runs
                                    ),
                                    "layout": cell.layout
                                    or ParagraphLayout(space_before_pt=0.0, space_after_pt=0.0),
                                }
                            )
                            for c, cell in enumerate(row.cells)
                        )
                    }
                )
                for r, row in enumerate(block.rows)
            )
        return block.model_copy(update=update)

    # ------------------------------------------------------------------ between blocks

    @staticmethod
    def _gaps(
        blocks: list[Block], lines_of: dict[str, list[_Line]], pages: list[_Page]
    ) -> list[Block]:
        """Extra space between measured blocks: into a spacer the model put there, else into
        'space before' of the next block."""
        out = list(blocks)
        previous: int | None = None
        for index, block in enumerate(out):
            lines = lines_of.get(block.id)
            if not lines:
                if isinstance(block, SpacerBlock) and index < _first(out, lines_of):
                    # the top margin is measured from the first line already
                    out[index] = block.model_copy(update={"height_pt": _HAIRLINE_PT})
                elif not isinstance(block, SpacerBlock):
                    previous = None  # a table or a picture between: its height is its own
                continue
            if previous is not None and out[previous].page == block.page:
                above = lines_of[out[previous].id][-1]
                page = pages[block.page - 1]
                layout = getattr(block, "layout", None)
                spacing = layout.line_spacing if layout and layout.line_spacing else 1.0
                size = _size_of(block) or _font_size(page.pt(lines[0].height), block.text())
                extra = page.pt(lines[0].top - above.top) - size * page.single * spacing
                # Word puts the space after the block above into this gap already
                above_layout = getattr(out[previous], "layout", None)
                extra -= (above_layout.space_after_pt or 0.0) if above_layout else 0.0
                if extra > _MIN_GAP_PT:
                    spacer = next(
                        (i for i in range(previous + 1, index) if isinstance(out[i], SpacerBlock)),
                        None,
                    )
                    if spacer is not None:
                        out[spacer] = out[spacer].model_copy(update={"height_pt": round(extra, 1)})
                    elif isinstance(layout, ParagraphLayout):
                        out[index] = block.model_copy(
                            update={
                                "layout": layout.model_copy(
                                    update={"space_before_pt": round(extra, 1)}
                                )
                            }
                        )
            previous = index
        return out


def _lines_in(page: _Page, box: BoundingBox) -> list[_Line]:
    """Text lines inside a block's area, found there and not across the whole page: a table or
    a column next to the block would otherwise join its lines into one tall band. The area is
    widened a little, since a model's box is approximate."""
    slack_x, slack_y = page.width_px * _BOX_SLACK, page.height_px * _BOX_SLACK / 4
    x0 = max(round(min(box.x0, box.x1) * page.width_px - slack_x), 0)
    x1 = min(round(max(box.x0, box.x1) * page.width_px + slack_x), page.width_px)
    y0 = max(round(min(box.y0, box.y1) * page.height_px - slack_y), 0)
    y1 = min(round(max(box.y0, box.y1) * page.height_px + slack_y), page.height_px)
    if x1 - x0 < 2 or y1 - y0 < 2:  # noqa: PLR2004
        return []
    top, bottom = min(box.y0, box.y1) * page.height_px, max(box.y0, box.y1) * page.height_px
    return [
        _Line(line.top + y0, line.bottom + y0, line.left + x0, line.right + x0)
        for line in _lines(_without_rules(page.ink.crop((x0, y0, x1, y1))))
        if top <= line.middle + y0 <= bottom
    ]


def _cell_lines(table: Image.Image) -> list[_Line]:
    """Text lines of a table, column by column: across a row, a two-line cell next to a
    one-line cell leaves no empty row, so the row would look like one tall line."""
    width, height = table.size
    columns = _values(table.resize((width, 1), Image.Resampling.BOX))
    rules = [x for x, value in enumerate(columns) if value > _RULE_SHARE * 255]
    edges = [0, *rules, width]
    cleaned = _without_rules(table)
    found: list[_Line] = []
    for left, right in pairwise(edges):
        if right - left > _MIN_CELL_PX:
            found += _lines(cleaned.crop((left + 1, 0, right, height)))
    return found


def _without_rules(ink: Image.Image) -> Image.Image:
    """Ink with the table's ruling taken out: columns and rows that are mostly ink."""
    width, height = ink.size
    cleaned = ink.copy()
    if height >= _MIN_RULE_PX:  # in a one-line area a letter's stem looks like a rule
        columns = _values(ink.resize((width, 1), Image.Resampling.BOX))
        for x, value in enumerate(columns):
            if value > _RULE_SHARE * 255:
                cleaned.paste(0, (x, 0, x + 1, height))
    if width >= _MIN_RULE_PX and height >= _MIN_RULE_PX:  # one line: underlines are runs
        rows = _values(ink.resize((1, height), Image.Resampling.BOX))
        for y, value in enumerate(rows):
            if value > _RULE_SHARE * 255:
                cleaned.paste(0, (0, y, width, y + 1))
    return cleaned


def _fit_size(
    block: Block, lines: list[_Line], page: _Page, ink_size: float, family: str | None
) -> _Fit | None:
    """The size at which the block's text, set in Times or Arial, wraps into the lines seen on
    the photo (same number of lines, same length of the last one). One line: its width divided
    by the width of the text at one point."""
    if all(line.text for line in lines) and not isinstance(block, FillRowBlock):
        return _fit_line_texts(block, lines, page, ink_size, family)
    if isinstance(block, RequisitesBlock):
        return _fit_lines(block.lines, lines, page, ink_size, family)
    if not isinstance(block, HeadingBlock | ParagraphBlock | ListItemBlock):
        return None
    text = (
        block.text() if not isinstance(block, ListItemBlock) else f"{block.marker} {block.text()}"
    )
    if len(text.strip()) < _MIN_FIT_CHARS or _mostly_blanks(text):
        return None
    bold = all(run.bold for run in block.runs if run.text.strip())
    known = family if family and TextMetrics.available(family, bold) else None
    families = [known] if known else [f for f in _GUESSED if TextMetrics.available(f, bold)]
    if not families:
        return None
    if len(lines) == 1:
        width = page.pt(lines[0].right - lines[0].left + 1)
        # the width of one line is a reliable size; between typefaces, the ink height decides
        options = [
            _Fit(size, name, abs(size - ink_size) / ink_size * _STEP_PENALTY, lines=1)
            for name in families
            if (unit := _METRICS.width_pt(" ".join(text.split()), 1.0, name, bold)) > 0
            and (size := round(width / unit * 2) / 2)
        ]
    else:
        rest = min(line.left for line in lines[1:])
        # Word wraps at the column edge, not at the widest line of ragged text
        width = page.pt(max(page.right_px, *(line.right for line in lines)) - rest + 1)
        indent = page.pt(lines[0].left - rest)
        last = page.pt(lines[-1].right - lines[-1].left + 1)
        options = []
        for name in families:
            for step in range(-8, 9):
                size = ink_size + step / 2
                if size < _MIN_FIT_PT:
                    continue
                wrapped = _METRICS.wrap(text, size, width, name, bold=bold, first_indent_pt=indent)
                miss = abs(wrapped.lines - len(lines))
                error = 1.0 + miss if miss else abs(wrapped.last_pt - last) / width
                options.append(
                    _Fit(size, name, error + abs(step) * _STEP_PENALTY, lines=len(lines))
                )
    plausible = [o for o in options if abs(o.size - ink_size) <= _MAX_FIT_SHIFT_PT]
    best = min(plausible, key=lambda o: o.error, default=None)
    return best if best is not None and best.error < _MAX_FIT_ERROR else None


def _fit_line_texts(
    block: Block, lines: list[_Line], page: _Page, ink_size: float, family: str | None
) -> _Fit | None:
    """Each OCR line knows its own text, so each width gives a size. Lines of a justified
    paragraph that reach the column edge are stretched by Word and say nothing."""
    usable = [
        line
        for index, line in enumerate(lines)
        if index == len(lines) - 1 or page.mm(page.right_px - line.right) > _SAME_EDGE_MM
    ]
    usable = [line for line in usable if len(line.text.strip()) >= _MIN_FIT_CHARS // 2]
    # a blank '____' may be cut out with the rules: the line's width then misses it
    usable = [line for line in usable if "__" not in line.text]
    if not usable:
        return None
    runs = getattr(block, "runs", ())
    bold = bool(runs) and all(run.bold for run in runs if run.text.strip())
    known = family if family and TextMetrics.available(family, bold) else None
    best: _Fit | None = None
    for name in [known] if known else [f for f in _GUESSED if TextMetrics.available(f, bold)]:
        sizes = [
            page.pt(line.text_width) / unit
            for line in usable
            if (unit := _METRICS.width_pt(" ".join(line.text.split()), 1.0, name, bold)) > 0
        ]
        if not sizes:
            continue
        size = round(median(sizes) * 2) / 2
        if abs(size - ink_size) > _MAX_FIT_SHIFT_PT:
            continue
        spread = (max(sizes) - min(sizes)) / size if len(sizes) > 1 else 0.0
        # widths alone cannot tell Times from Arial (both scale alike); the ink height can
        error = spread + abs(size - ink_size) / ink_size + _family_bias(name)
        if best is None or error < best.error:
            best = _Fit(size, name, error, lines=len(sizes))
    return best if best is not None and best.error < _MAX_LINE_FIT_ERROR else None


def _from_ocr(
    blocks: list[Block], ocr: Sequence[TextLine], pages: list[_Page]
) -> dict[str, list[_Line]]:
    """Lines of each block found by its text among the OCR lines, edges tightened on the ink."""
    if not ocr:
        return {}
    found: dict[str, list[_Line]] = {}
    for block_id, indexes in anchor(blocks, ocr).items():
        lines = []
        for index in indexes:
            line = ocr[index]
            if 0 < line.page <= len(pages):
                lines.append(_tight(line, pages[line.page - 1]))
        if lines:
            found[block_id] = sorted(lines, key=lambda line: line.top)
    return found


def _page_breaks(document: Document) -> Document:
    """Each photo is a page of the original: its first block starts a new page."""
    blocks = list(document.blocks)
    for index in range(1, len(blocks)):
        if blocks[index].page > blocks[index - 1].page:
            blocks[index] = blocks[index].model_copy(update={"page_break_before": True})
    return document.model_copy(update={"blocks": tuple(blocks)})


def _floating_pictures(
    blocks: list[Block], lines_of: dict[str, list[_Line]], pages: list[_Page]
) -> list[Block]:
    """A picture lying over the text of other blocks on the photo (a stamp on a signature line)
    floats at its place on the page instead of pushing the text apart; one apart from the text
    (a logo above it) stays in the flow."""
    out: list[Block] = []
    for block in blocks:
        if (
            not isinstance(block, ImageBlock)
            or block.floating is not None
            or block.bbox is None
            or not 0 < block.page <= len(pages)
        ):
            out.append(block)
            continue
        page = pages[block.page - 1]
        box = block.bbox
        left, right = box.x0 * page.width_px, box.x1 * page.width_px
        top, bottom = box.y0 * page.height_px, box.y1 * page.height_px
        over_text = any(
            line.left < right and left < line.right and line.top < bottom and top < line.bottom
            for other in blocks
            if other.id != block.id and other.page == block.page
            for line in lines_of.get(other.id, ())
        )
        if not over_text:
            out.append(block)
            continue
        placement = ImagePlacement(
            horizontal_from="page",
            x_mm=round(page.mm(left), 1),
            vertical_from="page",
            y_mm=round(page.mm(top), 1),
        )
        out.append(
            block.model_copy(
                update={
                    "floating": placement,
                    "width_mm": round(page.mm(right - left), 1),
                    "height_mm": round(page.mm(bottom - top), 1),
                }
            )
        )
    return out


def _cell_sizes(
    table: TableBlock, page: _Page, ocr: Sequence[TextLine], family: str | None
) -> dict[tuple[int, int], float]:
    """Sizes of the cells whose whole text is one OCR line inside the table."""
    if not ocr or table.bbox is None:
        return {}
    box = table.bbox
    inside = [
        line
        for line in ocr
        if line.page == table.page
        and box.x0 <= (line.box.x0 + line.box.x1) / 2 <= box.x1
        and box.y0 <= (line.box.y0 + line.box.y1) / 2 <= box.y1
    ]
    by_text = {_squash_text(line.text): line for line in inside}
    name = family if family and TextMetrics.available(family) else FAMILIES[0]
    sizes: dict[tuple[int, int], float] = {}
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            text = " ".join(plain_text(cell.runs).split())
            line = by_text.get(_squash_text(text))
            if line is None or len(text) < _MIN_FIT_CHARS // 2:
                continue
            bold = all(run.bold for run in cell.runs if run.text.strip())
            unit = (
                _METRICS.width_pt(text, 1.0, name, bold) if TextMetrics.available(name, bold) else 0
            )
            if unit > 0:
                width = page.pt(_tight(line, page).text_width)
                sizes[(r, c)] = round(width / unit * 2) / 2
    return sizes


def _squash_text(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _box_of(lines: list[_Line], page: _Page) -> BoundingBox:
    """The area of a block found by its text lines (a table placed by OCR)."""
    pad = _OCR_PAD_PX * 2
    return BoundingBox(
        x0=max(min(line.left for line in lines) - pad, 0) / page.width_px,
        y0=max(min(line.top for line in lines) - pad, 0) / page.height_px,
        x1=min(max(line.right for line in lines) + pad, page.width_px) / page.width_px,
        y1=min(max(line.bottom for line in lines) + pad, page.height_px) / page.height_px,
    )


def _tight(line: TextLine, page: _Page) -> _Line:
    """The OCR box with a little air around it, shrunk to the ink inside."""
    box = line.box
    x0 = max(round(min(box.x0, box.x1) * page.width_px) - _OCR_PAD_PX, 0)
    y0 = max(round(min(box.y0, box.y1) * page.height_px) - _OCR_PAD_PX, 0)
    x1 = min(round(max(box.x0, box.x1) * page.width_px) + _OCR_PAD_PX, page.width_px)
    y1 = min(round(max(box.y0, box.y1) * page.height_px) + _OCR_PAD_PX, page.height_px)
    ink = _lines(page.ink.crop((x0, y0, max(x1, x0 + 1), max(y1, y0 + 1))))
    if not ink:
        return _Line(y0, y1 - 1, x0, x1 - 1, line.text)
    main = max(ink, key=lambda part: part.height * (part.right - part.left))
    crop = page.ink.crop((x0, main.top + y0, max(x1, x0 + 1), main.bottom + y0 + 1))
    left, right = min(p.left for p in ink) + x0, max(p.right for p in ink) + x0
    # a blank '____' at an end is taken out of the ink with the rules: the OCR box keeps it
    if line.text.lstrip().startswith("_"):
        left = x0 + _OCR_PAD_PX
    if line.text.rstrip().endswith("_"):
        right = x1 - 1 - _OCR_PAD_PX
    return _Line(
        main.top + y0, main.bottom + y0, left, right, line.text, _text_span(crop, main.height),
    )  # fmt: skip


def _text_span(band: Image.Image, height: int) -> int:
    """Ink width with every gap wider than a tab-like stretch counted as a normal space."""
    columns = [v > 0 for v in _values(band.resize((band.size[0], 1), Image.Resampling.BOX))]
    inked = [x for x, on in enumerate(columns) if on]
    if not inked:
        return 0
    wide, space = height * _TAB_GAP, max(round(height * _SPACE_SHARE), 1)
    span, previous = 1, inked[0]
    for x in inked[1:]:
        gap = x - previous - 1
        span += 1 + (space if gap > wide else gap)
        previous = x
    return span


def _fit_lines(
    texts: tuple[str, ...], lines: list[_Line], page: _Page, ink_size: float, family: str | None
) -> _Fit | None:
    """Lines whose text is known one by one (requisites): each width gives a size."""
    if len(texts) != len(lines):
        return None
    known = family if family and TextMetrics.available(family) else None
    best: _Fit | None = None
    for name in [known] if known else [f for f in _GUESSED if TextMetrics.available(f)]:
        sizes = [
            page.pt(line.right - line.left + 1) / unit
            for text, line in zip(texts, lines, strict=True)
            if len(text) >= _MIN_FIT_CHARS and (unit := _METRICS.width_pt(text, 1.0, name)) > 0
        ]
        if not sizes:
            continue
        size = round(median(sizes) * 2) / 2
        spread = (max(sizes) - min(sizes)) / size
        if abs(size - ink_size) <= _MAX_FIT_SHIFT_PT and (best is None or spread < best.error):
            best = _Fit(size, name, spread)
    return best if best is not None and best.error < _MAX_FIT_ERROR else None


def _family_bias(name: str) -> float:
    """Russian business documents are set in Times far more often than in anything else (80 %
    of the text of our samples): another typeface must explain the photo clearly better."""
    return 0.0 if name == FAMILIES[0] else _OTHER_FAMILY_BIAS


def _typeface_on_photo(ocr: Sequence[TextLine], pages: list[_Page]) -> str | None:
    """The typeface, from two clues that fail on different documents, multiplied: where the
    gaps between words fall, and whether the size the line's width asks for gives its height."""
    families = [f for f in FAMILIES if TextMetrics.available(f)]
    if len(families) < 2:  # noqa: PLR2004
        return None
    scores = dict.fromkeys(families, 1.0)
    used = False
    for errors in (_word_gap_errors(ocr, pages), _height_errors(ocr, pages)):
        if all(errors.get(f) for f in families):
            used = True
            for family in families:
                scores[family] *= errors[family]
    if not used:
        return None
    times, *others = families  # serif or not first, then which of the others
    sans = min(others, key=scores.__getitem__)
    if scores[times] * _TYPEFACE_MARGIN < scores[sans] * _OTHER_PRIOR:
        return times
    if scores[sans] * _OTHER_PRIOR * _TYPEFACE_MARGIN < scores[times]:
        return sans
    return None


def _height_errors(ocr: Sequence[TextLine], pages: list[_Page]) -> dict[str, float]:
    """Per typeface: how far the ink height of each line is from the height its text has at
    the size its width asks for (Arial's small letters are taller than Times' at one size)."""
    errors: dict[str, list[float]] = {f: [] for f in FAMILIES if TextMetrics.available(f)}
    for text_line in list(ocr)[:_GAP_LINES]:
        if not 0 < text_line.page <= len(pages):
            continue
        page = pages[text_line.page - 1]
        line = _tight(text_line, page)
        text = " ".join(line.text.split())
        height = page.pt(line.bottom - line.top + 1)
        if len(text) < _MIN_HEIGHT_CHARS or height <= 0:
            continue
        for family, found in errors.items():
            unit = _METRICS.width_pt(text, 1.0, family)
            if unit > 0:
                size = page.pt(line.text_width) / unit
                found.append(abs(size * _METRICS.ink_height_em(text, family) - height) / height)
    return {f: sum(e) / len(e) for f, e in errors.items() if len(e) >= _MIN_FONT_VOTES}


def _word_gap_errors(ocr: Sequence[TextLine], pages: list[_Page]) -> dict[str, float]:
    """Per typeface: how far the gaps between words are from where its word widths put them."""
    errors: dict[str, list[float]] = {f: [] for f in FAMILIES if TextMetrics.available(f)}
    for text_line in list(ocr)[:_GAP_LINES]:
        if not 0 < text_line.page <= len(pages):
            continue
        page = pages[text_line.page - 1]
        line = _tight(text_line, page)
        words = line.text.split()
        gaps = _word_gaps(page, line)
        if len(words) < _MIN_GAP_WORDS or gaps is None or len(gaps) != len(words) - 1:
            continue
        span = line.right - line.left + 1
        for family, found in errors.items():
            expected = _expected_gaps(words, family, span)
            found.append(
                sum(abs(a - b) for a, b in zip(gaps, expected, strict=True)) / len(gaps) / span
            )
    return {f: sum(e) / len(e) for f, e in errors.items() if len(e) >= _MIN_FONT_VOTES}


def _word_gaps(page: _Page, line: _Line) -> list[float] | None:
    """Centres of the gaps between words, from the line's left edge; None for a line with a
    tab-wide gap, where positions say nothing about letter widths."""
    band = page.ink.crop((line.left, line.top, line.right + 1, line.bottom + 1))
    columns = [v > 0 for v in _values(band.resize((band.size[0], 1), Image.Resampling.BOX))]
    least, widest = max(round(line.height * _WORD_GAP), 3), line.height * _TAB_GAP
    gaps: list[float] = []
    start: int | None = None
    for x, inked in enumerate(columns):
        if not inked and start is None:
            start = x
        elif inked and start is not None:
            if x - start > widest:
                return None
            if x - start >= least:
                gaps.append((start + x - 1) / 2)
            start = None
    return gaps


def _expected_gaps(words: list[str], family: str, span: int) -> list[float]:
    widths = [_METRICS.width_pt(word, 1.0, family) for word in words]
    space = _METRICS.width_pt(" ", 1.0, family)
    scale = span / (sum(widths) + space * (len(words) - 1))
    positions, cursor = [], 0.0
    for width in widths[:-1]:
        cursor += width
        positions.append((cursor + space / 2) * scale)
        cursor += space
    return positions


def _typeface(fits: dict[str, _Fit]) -> str | None:
    """The typeface most blocks fit best, when they clearly agree."""
    votes = [fit.family for fit in fits.values() if fit.lines > 1]
    if len(votes) < _MIN_FONT_VOTES:
        return None
    family = max(set(votes), key=votes.count)
    return family if votes.count(family) >= len(votes) * _FONT_AGREEMENT else None


def _mostly_blanks(text: str) -> bool:
    """Underscore blanks are taken out with the rules and cut the letter tails at their level."""
    visible = [ch for ch in text if not ch.isspace()]
    return bool(visible) and visible.count("_") * 2 >= len(visible)


def _snap_sizes(
    blocks: list[Block],
    lines_of: dict[str, list[_Line]],
    pages: list[_Page],
    fits: dict[str, _Fit],
) -> list[Block]:
    """Sizes from ink height are noisy (a pixel is about a point at phone resolution); sizes
    fitted from text widths are not. Blocks measured by ink height and close to the common size
    take it; the common size comes from the fitted blocks when there are any."""
    fitted = [fit.size for fit in fits.values()]
    pooled = [
        pages[block.page - 1].pt(line.height)
        for block in blocks
        if _ink_per_em(block.text()) == _INK_PER_EM
        for line in lines_of.get(block.id, ())
    ]
    measured = [x for b in blocks if (x := _size_of(b)) is not None and x != _UNMEASURED]
    if fitted:
        common = max(set(fitted), key=fitted.count)
    elif len(pooled) >= _MIN_POOLED_LINES:
        common = _font_size(median(pooled))
    elif measured:
        common = max(set(measured), key=measured.count)
    else:
        common = _FALLBACK_SIZE
    out: list[Block] = []
    for block in blocks:
        if block.id in fits:
            out.append(block)
            continue
        size = _size_of(block)
        unmeasured = size == _UNMEASURED
        if size is None or size == common or (abs(size - common) > _SNAP_PT and not unmeasured):
            out.append(block)
            continue
        update: dict[str, object] = {}
        if hasattr(block, "size_pt"):
            update["size_pt"] = common
        if hasattr(block, "runs"):
            update["runs"] = tuple(
                r.model_copy(update={"size_pt": common}) if r.size_pt == size else r
                for r in getattr(block, "runs", ())
            )
        out.append(block.model_copy(update=update))
    return out


def _first(blocks: list[Block], lines_of: dict[str, list[_Line]]) -> int:
    return next((i for i, b in enumerate(blocks) if lines_of.get(b.id)), len(blocks))


def _size_of(block: Block) -> float | None:
    runs = getattr(block, "runs", ())
    return getattr(block, "size_pt", None) or (runs[0].size_pt if runs else None)


def _lines(ink: Image.Image) -> list[_Line]:
    """Text lines: runs of ink rows joined into lines, each with its left and right ink edge."""
    width = ink.size[0]
    lines: list[_Line] = []
    for top, bottom in _join_thin(_ink_runs(ink)):
        if bottom - top + 1 < 3:  # noqa: PLR2004 - thinner runs are rules and specks
            continue
        band = ink.crop((0, top, width, bottom + 1)).resize((width, 1), Image.Resampling.BOX)
        columns = [x for x, v in enumerate(_values(band)) if v > 0]
        if columns:
            lines.append(_Line(top, bottom, columns[0], columns[-1]))
    if not lines:
        return lines
    typical = median(line.height for line in lines)
    return [line for line in lines if line.height <= typical * 3]  # tables, pictures


def _ink_runs(ink: Image.Image) -> list[tuple[int, int]]:
    """Consecutive rows with at least two ink pixels."""
    width, height = ink.size
    rows = _values(ink.resize((1, height), Image.Resampling.BOX))
    min_row = 255 * 2 / width
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y, value in enumerate([*rows, 0]):
        if value >= min_row and start is None:
            start = y
        elif value < min_row and start is not None:
            thin = y - start <= 2  # noqa: PLR2004
            if not (thin and max(rows[start:y]) >= _UNDERLINE_SHARE * 255):
                runs.append((start, y - 1))
            start = None
    return runs


def _join_thin(runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """A few tall letters ('б', 'й') or tails ('р', 'у') leave an empty row between them and the
    rest of their line: such a thin run joins the nearer full line, if it is close. Two full
    lines are never joined."""
    if not runs:
        return []
    typical = median(bottom - top + 1 for top, bottom in runs)
    limit = max(typical * _SPLIT_GAP, 1)
    merged: list[tuple[int, int]] = []
    carry: int | None = None  # top of a thin run waiting for the line below it
    for index, (top, bottom) in enumerate(runs):
        if bottom - top + 1 >= typical * _THIN_RUN:
            merged.append((top if carry is None else carry, bottom))
            carry = None
            continue
        up = top - merged[-1][1] - 1 if merged and carry is None else limit + 1
        down = runs[index + 1][0] - bottom - 1 if index + 1 < len(runs) else limit + 1
        if down <= limit and down <= up:
            carry = top if carry is None else carry
        elif up <= limit:
            merged[-1] = (merged[-1][0], bottom)
        else:
            merged.append((top, bottom))
    return merged


def _values(image: Image.Image) -> list[float]:
    """Pixel values of a one-band image, row by row."""
    return [float(cast("float", v)) for v in image.get_flattened_data()]


def _rest(lines: list[_Line]) -> list[int]:
    """Left edges that show the paragraph's indent: all lines but an indented first one."""
    return [line.left for line in lines[1:]] if len(lines) > 1 else [lines[0].left]


def _font_size(ink_height_pt: float, text: str = "") -> float:
    estimate = ink_height_pt / _ink_per_em(text)
    return min(_SIZES, key=lambda size: abs(size - estimate))


def _ink_size(lines: list[_Line], page: _Page, text: str) -> float:
    """Size from ink height: each OCR line against the ink of its own letters in the typeface
    (a line without tails is shorter than one with them; Д, Ц, Щ and Й reach further than the
    rule of thumb thinks), else the block's lines against the block's text by that rule."""
    if lines and all(line.text.strip() for line in lines):
        # a blank '____' is cut out with the rules or not, so its line says nothing sure
        estimates = [
            page.pt(line.height) / _ink_em(line.text)
            for line in lines
            if "_" not in line.text and len(line.text.strip()) >= _MIN_INK_CHARS
        ]
        if estimates:
            return min(_SIZES, key=lambda size: abs(size - median(estimates)))
    return _font_size(page.pt(median(line.height for line in lines)), text)


def _ink_em(text: str) -> float:
    """Ink height of the text in font sizes, from the typeface itself when it is at hand."""
    flat = " ".join(text.split())
    if flat and TextMetrics.available(FAMILIES[0]):
        return _METRICS.ink_height_em(flat, FAMILIES[0])
    return _ink_per_em(text)


def _ink_per_em(text: str) -> float:
    """How tall the ink of this text is, in font sizes: 'ЗАЯВЛЕНИЕ' and 'Исполнитель.' have no
    descenders, 'ассистент' has neither capitals nor descenders."""
    if not text.strip():
        return _INK_PER_EM
    tall = any(ch.isupper() or ch.isdigit() or ch in _ASCENDERS for ch in text)
    low = any(ch in _DESCENDERS for ch in text)
    return (_CAP_TOP if tall else _X_TOP) + (_DESCENT if low else 0.0)


def _alignment(lines: list[_Line], page: _Page) -> Alignment:
    """Conservative: centre and right only when every line shows it."""
    middle = (page.left_px + page.right_px) / 2
    gaps = [
        (page.mm(line.left - page.left_px), page.mm(page.right_px - line.right)) for line in lines
    ]
    if all(
        left > _SAME_EDGE_MM * 3
        and abs(page.mm((line.left + line.right) / 2 - middle)) < _SAME_EDGE_MM
        for line, (left, _) in zip(lines, gaps, strict=True)
    ):
        return Alignment.CENTER
    if all(right < _SAME_EDGE_MM and left > _SAME_EDGE_MM * 4 for left, right in gaps):
        return Alignment.RIGHT
    if len(lines) > 1 and all(right < _SAME_EDGE_MM for _, right in gaps[:-1]):
        return Alignment.JUSTIFY
    return Alignment.LEFT
