"""Text lines of a PDF page with their exact place: what a perfect OCR would return.

Used to find where blocks ended up on our own rendering (the layout fit) and, in the bench, as
the OCR lines of an original whose PDF is known.
"""

from itertools import pairwise

import pypdfium2

from foto2word.domain.document import BoundingBox
from foto2word.domain.ocr import TextLine

_SAME_ROW = 0.5
_BLANK_DROP = 0.5
"""A blank or a comma may lie this many line heights below the letters of its line."""
_WORD_GAP = 0.15
_LINE_GAP = 2.5
"""Pieces further apart than this many heights are separate lines."""
"""A gap between pieces wider than this share of their height is a space."""
_Piece = tuple[float, float, float, float, str]
"""Pieces whose vertical overlap is more than half their height are on one line."""


def pdf_lines(pdf: bytes, page_numbers: tuple[int, ...] = ()) -> list[TextLine]:
    """Lines of the given pages (all when empty), in reading order on each page."""
    document = pypdfium2.PdfDocument(pdf)
    try:
        wanted = page_numbers or tuple(range(1, len(document) + 1))
        found: list[TextLine] = []
        for number in wanted:
            if 0 < number <= len(document):
                found += _page_lines(document[number - 1], number)
        return found
    finally:
        document.close()


def _page_lines(page: pypdfium2.PdfPage, number: int) -> list[TextLine]:
    width, height = page.get_size()
    text = page.get_textpage()
    pieces: list[_Piece] = []
    for index in range(text.count_rects()):
        left, bottom, right, top = text.get_rect(index)
        content = text.get_text_bounded(left, bottom, right, top)
        if content.strip():
            pieces.append((left, height - top, right, height - bottom, content))
    lines = []
    for row in _rows(pieces):
        box = BoundingBox(
            x0=min(p[0] for p in row) / width,
            y0=min(p[1] for p in row) / height,
            x1=max(p[2] for p in row) / width,
            y1=max(p[3] for p in row) / height,
        )
        lines.append(TextLine(page=number, text=_joined(row), box=box))
    return sorted(lines, key=lambda line: (line.box.y0, line.box.x0))


def _rows(pieces: list[_Piece]) -> list[list[_Piece]]:
    """Pieces grouped into lines, each in reading order. Blanks '____' and punctuation sit low,
    under the boxes of letters without tails: they join the line of letters they touch most."""
    rows: list[list[_Piece]] = []
    marks = [p for p in pieces if _mark(p)]
    for piece in sorted((p for p in pieces if not _mark(p)), key=lambda p: p[1]):
        row = next(
            (r for r in rows if _overlap(r, piece) > _SAME_ROW * (piece[3] - piece[1])), None
        )
        if row is None:
            rows.append([piece])
        else:
            row.append(piece)
    for mark in marks:
        near = [r for r in rows if _overlap(r, mark) > -_BLANK_DROP * _height(r)]
        if near:
            max(near, key=lambda r: _overlap(r, mark)).append(mark)
        else:
            rows.append([mark])
    return [part for whole in rows for part in _split(whole)]


def _mark(piece: _Piece) -> bool:
    """Blanks and punctuation: no letter or digit to tell the line by."""
    return not any(ch.isalnum() for ch in piece[4])


def _height(row: list[_Piece]) -> float:
    return max(p[3] for p in row) - min(p[1] for p in row)


def _split(row: list[_Piece]) -> list[list[_Piece]]:
    """A row cut where pieces are far apart, as an OCR engine splits lines: the next table
    cell, the right-hand column."""
    ordered = sorted(row, key=lambda p: p[0])
    parts = [[ordered[0]]]
    for before, piece in pairwise(ordered):
        tall = max(piece[3] - piece[1], before[3] - before[1])  # a blank is flat
        if piece[0] - before[2] > _LINE_GAP * tall:
            parts.append([piece])
        else:
            parts[-1].append(piece)
    return parts


def _joined(row: list[_Piece]) -> str:
    """Pieces of one line: a space where there is a gap or a piece carries one at its edge."""
    text = row[0][4].strip()
    for before, piece in pairwise(row):
        gap = piece[0] - before[2]
        spaced = before[4][-1:].isspace() or piece[4][:1].isspace()
        text += " " if spaced or gap > _WORD_GAP * (piece[3] - piece[1]) else ""
        text += piece[4].strip()
    return text


def _overlap(row: list[_Piece], piece: _Piece) -> float:
    top = max(min(p[1] for p in row), piece[1])
    bottom = min(max(p[3] for p in row), piece[3])
    return float(bottom - top)
