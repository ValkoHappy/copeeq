"""Fitting the layout by rendering: build the Word file, see where each block landed, move it.

Measured sizes and gaps are close but small errors add up down the page. The rendering is
deterministic, so the fix needs no model: render, find each block on our own page (by its text,
in the PDF's exact text positions), compare with where it is on the photo, change the space
above it by the difference — what is left after the moves above — and render again.
"""

from collections.abc import Sequence

from foto2word.application.ports import DocumentRenderer, Previewer
from foto2word.domain.document import Block, Document, ParagraphLayout, SpacerBlock
from foto2word.domain.extras import NO_EXTRAS, RenderExtras
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine, anchor
from foto2word.domain.profile import Profile, RenderMode
from foto2word.infrastructure.layout.pdf_lines import pdf_lines

_PT_PER_MM = 72 / 25.4
_A4_HEIGHT_MM = 297.0
_TOLERANCE_PT = 1.0
"""Differences below this are reading noise, not layout errors."""
_MIN_SPACER_PT = 1.0


class RenderLayoutFitter:
    def __init__(self, renderer: DocumentRenderer, previewer: Previewer, rounds: int = 2) -> None:
        self._renderer = renderer
        self._previewer = previewer
        self._rounds = rounds

    def fit(
        self,
        document: Document,
        pages: Sequence[PageImage],
        lines: Sequence[TextLine],
        profile: Profile,
        extras: RenderExtras = NO_EXTRAS,
    ) -> Document:
        """`lines` are the photo's OCR lines; without them the blocks' boxes give the targets."""
        height = (document.page.height_mm if document.page else _A4_HEIGHT_MM) * _PT_PER_MM
        targets = _tops(document.blocks, lines, height) if lines else _box_tops(document, height)
        if not targets or not pages:
            return document
        for _ in range(self._rounds):
            rendered = self._renderer.render(document, profile, RenderMode.FAITHFUL, extras)
            placed = _tops(
                document.blocks, pdf_lines(self._previewer.to_pdf(rendered), (1,)), height
            )
            moved = _move(document, targets, placed)
            if moved is document:
                break
            document = moved
        return document


def _tops(blocks: Sequence[Block], lines: Sequence[TextLine], height_pt: float) -> dict[str, float]:
    """Top of each block's first line on page 1, in points from the top of the page."""
    return {
        block_id: lines[indexes[0]].box.y0 * height_pt
        for block_id, indexes in anchor(blocks, lines).items()
        if indexes and lines[indexes[0]].page == 1
    }


def _box_tops(document: Document, height_pt: float) -> dict[str, float]:
    return {
        block.id: min(block.bbox.y0, block.bbox.y1) * height_pt
        for block in document.blocks
        if block.bbox is not None and block.page == 1 and block.text()
    }


def _move(document: Document, targets: dict[str, float], placed: dict[str, float]) -> Document:
    """Each block moved by what is still wrong after the moves of the blocks above it."""
    blocks = list(document.blocks)
    shift = 0.0
    changed = False
    for index, block in enumerate(blocks):
        if block.id not in targets or block.id not in placed:
            continue
        need = targets[block.id] - placed[block.id] - shift
        if abs(need) < _TOLERANCE_PT:
            continue
        applied = _space_above(blocks, index, need)
        if applied:
            shift += applied
            changed = True
    return document.model_copy(update={"blocks": tuple(blocks)}) if changed else document


def _space_above(blocks: list[Block], index: int, need: float) -> float:
    """Change the gap above block `index` by `need` points; returns what could be applied."""
    previous = blocks[index - 1] if index else None
    if isinstance(previous, SpacerBlock):
        height = previous.height_pt or 0.0
        new = max(height + need, _MIN_SPACER_PT)
        blocks[index - 1] = previous.model_copy(update={"height_pt": round(new, 1)})
        return new - height
    block = blocks[index]
    layout = getattr(block, "layout", None)
    if not isinstance(layout, ParagraphLayout):
        return 0.0
    before = layout.space_before_pt or 0.0
    new = max(before + need, 0.0)
    blocks[index] = block.model_copy(
        update={"layout": layout.model_copy(update={"space_before_pt": round(new, 1)})}
    )
    return new - before
