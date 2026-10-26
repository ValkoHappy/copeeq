"""Draws a Document as a printed A4 page.

Used to synthesise eval photos and as a dependency-free preview. Keeps the exact x
position of every character, so handwritten edits can be drawn over specific words.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from foto2word.domain.document import (
    Alignment,
    Document,
    FillRowBlock,
    HeadingBlock,
    ImageBlock,
    LabeledLineBlock,
    ListItemBlock,
    ParagraphBlock,
    RequisitesBlock,
    ShapeBlock,
    SignatureLineBlock,
    SpacerBlock,
    SpacerSize,
    TableBlock,
    TextBoxBlock,
    TwoColumnLineBlock,
    plain_text,
)
from foto2word.domain.profile import Profile, TextStyle
from foto2word.infrastructure.raster.fonts import FontSet

INK = (25, 25, 30)
PAPER = (255, 255, 255)
_SPACER_LINES = {SpacerSize.SMALL: 1, SpacerSize.MEDIUM: 2, SpacerSize.LARGE: 4}
Box = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class TextSpan:
    """One drawn line of a block with the x position of every character boundary."""

    block_id: str
    text: str
    xs: tuple[float, ...]
    top: float
    bottom: float

    def locate(self, fragment: str) -> Box | None:
        start = self.text.find(fragment)
        if start < 0 or not fragment:
            return None
        return (self.xs[start], self.top, self.xs[start + len(fragment)], self.bottom)


@dataclass(slots=True)
class RasterPage:
    image: Image.Image
    spans: list[TextSpan] = field(default_factory=list)
    block_boxes: dict[str, Box] = field(default_factory=dict)
    signature_slots: dict[str, Box] = field(default_factory=dict)

    def locate(self, block_id: str, fragment: str) -> Box | None:
        for span in self.spans:
            if span.block_id == block_id and (box := span.locate(fragment)) is not None:
                return box
        return None


class PageRasterizer:
    """Stateful while drawing: use one instance per thread."""

    def __init__(self, fonts: FontSet, profile: Profile, dpi: int = 150) -> None:
        self._fonts = fonts
        self._profile = profile
        self._dpi = dpi
        self._draw_block: dict[type, Callable[[Any], None]] = {
            HeadingBlock: self._heading,
            ParagraphBlock: self._paragraph,
            ListItemBlock: self._list_item,
            LabeledLineBlock: self._labeled_line,
            TwoColumnLineBlock: self._two_column_line,
            SignatureLineBlock: self._signature_line,
            RequisitesBlock: self._requisites,
            SpacerBlock: self._spacer,
            TableBlock: self._table,
            ImageBlock: self._image,
            FillRowBlock: self._fill_row,
            TextBoxBlock: self._text_box,
            ShapeBlock: lambda block: None,
        }
        self._page = RasterPage(Image.new("RGB", (1, 1)))
        self._draw = ImageDraw.Draw(self._page.image)
        self._y = 0.0
        self._current = ""

    def mm(self, value: float) -> float:
        return value * self._dpi / 25.4

    def render(self, document: Document) -> RasterPage:
        page = self._profile.page
        size = (round(self.mm(page.width_mm)), round(self.mm(page.height_mm)))
        self._page = RasterPage(Image.new("RGB", size, PAPER))
        self._draw = ImageDraw.Draw(self._page.image)
        self._y = self.mm(page.margins.top_mm)
        for block in document.blocks:
            top = self._y
            self._current = block.id
            self._draw_block[type(block)](block)
            self._page.block_boxes[block.id] = (self._left, top, self._right, self._y)
        return self._page

    # --- geometry and fonts -----------------------------------------------------------------

    @property
    def _left(self) -> float:
        return self.mm(self._profile.page.margins.left_mm)

    @property
    def _right(self) -> float:
        page = self._profile.page
        return self.mm(page.width_mm - page.margins.right_mm)

    def _font(self, style: TextStyle, bold: bool = False) -> ImageFont.FreeTypeFont:
        return self._fonts.text(round(style.size_pt * self._dpi / 72), bold or style.bold)

    def _line_height(self, style: TextStyle) -> float:
        return style.size_pt * self._dpi / 72 * 1.2 * style.line_spacing

    # --- text primitives --------------------------------------------------------------------

    def _wrap(
        self, text: str, font: ImageFont.FreeTypeFont, width: float, first: float
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}" if current else word
            available = width - (first if not lines else 0)
            if current and font.getlength(candidate) > available:
                lines.append(current)
                current = word
            else:
                current = candidate
        return [*lines, current] if current else lines

    def _draw_line(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        *,
        x0: float,
        x1: float,
        align: Alignment,
        line_height: float,
        justify: bool = False,
    ) -> None:
        words = text.split(" ")
        widths = [font.getlength(w) for w in words]
        natural = font.getlength(text)
        gap = font.getlength(" ")
        if justify and len(words) > 1:
            gap = (x1 - x0 - sum(widths)) / (len(words) - 1)
            x = x0
        elif align is Alignment.CENTER:
            x = x0 + (x1 - x0 - natural) / 2
        elif align is Alignment.RIGHT:
            x = x1 - natural
        else:
            x = x0

        xs: list[float] = []
        for index, (word, width) in enumerate(zip(words, widths, strict=True)):
            self._draw.text((x, self._y), word, font=font, fill=INK)
            xs += [x + font.getlength(word[:k]) for k in range(len(word))]
            x += width
            if index < len(words) - 1:
                xs.append(x)
                x += gap
        xs.append(x)
        self._page.spans.append(
            TextSpan(self._current, text, tuple(xs), self._y, self._y + line_height)
        )

    def _text_block(
        self,
        text: str,
        style: TextStyle,
        align: Alignment,
        *,
        bold: bool = False,
        first_indent_mm: float | None = None,
        left_mm: float | None = None,
    ) -> None:
        font = self._font(style, bold)
        x0 = self._left + self.mm(style.left_indent_mm if left_mm is None else left_mm)
        first = self.mm(style.first_line_indent_mm if first_indent_mm is None else first_indent_mm)
        if align is not Alignment.JUSTIFY and align is not Alignment.LEFT:
            first = 0.0
        height = self._line_height(style)
        self._y += style.space_before_pt * self._dpi / 72
        lines = self._wrap(text, font, self._right - x0, first)
        for index, line in enumerate(lines):
            start = x0 + (first if index == 0 else 0.0)
            is_last = index == len(lines) - 1
            justify = align is Alignment.JUSTIFY and not is_last
            self._draw_line(
                line,
                font,
                x0=start,
                x1=self._right,
                align=align,
                line_height=height,
                justify=justify,
            )
            self._y += height
        self._y += style.space_after_pt * self._dpi / 72

    def _columns(self, parts: list[tuple[str, float, bool]], style: TextStyle) -> None:
        """Draw one line with text at fixed x positions (tab stops). (text, x, right-aligned)"""
        font = self._font(style)
        height = self._line_height(style)
        for text, x, right in parts:
            if not text:
                continue
            width = font.getlength(text)
            start = x - width if right else x
            self._draw_line(
                text, font, x0=start, x1=start + width, align=Alignment.LEFT, line_height=height
            )
        self._y += height

    # --- blocks -------------------------------------------------------------------------------

    def _heading(self, block: HeadingBlock) -> None:
        styles = self._profile.styles
        style = styles.title if block.level <= 1 else styles.subtitle
        self._text_block(block.text(), style, block.align or style.align)

    def _paragraph(self, block: ParagraphBlock) -> None:
        style = self._profile.styles.body
        align = block.align or style.align
        indent = None if align is Alignment.JUSTIFY else 0.0
        bold = bool(block.runs) and all(run.bold for run in block.runs)
        self._text_block(block.text(), style, align, bold=bold, first_indent_mm=indent)

    def _list_item(self, block: ListItemBlock) -> None:
        style = self._profile.styles.list_item
        first = style.first_line_indent_mm + block.level * self._profile.list_indent_mm
        self._text_block(
            f"{block.marker} {block.text()}", style, style.align, first_indent_mm=first
        )

    def _labeled_line(self, block: LabeledLineBlock) -> None:
        width = self._right - self._left
        parts = [(block.label, self._left, False), (block.value, self._left + width * 0.35, False)]
        self._columns(parts, self._profile.styles.line)

    def _two_column_line(self, block: TwoColumnLineBlock) -> None:
        parts = [(block.left, self._left, False), (block.right, self._right, True)]
        self._columns(parts, self._profile.styles.line)

    def _signature_line(self, block: SignatureLineBlock) -> None:
        style = self._profile.styles.line
        width = self._right - self._left
        self._y += self.mm(6)
        blank_x0, blank_x1 = self._left + width * 0.38, self._left + width * 0.62
        baseline = self._y + self._line_height(style) * 0.8
        self._draw.line((blank_x0, baseline, blank_x1, baseline), fill=INK, width=2)
        self._page.signature_slots[block.id] = (blank_x0, self._y - self.mm(4), blank_x1, baseline)
        parts = [(block.label, self._left, False), (block.name, self._left + width * 0.70, False)]
        self._columns(parts, style)

    def _requisites(self, block: RequisitesBlock) -> None:
        style = self._profile.styles.requisites
        for line in block.lines:
            self._text_block(line, style, Alignment.LEFT, first_indent_mm=0.0)

    def _spacer(self, block: SpacerBlock) -> None:
        self._y += self._line_height(self._profile.styles.line) * _SPACER_LINES[block.size]

    def _text_box(self, block: TextBoxBlock) -> None:
        for inner in block.blocks:
            self._draw_block[type(inner)](inner)

    def _fill_row(self, block: FillRowBlock) -> None:
        """Labels and blanks on one line, captions in small type under the blanks."""
        style = self._profile.styles.line
        width = (self._right - self._left) / max(len(block.slots), 1)
        parts = [
            (
                f"{slot.label} {plain_text(slot.value) or '_' * 12}".strip(),
                self._left + i * width,
                False,
            )
            for i, slot in enumerate(block.slots)
        ]
        self._columns(parts, style)
        captions = [(s.caption, self._left + i * width, False) for i, s in enumerate(block.slots)]
        if any(text for text, _, _ in captions):
            small = style.model_copy(update={"size_pt": max(style.size_pt * 0.65, 6.0)})
            self._columns([c for c in captions if c[0]], small)

    def _image(self, block: ImageBlock) -> None:
        """A grey frame where the picture would be."""
        width = self.mm(block.width_mm or 40.0)
        height = self.mm(block.height_mm or 20.0)
        left = (self._left + self._right - width) / 2
        self._draw.rectangle(
            (left, self._y, left + width, self._y + height), outline=(160, 160, 160)
        )
        self._y += height + self._line_height(self._profile.styles.line) * 0.5

    def _table(self, block: TableBlock) -> None:
        style = self._profile.styles.table
        font = self._font(style)
        n_cols = block.column_count()
        if n_cols == 0:
            return
        weights = list(block.column_widths or ())
        if len(weights) != n_cols or any(w <= 0 for w in weights):
            weights = [1.0] * n_cols
        total = self._right - self._left
        edges = [self._left]
        for weight in weights:
            edges.append(edges[-1] + total * weight / sum(weights))

        pad = self.mm(1.5)
        height = self._line_height(style)
        placements = block.placements()
        row_heights = [height + 2 * pad] * len(block.rows)
        for p in placements:
            if p.cell.row_span == 1:
                width = edges[p.col + p.cell.col_span] - edges[p.col] - 2 * pad
                n_lines = max(len(self._wrap(plain_text(p.cell.runs), font, width, 0)), 1)
                row_heights[p.row] = max(row_heights[p.row], n_lines * height + 2 * pad)
        tops = [self._y]
        for h in row_heights:
            tops.append(tops[-1] + h)

        for p in placements:
            x0, x1 = edges[p.col], edges[min(p.col + p.cell.col_span, n_cols)]
            y0, y1 = tops[p.row], tops[min(p.row + p.cell.row_span, len(block.rows))]
            self._draw.rectangle((x0, y0, x1, y1), outline=INK, width=2)
            saved = self._y
            self._y = y0 + pad
            bold = p.row < block.header_rows
            cell_font = self._font(style, bold)
            for line in self._wrap(plain_text(p.cell.runs), cell_font, x1 - x0 - 2 * pad, 0):
                align = p.cell.align or style.align
                self._draw_line(
                    line, cell_font, x0=x0 + pad, x1=x1 - pad, align=align, line_height=height
                )
                self._y += height
            self._y = saved
        self._y = tops[-1] + height
