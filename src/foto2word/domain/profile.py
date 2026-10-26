"""Formatting profiles: how a document of a given type should look."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from foto2word.domain.document import Alignment, CellBorders, TabStop


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RenderMode(StrEnum):
    FAITHFUL = "faithful"
    """Keep alignment and layout as seen on the photo; fonts and page come from the profile."""
    STANDARD = "standard"
    """Apply the profile completely, ignoring the photo's layout."""


class Margins(_Frozen):
    top_mm: float
    bottom_mm: float
    left_mm: float
    right_mm: float


class PageSetup(_Frozen):
    width_mm: float = 210.0
    height_mm: float = 297.0
    margins: Margins

    @property
    def content_width_mm(self) -> float:
        return self.width_mm - self.margins.left_mm - self.margins.right_mm


class TextStyle(_Frozen):
    font: str = "Times New Roman"
    size_pt: float = 14.0
    bold: bool = False
    italic: bool = False
    all_caps: bool = False
    align: Alignment = Alignment.JUSTIFY
    first_line_indent_mm: float = 0.0
    left_indent_mm: float = 0.0
    right_indent_mm: float = 0.0
    line_spacing: float = 1.0
    line_pt: float | None = None
    """Exact (or, with line_at_least, minimum) line height; overrides line_spacing."""
    line_at_least: bool = False
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    tabs: tuple[TabStop, ...] = ()
    borders: CellBorders | None = None
    shading: str | None = None
    keep_next: bool = False
    keep_lines: bool = False
    mark_size_pt: float | None = None
    mark_font: str | None = None
    frame: tuple[tuple[str, str], ...] | None = None
    off_grid: bool = False
    no_hyphens: bool = False


class StyleSheet(_Frozen):
    body: TextStyle
    title: TextStyle
    subtitle: TextStyle
    list_item: TextStyle
    note: TextStyle
    table: TextStyle
    requisites: TextStyle
    line: TextStyle
    """Single-line layouts: labeled lines, two-column lines, signatures."""

    def with_font(self, font: str) -> "StyleSheet":
        """The same sheet with one typeface everywhere (the one seen on the photo)."""
        return self.model_copy(
            update={
                name: getattr(self, name).model_copy(update={"font": font})
                for name in type(self).model_fields
            }
        )


class Profile(_Frozen):
    id: str
    title: str
    applies_to: tuple[str, ...] = Field(
        default=(), description="Document type ids this profile is chosen for."
    )
    page: PageSetup
    styles: StyleSheet
    list_indent_mm: float = 10.0
    """Extra left indent per list nesting level."""
