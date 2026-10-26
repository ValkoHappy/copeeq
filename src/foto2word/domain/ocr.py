"""Text lines a classic OCR engine reads off a page photo — what is written and exactly where —
and their link to the blocks a vision model returned.

Vision-language models read and structure documents well but place boxes poorly (GPT-class
models especially). An OCR engine places lines precisely but knows nothing of the structure.
They meet on the text: each block of the model is found in the stream of OCR lines by its words,
so geometry never depends on the model's boxes.
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz

from foto2word.domain.document import Block, BoundingBox

_NOT_TEXT = re.compile(r"[\W_]+")
_MIN_SCORE = 75.0
_MIN_CHARS = 2
_WINDOW_SLACK = 200


class TextLine(BaseModel):
    """One line of text on a page photo as an OCR engine reads it."""

    model_config = ConfigDict(frozen=True)

    page: int
    text: str
    box: BoundingBox


class TextWord(BaseModel):
    """One word on a page photo as an OCR engine reads it, with the line it belongs to."""

    model_config = ConfigDict(frozen=True)

    page: int
    line: int
    text: str
    box: BoundingBox


def anchor(blocks: Sequence[Block], lines: Sequence[TextLine]) -> dict[str, list[int]]:
    """For each block, the indexes of the OCR lines that carry its text.

    Blocks are looked for in reading order, each after the previous one; a block not found there
    (another column, another order) is looked for in the whole page. A line may serve two blocks
    when the OCR joined them into one line.
    """
    stream: list[str] = []
    owner: list[int] = []
    for index, line in enumerate(lines):
        text = _squash(line.text)
        stream.append(text)
        owner += [index] * len(text)
    joined = "".join(stream)
    found: dict[str, list[int]] = {}
    cursor = 0
    for block in blocks:
        text = _squash(block.text())
        if len(text) < _MIN_CHARS:
            continue
        span = _find(text, joined, cursor)
        if span is None:
            continue
        start, end = span
        found[block.id] = sorted(set(owner[start:end]))
        cursor = end
    return found


def _find(text: str, stream: str, cursor: int) -> tuple[int, int] | None:
    window_end = min(cursor + len(text) * 2 + _WINDOW_SLACK, len(stream))
    for start, end in ((cursor, window_end), (0, len(stream))):
        if end - start < _MIN_CHARS:
            continue
        hit = fuzz.partial_ratio_alignment(text, stream[start:end])
        if hit is not None and hit.score >= _MIN_SCORE and hit.dest_end > hit.dest_start:
            return start + hit.dest_start, start + hit.dest_end
    return None


def _squash(text: str) -> str:
    """Letters and digits only: OCR and the model differ in spaces, quotes and blanks."""
    return _NOT_TEXT.sub("", text).casefold()
