"""DocModel: the provider-independent description of a document.

Every pipeline stage talks through these types. The same schema is handed to a
vision model as the required output format, so field descriptions double as
instructions for the model.
"""

from abc import abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Alignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class InlinePicture(_Frozen):
    """A picture standing in a line of text (a logo before a title, a button in an
    instruction); its pixels come with the source file (RenderExtras.images, by image_id)."""

    image_id: str
    width_mm: float | None = None
    height_mm: float | None = None
    crop: tuple[float, float, float, float] | None = None
    """Shares of the picture cut off at its left, top, right and bottom (Word's crop)."""


class Run(_Frozen):
    """A piece of text with uniform inline formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    superscript: bool = False
    subscript: bool = False
    size_pt: float | None = Field(
        default=None, description="Font size as seen on the page, if it differs from body text."
    )
    color: str | None = Field(
        default=None, description="Hex RGB like '1F4E79' for coloured text; null for black."
    )
    font: str | None = Field(
        default=None, description="Typeface if recognisable: 'Times New Roman', 'Arial', ..."
    )
    spacing_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Extra space between letters (negative: condensed), as Word's character spacing."""
    background: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Colour behind the text as RRGGBB: a highlighter mark or shading of the run."""
    picture: InlinePicture | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """This run is a picture in the line, not text."""
    kern_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Letters are kerned in pairs from this size up (w:kern): the text is a little narrower."""
    scale_pct: int | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Letters stretched or squeezed in width (w:w), in per cent: 95 is a little narrower."""
    clear: Literal["all", "left", "right"] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Its line breaks send the text after below floating objects (w:clear): the text under a
    floating table rather than beside it."""
    math: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """This run is Word's own equation (OMML, as Word wrote it); the text is what it reads."""
    vml: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """An old-style drawing standing in the line (w:pict, as Word wrote it): WordArt, a box; the
    text is what WordArt says, else empty."""
    field: Literal["page", "pages"] | None = Field(
        default=None,
        description="'page' for the current page number, 'pages' for the number of pages "
        "(as in 'Страница 1 из 4'); the text is the number as printed.",
    )
    """Word fills the number in on every page: PAGE and NUMPAGES fields."""
    footnote: int | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """This run is a footnote mark: the reference to footnote N in the text, or (0) the number
    at the start of the note itself. Its text is the mark as printed; Word numbers it."""

    def replaced(self, before: str, after: str) -> Self | None:
        if before not in self.text:
            return None
        return self.model_copy(update={"text": self.text.replace(before, after, 1)})


def _replace_in_runs(runs: tuple[Run, ...], before: str, after: str) -> tuple[Run, ...] | None:
    for index, run in enumerate(runs):
        new_run = run.replaced(before, after)
        if new_run is not None:
            return (*runs[:index], new_run, *runs[index + 1 :])
    return None


def _replace_in_strings(values: tuple[str, ...], before: str, after: str) -> tuple[str, ...] | None:
    for index, value in enumerate(values):
        if before in value:
            return (*values[:index], value.replace(before, after, 1), *values[index + 1 :])
    return None


def plain_text(runs: tuple[Run, ...]) -> str:
    return "".join(run.text for run in runs)


class BoundingBox(_Frozen):
    """Region on the source photo, coordinates normalised to 0..1 from the top-left."""

    x0: float
    y0: float
    x1: float
    y1: float


def _require_kind(schema: dict[str, Any]) -> None:
    """`kind` has a default for convenient construction in code, but a model must always send it."""
    kind = schema["properties"]["kind"]
    if "const" in kind:
        kind["enum"] = [kind.pop("const")]
    kind.pop("default", None)
    required = schema.setdefault("required", [])
    if "kind" not in required:
        required.append("kind")


class PageGeometry(_Frozen):
    width_mm: float
    height_mm: float
    top_mm: float
    bottom_mm: float
    left_mm: float
    right_mm: float
    header_mm: float | None = None
    """From the page's top edge to the header; text starts below the header if it reaches
    further down than the top margin."""
    footer_mm: float | None = None
    borders: tuple[tuple[Literal["top", "left", "bottom", "right"], "BorderLine"], ...] = ()
    """A frame around the page, side by side (Word's page borders)."""
    borders_from_text: bool = False
    """The frame's distances count from the text, not from the page's edge."""
    number_start: int | None = None
    """The section's pages are numbered from this number (an appendix that goes on from 2)."""
    doc_grid: tuple[tuple[str, str], ...] | None = None
    gutter_mm: float = 0.0
    exact: tuple[bool, bool] = (False, False)
    """Top and bottom margins held exactly (written negative): the header and footer do not
    push the text, however tall they are."""
    """Room left for binding beside the left margin (w:gutter): the text starts further in."""
    """Word's grid of lines (w:docGrid, its attributes as written): each line takes a whole
    number of the grid's lines."""


class SectionStart(_Frozen):
    """The original starts a new section here: text in columns, a landscape page, ..."""

    new_page: bool = True
    columns: int = 1
    column_gap_mm: float = 12.5
    column_widths_mm: tuple[tuple[float, float], ...] = ()
    """Columns of their own widths: (width, gap after it) each; empty: equal columns."""
    page: PageGeometry | None = None
    """The section's own page size and margins (portrait or landscape by its size)."""


class _Block(_Frozen):
    model_config = ConfigDict(json_schema_extra=_require_kind)

    id: str = Field(description="Unique block id, e.g. 'b1', 'b2' in reading order.")
    page: int = Field(default=1, description="1-based page number on the source photos.")
    bbox: BoundingBox | None = None
    confidence: float = Field(default=1.0, description="0..1, how sure the reading is.")
    page_break_before: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    """The original starts a new page here: a manual break, a new section, the next photo."""
    column_break_before: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    """The original moves on to the next column here (a column break)."""
    section: SectionStart | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The original starts a new section here (on the first block: the first section's own
    columns)."""

    @abstractmethod
    def replace_text(self, before: str, after: str) -> Self | None:
        """Return a copy with the first occurrence replaced, or None if not found."""

    @abstractmethod
    def text(self) -> str:
        """Plain text of the block, used for checks and comparisons."""


class BorderLine(_Frozen):
    """How a line looks, as Word draws it."""

    style: str = "single"
    """Word's line kind: 'single', 'double', 'dashed', 'dotted', 'thick', ..."""
    size: int = 4
    """Width in eighths of a point."""
    color: str | None = None
    """RRGGBB; null: black."""
    space_pt: int = 0
    """Distance to the text (paragraph lines)."""


PageGeometry.model_rebuild()


class CellBorders(_Frozen):
    """Which sides of a table cell or a paragraph have a visible line."""

    top: bool = True
    bottom: bool = True
    left: bool = True
    right: bool = True
    lines: tuple[tuple[Literal["top", "bottom", "left", "right"], BorderLine], ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """The look of the sides whose line is not a thin black one (a teal bar, a grey grid)."""


class TabStop(_Frozen):
    """A tab position; a leader fills the gap, e.g. '______' lines to write on."""

    position_mm: float
    align: Literal["left", "center", "right", "decimal"] = "left"
    leader: Literal["none", "dot", "underscore", "hyphen"] = "none"


class ParagraphLayout(_Frozen):
    """Spacing and indents as on the original page. Unset values come from the profile."""

    space_before_pt: float | None = None
    space_after_pt: float | None = None
    line_spacing: float | None = Field(default=None, description="Multiple, e.g. 1.0 or 1.5.")
    line_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Line height in points when the original sets it 'exactly' or 'at least'; line_spacing
    is then only an estimate of it."""
    line_at_least: bool = False
    """line_pt is a minimum: a taller line keeps its natural height."""
    first_line_indent_mm: float | None = None
    left_indent_mm: float | None = None
    right_indent_mm: float | None = None
    tabs: tuple[TabStop, ...] = ()
    borders: CellBorders | None = None
    """Lines drawn around the paragraph: a rule under a letterhead or a title, a framed note."""
    shading: str | None = None
    """Background of the paragraph as RRGGBB: a grey bar behind a section title."""
    keep_next: bool = False
    """Kept on one page with the next paragraph (a heading with its first lines)."""
    keep_lines: bool = False
    """Its lines are not split between pages."""
    mark_size_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    mark_font: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Size and face of the paragraph mark: Word counts the mark in the height of the last line
    (a 7 pt caption ending in a 12 pt mark is a 12 pt line)."""
    frame: tuple[tuple[str, str], ...] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The paragraph stands in a frame at a fixed place (w:framePr), as forms exported by 1C
    place each field: its attributes as Word writes them."""
    off_grid: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    no_hyphens: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    """Word does not hyphenate this paragraph's words (w:suppressAutoHyphens)."""
    """The paragraph keeps its own line height on a page with a grid of lines (w:snapToGrid 0)."""


class _RunsBlock(_Block):
    runs: tuple[Run, ...]
    layout: ParagraphLayout | None = None

    def replace_text(self, before: str, after: str) -> Self | None:
        runs = _replace_in_runs(self.runs, before, after)
        return None if runs is None else self.model_copy(update={"runs": runs})

    def text(self) -> str:
        return plain_text(self.runs)


class HeadingBlock(_RunsBlock):
    kind: Literal["heading"] = "heading"
    level: int = Field(default=1, description="1 = document title, 2..3 = subtitles/sections.")
    align: Alignment | None = None


class ParagraphRole(StrEnum):
    BODY = "body"
    NOTE = "note"
    CAPTION = "caption"


class ParagraphBlock(_RunsBlock):
    kind: Literal["paragraph"] = "paragraph"
    role: ParagraphRole = ParagraphRole.BODY
    align: Alignment | None = None


class ListItemBlock(_RunsBlock):
    kind: Literal["list_item"] = "list_item"
    marker: str = Field(description="Marker exactly as printed: '1.', '2)', 'а)', '-', '•'.")
    level: int = Field(default=0, description="Nesting depth, 0 = top level.")
    align: Alignment | None = None
    marker_font: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    marker_size_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The marker's own typeface and size: a bullet in Symbol makes its line taller."""
    marker_glyph: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """A bullet's character as the Word file has it, to be typed in marker_font."""
    marker_gap: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """What follows the marker in the Word file: a tab (Word's default), a space or nothing."""


class VerticalAlignment(StrEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class CellPadding(_Frozen):
    """Space between cell lines and cell text."""

    top_mm: float = 0.0
    bottom_mm: float = 0.0
    left_mm: float = 1.9
    right_mm: float = 1.9


class ImagePlacement(_Frozen):
    """A picture floating at a fixed place over or under the text (Word's anchored drawing):
    a stamp over a signature, a logo in a corner. It takes no room in the flow of text."""

    horizontal_from: Literal[
        "page",
        "margin",
        "column",
        "character",
        "leftMargin",
        "rightMargin",
        "insideMargin",
        "outsideMargin",
    ] = "column"
    x_mm: float | None = None
    x_align: Literal["left", "center", "right", "inside", "outside"] | None = None
    vertical_from: Literal[
        "page",
        "margin",
        "paragraph",
        "line",
        "topMargin",
        "bottomMargin",
        "insideMargin",
        "outsideMargin",
    ] = "paragraph"
    y_mm: float | None = None
    y_align: Literal["top", "center", "bottom", "inside", "outside"] | None = None
    wrap: Literal["none", "square", "top_and_bottom"] = "none"
    """How the text goes around it; 'none': the picture lies over (or under) the text."""
    distances_emu: tuple[int, int, int, int] = (0, 0, 0, 0)
    """How far the text keeps from it: above, below, left, right (wp:anchor dist*)."""
    behind_text: bool = False


class CellImage(_Frozen):
    """A picture in a table cell (a logo in a letterhead table), at the start of a line of
    the cell; its pixels come with the source file (RenderExtras.images, by image_id)."""

    line: int
    image_id: str
    width_mm: float | None = None
    height_mm: float | None = None
    floating: ImagePlacement | None = None
    crop: tuple[float, float, float, float] | None = None
    """Shares of the picture cut off at its left, top, right and bottom (Word's crop)."""


class TableCell(_Frozen):
    runs: tuple[Run, ...] = ()
    col_span: int = 1
    row_span: int = 1
    align: Alignment | None = None
    borders: CellBorders | None = Field(
        default=None, description="Visible cell lines; null = the table's default."
    )
    v_align: VerticalAlignment | None = None
    layout: ParagraphLayout | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    size_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Font size of the cell's paragraph: an empty cell is still one line of it tall."""
    line_layouts: tuple[ParagraphLayout, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """One per paragraph of the cell when they differ (a name at 1.5 lines, details at 1)."""
    line_aligns: tuple[Alignment, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """One per paragraph of the cell when they differ (an address, a caption centred under it)."""
    hide_mark: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    shading: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Background fill of the cell as RRGGBB: a grey header, a tinted box not to fill in."""
    text_direction: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The cell's text turned on its side, as Word writes it (w:textDirection: 'btLr' bottom
    to top, 'tbRl' top to bottom); null: across."""
    padding: CellPadding | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The cell's own margins where they differ from the table's (null: the table's)."""
    """An empty cell that does not make its row taller (Word's hideMark)."""
    rest_sizes_pt: tuple[float, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """Size of the empty line left in each row a vertically merged cell continues into."""
    images: tuple[CellImage, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    tables: tuple["NestedTable", ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """Tables inside the cell: a form drawn within one framing cell."""

    def text(self) -> str:
        return "\n".join([plain_text(self.runs), *(t.table.text() for t in self.tables)])

    def replaced(self, before: str, after: str) -> Self | None:
        """The cell with the first occurrence replaced, in its own text or a nested table."""
        runs = _replace_in_runs(self.runs, before, after)
        if runs is not None:
            return self.model_copy(update={"runs": runs})
        for index, nested in enumerate(self.tables):
            table = nested.table.replace_text(before, after)
            if table is not None:
                changed = nested.model_copy(update={"table": table})
                tables = (*self.tables[:index], changed, *self.tables[index + 1 :])
                return self.model_copy(update={"tables": tables})
        return None


class TableRow(_Frozen):
    cells: tuple[TableCell, ...]
    height_mm: float | None = None
    exact_height: bool = False
    """The row is exactly height_mm (forms with fixed boxes), not at least that."""
    skip: int = Field(default=0, description="Leave 0; set only when imported from a Word file.")
    """Grid columns left empty before the row's first cell (Word's gridBefore)."""


@dataclass(frozen=True, slots=True)
class CellPlacement:
    row: int
    col: int
    cell: TableCell


class TablePosition(_Frozen):
    """Where a floating table stands, text flowing around it (Word's tblpPr). Unset values
    are Word's defaults."""

    horizontal_anchor: Literal["text", "margin", "page"] | None = None
    vertical_anchor: Literal["text", "margin", "page"] | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    x_align: Literal["left", "center", "right", "inside", "outside"] | None = None
    y_align: Literal["top", "center", "bottom", "inside", "outside", "inline"] | None = None
    gap_left_mm: float | None = None
    gap_right_mm: float | None = None
    gap_top_mm: float | None = None
    gap_bottom_mm: float | None = None


class TableBlock(_Block):
    kind: Literal["table"] = "table"
    rows: tuple[TableRow, ...]
    header_rows: int = 0
    column_widths: tuple[float, ...] | None = Field(
        default=None, description="Relative column widths, any positive numbers."
    )
    width_mm: float | None = Field(
        default=None, description="Total table width if it differs from the text width."
    )
    grid: bool = Field(
        default=True,
        description="True = all lines visible (ordinary table); false = an invisible layout table.",
    )
    align: Alignment | None = Field(default=None, description="Position of the table on the page.")
    indent_mm: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    padding: CellPadding | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    cell_spacing_mm: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Gap between neighbouring cells; each cell then draws its own frame (double lines)."""
    autofit: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    """Word may widen a column to fit its longest word (the original's layout); else the
    column widths are fixed."""
    position: TablePosition | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )

    def replace_text(self, before: str, after: str) -> Self | None:
        for r, row in enumerate(self.rows):
            for c, cell in enumerate(row.cells):
                new_cell = cell.replaced(before, after)
                if new_cell is None:
                    continue
                new_row = row.model_copy(
                    update={"cells": (*row.cells[:c], new_cell, *row.cells[c + 1 :])}
                )
                rows = (*self.rows[:r], new_row, *self.rows[r + 1 :])
                return self.model_copy(update={"rows": rows})
        return None

    def text(self) -> str:
        return "\n".join("\t".join(cell.text() for cell in row.cells) for row in self.rows)

    def placements(self) -> list[CellPlacement]:
        """Grid coordinates of every cell, skipping slots covered by row spans."""
        covered: set[tuple[int, int]] = set()
        placements: list[CellPlacement] = []
        for row_index, row in enumerate(self.rows):
            col = row.skip
            for cell in row.cells:
                while (row_index, col) in covered:
                    col += 1
                placements.append(CellPlacement(row_index, col, cell))
                for dr in range(cell.row_span):
                    for dc in range(cell.col_span):
                        covered.add((row_index + dr, col + dc))
                col += cell.col_span
        return placements

    def column_count(self) -> int:
        return max((p.col + p.cell.col_span for p in self.placements()), default=0)


class NestedTable(_Frozen):
    """A table inside a table cell, after the first after_line lines of the cell's text."""

    after_line: int
    table: TableBlock


TableCell.model_rebuild()
TableRow.model_rebuild()
TableBlock.model_rebuild()


class _LabeledBlock(_Block):
    """Common shape for blocks made of a left label and a right value."""

    size_pt: float | None = None
    layout: ParagraphLayout | None = None

    @abstractmethod
    def _fields(self) -> tuple[str, ...]: ...

    @abstractmethod
    def _with_fields(self, values: tuple[str, ...]) -> Self: ...

    def replace_text(self, before: str, after: str) -> Self | None:
        values = _replace_in_strings(self._fields(), before, after)
        return None if values is None else self._with_fields(values)

    def text(self) -> str:
        return "\t".join(self._fields())


class LabeledLineBlock(_LabeledBlock):
    """'Председатель комиссии:   Вальков И.В.' — a label followed by a value on one line."""

    kind: Literal["labeled_line"] = "labeled_line"
    label: str
    value: str

    def _fields(self) -> tuple[str, ...]:
        return (self.label, self.value)

    def _with_fields(self, values: tuple[str, ...]) -> Self:
        return self.model_copy(update={"label": values[0], "value": values[1]})


class TwoColumnLineBlock(_LabeledBlock):
    """One line with text pushed to the left and right edges, e.g. place and date."""

    kind: Literal["two_column_line"] = "two_column_line"
    left: str
    right: str

    def _fields(self) -> tuple[str, ...]:
        return (self.left, self.right)

    def _with_fields(self, values: tuple[str, ...]) -> Self:
        return self.model_copy(update={"left": values[0], "right": values[1]})


class SignatureLineBlock(_LabeledBlock):
    """'Председатель комиссии  ________  Вальков И.В.' — a place to sign."""

    kind: Literal["signature_line"] = "signature_line"
    label: str
    name: str = ""
    has_signature_mark: bool = Field(
        default=False, description="True if a handwritten signature is visible on the photo."
    )

    def _fields(self) -> tuple[str, ...]:
        return (self.label, self.name)

    def _with_fields(self, values: tuple[str, ...]) -> Self:
        return self.model_copy(update={"label": values[0], "name": values[1]})


class FillSlot(_Frozen):
    """One place to write on: printed text before the line, what is written on it, the small
    caption under it."""

    label: str = Field(default="", description="Printed text before the line: 'Руководитель'.")
    value: tuple[Run, ...] = Field(
        default=(), description="What is written on the line; empty if it is blank."
    )
    caption: str = Field(
        default="", description="Small text under the line: '(подпись)', '(ф.и.о.)'."
    )
    width: float = Field(default=1.0, description="Relative length of the line.")


class FillRowBlock(_Block):
    """A line of the form 'Руководитель ______ ______ ______' with captions '(должность)
    (подпись) (ф.и.о.)' under the lines; one slot is a single blank to fill in."""

    kind: Literal["fill_row"] = "fill_row"
    slots: tuple[FillSlot, ...]
    size_pt: float | None = None
    layout: ParagraphLayout | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )

    def replace_text(self, before: str, after: str) -> Self | None:
        for index, slot in enumerate(self.slots):
            changed: FillSlot | None = None
            if before in slot.label:
                changed = slot.model_copy(update={"label": slot.label.replace(before, after, 1)})
            elif (runs := _replace_in_runs(slot.value, before, after)) is not None:
                changed = slot.model_copy(update={"value": runs})
            elif before in slot.caption:
                changed = slot.model_copy(
                    update={"caption": slot.caption.replace(before, after, 1)}
                )
            if changed is not None:
                slots = (*self.slots[:index], changed, *self.slots[index + 1 :])
                return self.model_copy(update={"slots": slots})
        return None

    def text(self) -> str:
        parts = (
            part
            for slot in self.slots
            for part in (slot.label, plain_text(slot.value), slot.caption)
        )
        return " ".join(part for part in parts if part)


class RequisitesBlock(_Block):
    """Addressee/sender header in the top-right corner ('Генеральному директору ...')."""

    kind: Literal["requisites"] = "requisites"
    lines: tuple[str, ...] = Field(description="Logical lines, without the photo's line wraps.")
    align: Alignment | None = Field(
        default=None,
        description="'right' if every line is pushed to the right edge; null = a right column.",
    )
    size_pt: float | None = None
    font: str | None = Field(
        default=None, description="Typeface if recognisable: 'Times New Roman', 'Arial', ..."
    )
    spacing_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Space between letters, as Run.spacing_pt: a condensed block keeps its line breaks."""
    layout: ParagraphLayout | None = None

    def replace_text(self, before: str, after: str) -> Self | None:
        lines = _replace_in_strings(self.lines, before, after)
        return None if lines is None else self.model_copy(update={"lines": lines})

    def text(self) -> str:
        return "\n".join(self.lines)


class SpacerSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class EmptyLine(_Frozen):
    """One empty paragraph of the original: its spacing and line, and the size and typeface of
    its mark, which set how tall it is."""

    layout: ParagraphLayout
    size_pt: float
    font: str | None = None
    breaks: int = 0
    """Line breaks in it: each is one more line (an HTML page's <p><br></p>)."""
    clear: Literal["all", "left", "right"] | None = None
    """Its breaks send what follows below floating objects (w:clear), as Run.clear."""


class SpacerBlock(_Block):
    """Visible vertical gap that matters for the layout."""

    kind: Literal["spacer"] = "spacer"
    size: SpacerSize = SpacerSize.MEDIUM
    height_pt: float | None = None
    """Measured height of the gap, when known (imported documents); wins in faithful mode."""
    lines: tuple[EmptyLine, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """The empty paragraphs themselves: in faithful mode Word lays them out as in the original
    (spacing rules, page ends) instead of one paragraph of height_pt."""

    def replace_text(self, before: str, after: str) -> Self | None:
        return None

    def text(self) -> str:
        return ""


class ImageBlock(_Block):
    """A picture on the page: logo, stamp, photo, drawing. The pixels are not part of the model:
    they are cut from the photo by `bbox` or come with the source file (RenderExtras.images)."""

    kind: Literal["image"] = "image"
    description: str = Field(
        default="", description="What it shows, in Russian: 'логотип', 'печать', 'фото', 'схема'."
    )
    width_mm: float | None = Field(default=None, description="Approximate width on the page.")
    height_mm: float | None = Field(default=None, description="Approximate height on the page.")
    align: Alignment | None = None
    layout: ParagraphLayout | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    floating: ImagePlacement | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    crop: tuple[float, float, float, float] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Shares of the picture cut off at its left, top, right and bottom (Word's crop)."""
    effect_emu: tuple[int, int, int, int] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Room for a shadow or glow around the picture, left, top, right and bottom
    (wp:effectExtent): Word gives the line that much more height."""
    same_line: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    """Stands on the line of the picture before it: pictures side by side in one paragraph."""
    lead: str = Field(
        default="", description="Leave empty; set only when imported from a Word file."
    )
    """Spaces, tabs or line breaks before it: from the picture before it on the line, or from
    the start of its paragraph."""
    clear: bool = Field(
        default=False, description="Leave false; set only when imported from a Word file."
    )
    """A floating picture the text after waits below: a line break with 'clear' follows it."""

    def replace_text(self, before: str, after: str) -> Self | None:
        return None

    def text(self) -> str:
        return ""


class TextBoxBlock(_Block):
    """Text in a box floating at a fixed place on the page (Word's text box): a note in the
    margin, a 'М.П.' frame, a label beside a drawn line. It takes no room in the flow of text.
    Leave out: set only when imported from a Word file."""

    kind: Literal["text_box"] = "text_box"
    blocks: tuple["Block", ...] = ()
    width_mm: float
    height_mm: float
    floating: ImagePlacement
    framed: bool = False
    """A line drawn around the box."""
    padding: CellPadding | None = None
    """Space between the box's edge and its text."""
    rotation_deg: float = 0.0
    """Turned clockwise by this angle (-90: a bar up the page edge read from below)."""
    fill: str | None = None
    """Background colour as RRGGBB; null: none."""
    text_anchor: Literal["t", "ctr", "b"] = "t"
    """Where the text sits in the box: top, middle or bottom."""
    text_direction: str = "horz"
    """Word's text direction in the box: 'horz', 'vert', 'vert270', ..."""
    grows: bool = False
    """The box grows to fit its text (a:spAutoFit): Word sizes it so, whatever size it says."""

    def replace_text(self, before: str, after: str) -> Self | None:
        for index, block in enumerate(self.blocks):
            changed = block.replace_text(before, after)
            if changed is not None:
                blocks = (*self.blocks[:index], changed, *self.blocks[index + 1 :])
                return self.model_copy(update={"blocks": blocks})
        return None

    def text(self) -> str:
        return "\n".join(block.text() for block in self.blocks)


ArrowEnd = Literal["none", "triangle", "stealth", "arrow", "diamond", "oval"]
ShapeGeometry = Literal[
    "line",
    "rect",
    "roundRect",
    "ellipse",
    "triangle",
    "diamond",
    "rightArrow",
    "leftArrow",
    "upArrow",
    "downArrow",
    "custom",
]
"""Word's preset outlines a form or a flowchart draws; 'custom' is a free outline (path)."""


class ShapeBlock(_Block):
    """A line or a frame drawn at a fixed place (Word's shape): a rule to sign on, a box for a
    stamp, the lines of a form drawn over the page. Leave out: set only from a Word file."""

    kind: Literal["shape"] = "shape"
    geometry: ShapeGeometry
    width_mm: float
    height_mm: float
    floating: ImagePlacement
    flip_h: bool = False
    flip_v: bool = False
    """A line runs from corner to corner of its box; flipped, from the other corner."""
    line_pt: float = 0.75
    """0: no outline drawn."""
    color: str | None = None
    """RRGGBB of the line; None: black."""
    fill: str | None = None
    """RRGGBB inside the outline; None: see-through."""
    path: str | None = None
    """A free outline (geometry 'custom') as Word wrote it (a:custGeom)."""
    vml: str | None = None
    """An old-style shape (w:pict) as Word wrote it, drawn as it was: Word wraps the text around
    a thin one otherwise than around the same shape in DrawingML."""
    head: ArrowEnd = "none"
    tail: ArrowEnd = "none"
    """The ends of a line: an arrow of a flowchart points with its tail ('triangle')."""

    def replace_text(self, before: str, after: str) -> Self | None:
        return None

    def text(self) -> str:
        return ""


Block = Annotated[
    HeadingBlock
    | ParagraphBlock
    | ListItemBlock
    | TableBlock
    | LabeledLineBlock
    | TwoColumnLineBlock
    | SignatureLineBlock
    | RequisitesBlock
    | SpacerBlock
    | ImageBlock
    | FillRowBlock
    | TextBoxBlock
    | ShapeBlock,
    Field(discriminator="kind"),
]
TextBoxBlock.model_rebuild()


class CorrectionKind(StrEnum):
    REPLACE = "replace"
    INSERT = "insert"
    DELETE = "delete"


class CorrectionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Correction(_Frozen):
    """A handwritten edit over the printed text.

    Every kind is expressed as "replace `before` with `after`" inside one block:
    an insertion includes neighbouring printed text as an anchor, a deletion has
    an empty `after`.
    """

    id: str
    block_id: str
    kind: CorrectionKind = CorrectionKind.REPLACE
    before: str = Field(description="Printed text exactly as it appears in the block.")
    after: str = Field(description="Text after applying the handwritten edit.")
    bbox: BoundingBox | None = None
    confidence: float = 1.0
    status: CorrectionStatus = CorrectionStatus.PROPOSED


class FieldKind(StrEnum):
    DATE = "date"
    MONEY = "money"
    INN = "inn"
    PASSPORT = "passport"
    PHONE = "phone"
    EMAIL = "email"
    PERSON_NAME = "person_name"
    ADDRESS = "address"
    NUMBER = "number"


class ExtractedField(_Frozen):
    """A value worth double-checking by a human: dates, sums, ids, names."""

    kind: FieldKind
    value: str = Field(description="Exactly as printed.")
    block_id: str


class Suggestion(_Frozen):
    """A probable mistake in the original. Never applied automatically."""

    block_id: str
    text: str = Field(description="The suspicious fragment, exactly as printed.")
    proposal: str = Field(description="Suggested fix.")
    reason: str

    def as_correction(self, correction_id: str) -> "Correction":
        """Turn into a correction when the user chooses to fix the original's mistake."""
        return Correction(
            id=correction_id, block_id=self.block_id, before=self.text, after=self.proposal
        )


class DocumentTypeGuess(_Frozen):
    id: str = Field(description="Id from the document type catalog, or 'other'.")
    title: str = Field(description="Human title of this specific document, in Russian.")
    confidence: float


class Orientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class SpacingRule(StrEnum):
    """How Word combines the spacing after one paragraph with the spacing before the next."""

    LARGER = "larger"  # the larger of the two: Word's default
    SUM = "sum"  # both: documents with 'Don't use HTML paragraph auto spacing'


class PageNumbers(_Frozen):
    """Page numbers printed in the top or bottom margin."""

    position: Literal["top", "bottom"] = "bottom"
    align: Alignment = Alignment.CENTER
    first_page: bool = Field(
        default=True, description="False when the first page shows no number (a title page)."
    )
    frame: tuple[tuple[str, str], ...] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The number stands in a frame (w:framePr), as written: it takes no line of the margin."""
    size_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    font: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    layout: ParagraphLayout | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The number's line as the original sets it: its spacing lifts it off the page's edge."""


class FontFace(_Frozen):
    """How the original describes a typeface (w:font): Word picks a stand-in by these when the
    face is not installed, a swiss one for Liberation Sans, a roman one for PT Astra Serif."""

    name: str
    family: str | None = None
    panose: str | None = None
    charset: str | None = None
    pitch: str | None = None
    alt_name: str | None = None
    signature: tuple[tuple[str, str], ...] = ()
    """w:sig: the scripts the face covers; Word picks the stand-in for Cyrillic by it."""
    not_true_type: bool = False


class FootnoteParagraph(_Frozen):
    runs: tuple[Run, ...] = ()
    layout: ParagraphLayout | None = None
    align: Alignment | None = None


class Footnote(_Frozen):
    """A note at the foot of the page, referred to by a run with footnote=id in the text."""

    id: int
    paragraphs: tuple[FootnoteParagraph, ...] = ()


class Document(_Frozen):
    schema_version: Literal["1.0"] = "1.0"
    document_type: DocumentTypeGuess
    alternative_types: tuple[DocumentTypeGuess, ...] = ()
    orientation: Orientation = Orientation.PORTRAIT
    page: PageGeometry | None = Field(
        default=None, description="Page size and margins of the original, if known."
    )
    font: str | None = Field(
        default=None,
        description="Main typeface as seen: 'Times New Roman' (serif) or 'Arial' (sans-serif).",
    )
    page_numbers: PageNumbers | None = Field(
        default=None, description="Page numbers in the margin, if the page shows one; else null."
    )
    spacing_rule: SpacingRule | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    compat_mode: int | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """Word version whose layout the original keeps (14: Word 2010, 15: Word 2013 and later);
    the same text breaks into lines differently in them."""
    compat_switches: tuple[str, ...] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The original's layout switches of older Words (w:compat), in their order."""
    compat_settings: tuple[tuple[str, str], ...] | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The original's newer switches (w:compatSetting, but the mode): name and value."""
    default_tab_pt: float | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    hyphenation: tuple[tuple[str, str], ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """Word's automatic hyphenation settings as written (w:autoHyphenation, w:hyphenationZone,
    ...): name and value; empty: no hyphenation."""
    language: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The document's default language (w:lang, 'ru-RU'): Word hyphenates by its rules."""
    page_background: str | None = Field(
        default=None, description="Leave null; set only when imported from a Word file."
    )
    """The colour of the whole page (w:background), RRGGBB: a poster on light blue."""
    fonts: tuple[FontFace, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    footnotes: tuple[Footnote, ...] = Field(
        default=(), description="Leave empty; set only when imported from a Word file."
    )
    """Step of Word's default tab stops: 35.4 pt (1.25 cm) in Russian files, 36 pt in ours."""
    blocks: tuple[Block, ...]
    header: tuple[Block, ...] = Field(
        default=(), description="Blocks in the top margin repeated on every page (letterhead)."
    )
    footer: tuple[Block, ...] = Field(
        default=(), description="Blocks in the bottom margin repeated on every page."
    )
    corrections: tuple[Correction, ...] = ()
    fields: tuple[ExtractedField, ...] = ()
    suggestions: tuple[Suggestion, ...] = ()

    def block_index(self, block_id: str) -> int | None:
        return next((i for i, block in enumerate(self.blocks) if block.id == block_id), None)

    def iter_text(self) -> Iterator[str]:
        for block in self.blocks:
            yield block.text()

    def with_block_text(self, block_id: str, text: str) -> "Document":
        """Replace the text of a heading, paragraph or list item typed by the user."""
        index = self.block_index(block_id)
        if index is None:
            raise KeyError(block_id)
        block = self.blocks[index]
        if not isinstance(block, _RunsBlock):
            raise TypeError(f"Block '{block_id}' ({block.kind}) has no editable text")
        bold = bool(block.runs) and all(run.bold for run in block.runs)
        edited = block.model_copy(update={"runs": (Run(text=text, bold=bold),)})
        blocks = (*self.blocks[:index], edited, *self.blocks[index + 1 :])
        return self.model_copy(update={"blocks": blocks})
