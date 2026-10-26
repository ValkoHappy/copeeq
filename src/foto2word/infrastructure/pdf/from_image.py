"""A page picture read into the same content a PDF gives (reader.PageContent): words with their
place from an OCR engine, the typeface, size and boldness each line's words are set in, and the
lines drawn on the page found in its ink. The assembly is then the PDF's own.

What the PDF taught: an OCR word box is the ink of its letters, so its height says little (an
'о' is half as tall as a 'Б'); the width of a known word in a known face is precise. For every
face the words of a line give a size from their widths and one from their ink heights; the face
where both agree is the one, its size the line's.
"""

from collections.abc import Sequence
from io import BytesIO
from statistics import median

import cv2
import numpy as np
from PIL import Image

from foto2word.domain.document import BoundingBox, ImageBlock, ImagePlacement
from foto2word.domain.ocr import TextWord
from foto2word.infrastructure.layout.metrics import FAMILIES, TextMetrics
from foto2word.infrastructure.pdf.reader import _PT_PER_MM, PageContent, _Char, _merged
from foto2word.infrastructure.pdf.tables import Rule

_METRICS = TextMetrics()
_INK = 160
"""Grey values darker than this are ink."""
_LONG_PT = 24.0
"""A horizontal run of ink longer than this many points is a drawn line, not a letter."""
_TALL_PT = 14.0
"""A vertical run of ink taller than this many points is a drawn line."""
_THICK_PT = 3.0
WINDOWS_OCR_BOXES = (0.987, 1.035)
"""A Windows OCR word box against the ink of the same word in the same face and size
(measured on 455 words of PDFs whose faces and sizes are known, drawn at 200 dpi): 1.3 %
narrower, 3.5 % taller. Uncorrected, the right face looked 5 % off and a wrong one could fit
better. Another OCR engine has boxes of its own."""


def page_content(
    image: Image.Image,
    words: Sequence[TextWord],
    width_pt: float,
    height_pt: float,
    *,
    page: int = 1,
    images: dict[str, bytes] | None = None,
    boxes: tuple[float, float] = WINDOWS_OCR_BOXES,
) -> PageContent:
    """The page's characters, lines and pictures as a PDF would give them. `boxes`: how the
    OCR engine's word boxes compare with the ink, width and height; the pictures' pixels go to
    `images` by the id of their block."""
    rgb = np.asarray(image.convert("RGB"))
    scale = width_pt / rgb.shape[1]  # points per pixel
    rules, drawn = _ink_rules(rgb, scale)
    regions = _picture_regions(rgb, words, drawn, scale)
    kept = [_ink_box(w, boxes) for w in words if not _within(w.box, regions, rgb.shape)]
    rules = [rule for rule in rules if not any(_holds(region, rule, scale) for region in regions)]
    chars: list[_Char] = []
    by_line: dict[int, list[TextWord]] = {}
    for word in kept:
        by_line.setdefault(word.line, []).append(word)
    family = _family(kept, width_pt, height_pt)
    for line in by_line.values():
        ordered = sorted(line, key=lambda w: w.box.x0)
        chars += _line_chars(ordered, family, rgb, width_pt, height_pt)
    pictures = _pictures(image, regions, scale, page, images if images is not None else {})
    return PageContent(width_pt, height_pt, chars, _merged(rules), pictures)


def _ink_box(word: TextWord, boxes: tuple[float, float]) -> TextWord:
    """The word's box made as wide and as tall as its ink."""
    wide, tall = boxes
    middle_x, middle_y = (word.box.x0 + word.box.x1) / 2, (word.box.y0 + word.box.y1) / 2
    half_w = (word.box.x1 - word.box.x0) / wide / 2
    half_h = (word.box.y1 - word.box.y0) / tall / 2
    box = word.box.model_copy(
        update={
            "x0": middle_x - half_w,
            "x1": middle_x + half_w,
            "y0": middle_y - half_h,
            "y1": middle_y + half_h,
        }
    )
    return word.model_copy(update={"box": box})


def _line_chars(
    words: list[TextWord],
    family: str,
    rgb: np.ndarray,
    width_pt: float,
    height_pt: float,
) -> list[_Char]:
    _, guess = _weight_and_size(words, family, width_pt, height_pt)
    px = rgb.shape[1] / width_pt
    found = [_word_bold(word, family, guess * px, rgb) for word in words]
    line_bold = sum(1 for b in found if b) > sum(1 for b in found if b is False)
    weights = [line_bold if bold is None else bold for bold in found]
    size = _size(words, weights, family, width_pt, guess)
    base = median(
        word.box.y1 * height_pt
        - (
            TextMetrics.below_baseline_em(word.text, family, bold) * size
            if TextMetrics.available(family, bold)
            else 0.0
        )
        for word, bold in zip(words, weights, strict=True)
    )
    chars: list[_Char] = []
    for index, (word, bold) in enumerate(zip(words, weights, strict=True)):
        x0, x1 = word.box.x0 * width_pt, word.box.x1 * width_pt
        look = {
            "size": size,
            "family": family,
            "bold": bold,
            "color": _colour(word, rgb),
            "background": _background(word, rgb),
        }
        if index:  # the space between this word and the one before
            chars.append(_char(" ", chars[-1].x1, x0, base, **look))  # type: ignore[arg-type]
        total = _METRICS.width_pt(word.text, size, family, bold) or 1.0
        scale = (x1 - x0) / total
        position = x0
        for letter in word.text:
            advance = _METRICS.width_pt(letter, size, family, bold) * scale
            chars.append(_char(letter, position, position + advance, base, **look))  # type: ignore[arg-type]
            position += advance
    return chars


def _word_bold(word: TextWord, family: str, size_px: float, rgb: np.ndarray) -> bool | None:
    """Whether the word is bold: its box is as dark as the word set bold, not regular (bold
    strokes darken a quarter more of it: 455 words of known PDFs, all told apart). None for a
    single letter or no bold face to compare with."""
    text = word.text.strip()
    if len(text) < 2 or not TextMetrics.available(family, True):  # noqa: PLR2004
        return None
    height, width = rgb.shape[:2]
    crop = rgb[
        int(word.box.y0 * height) : int(word.box.y1 * height) + 1,
        int(word.box.x0 * width) : int(word.box.x1 * width) + 1,
    ]
    if crop.size == 0:
        return None
    seen = float(_ink(crop)[0].mean())
    regular = TextMetrics.ink_share(text, family, False, size_px)
    bold = TextMetrics.ink_share(text, family, True, size_px)
    if seen <= 0 or regular <= 0 or bold <= 0:
        return None
    return bool(abs(np.log(seen / bold)) < abs(np.log(seen / regular)))


def _size(
    words: list[TextWord], weights: list[bool], family: str, width_pt: float, guess: float
) -> float:
    """The line's size from its words' widths, each in its own weight."""
    sizes = [
        (word.box.x1 - word.box.x0) * width_pt / ink
        for word, bold in zip(words, weights, strict=True)
        if len(word.text.strip()) >= 2  # noqa: PLR2004
        and TextMetrics.available(family, bold)
        and (ink := TextMetrics.ink_width_em(word.text.strip(), family, bold)) > 0
    ]
    return round(median(sizes) * 2) / 2 if sizes else guess


def _char(
    text: str,
    x0: float,
    x1: float,
    base: float,
    *,
    size: float,
    family: str,
    bold: bool,
    color: str | None = None,
    background: str | None = None,
) -> _Char:
    return _Char(
        text=text,
        x0=x0,
        x1=max(x1, x0),
        top=base - 0.75 * size,
        bottom=base + 0.25 * size,
        base=base,
        size=size,
        font=family,
        bold=bold,
        italic=False,
        color=color,
        background=background,
    )


def _sizes(
    words: Sequence[TextWord], family: str, bold: bool, width_pt: float, height_pt: float
) -> list[tuple[float, float]]:
    """Each word's size as its width says and as its ink height says, set in this face."""
    found = []
    for word in words:
        text = word.text.strip()
        if len(text) < 2:  # noqa: PLR2004 - one letter says little
            continue
        width = TextMetrics.ink_width_em(text, family, bold)
        ink = TextMetrics.ink_height_em(text, family, bold)
        if width > 0 and ink > 0:
            found.append(
                (
                    (word.box.x1 - word.box.x0) * width_pt / width,
                    (word.box.y1 - word.box.y0) * height_pt / ink,
                )
            )
    return found


def _disagreement(sizes: list[tuple[float, float]]) -> float:
    return median(abs(by_width / by_height - 1) for by_width, by_height in sizes)


def _family(words: list[TextWord], width_pt: float, height_pt: float) -> str:
    """The page's face: the one in which the words of each line take one size by their widths
    (in another face the sizes scatter: 'предоставлении' and 'отпуска' 14.0 and 14.2 pt in
    Times, 13.6 and 14.6 in Calibri), and their widths and heights agree."""
    lines: dict[int, list[TextWord]] = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)
    scores = {}
    for family in FAMILIES:
        if not TextMetrics.available(family):
            continue
        sizes = _sizes(words, family, False, width_pt, height_pt)
        if not sizes:
            continue
        scatter = []
        for line in lines.values():
            widths = [w for w, _ in _sizes(line, family, False, width_pt, height_pt)]
            if len(widths) > 1:
                middle = median(widths)
                scatter.append(median(abs(w / middle - 1) for w in widths))
        scores[family] = _disagreement(sizes) + (median(scatter) if scatter else 0.0)
    return min(scores, key=lambda f: scores[f]) if scores else "Times New Roman"


def _weight_and_size(
    words: list[TextWord], family: str, width_pt: float, height_pt: float
) -> tuple[bool, float]:
    """Bold or not, and the size, of a line in the page's face."""
    best: tuple[float, bool, float] | None = None
    for bold in (False, True):
        if not TextMetrics.available(family, bold):
            continue
        sizes = _sizes(words, family, bold, width_pt, height_pt)
        if sizes:
            error = _disagreement(sizes)
            if best is None or error < best[0]:
                best = (error, bold, median(s for s, _ in sizes))
    if best is None:
        height = median((w.box.y1 - w.box.y0) * height_pt for w in words)
        return False, round(height / 0.7 * 2) / 2
    return best[1], round(best[2] * 2) / 2


def _ink_rules(rgb: np.ndarray, scale: float) -> tuple[list[Rule], np.ndarray]:
    """Straight lines in the ink: long thin horizontal and vertical runs; and the pixels they
    take."""
    ink = (rgb.mean(axis=2) < _INK).astype(np.uint8)
    drawn = np.zeros_like(ink)
    rules: list[Rule] = []
    for horizontal in (True, False):
        length = max(int((_LONG_PT if horizontal else _TALL_PT) / scale), 3)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (length, 1) if horizontal else (1, length)
        )
        lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
        drawn = np.maximum(drawn, lines)
        count, _, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
        for index in range(1, count):
            x, y, w, h, _ = stats[index]
            thick = (h if horizontal else w) * scale
            if thick > _THICK_PT:
                continue  # a filled area, not a line
            if horizontal:
                middle = (y + h / 2) * scale
                end = (x + w) * scale
                rules.append(Rule(x * scale, middle, end, middle, max(thick, 0.25), None))
            else:
                middle = (x + w / 2) * scale
                end = (y + h) * scale
                rules.append(Rule(middle, y * scale, middle, end, max(thick, 0.25), None))
    return rules, drawn


_MARK = 235
"""Pixels darker than this in any colour are marks on the page (a light photo too)."""
_PICTURE_PT = 30.0
"""A picture is at least this many points wide and tall."""
_GLUE_PT = 6.0
"""Marks closer than this many points belong to one picture."""

Region = tuple[int, int, int, int]
"""A picture's place in pixels: x0, y0, x1, y1."""


def _picture_regions(
    rgb: np.ndarray, words: Sequence[TextWord], drawn: np.ndarray, scale: float
) -> list[Region]:
    """Where pictures are: marks that are neither words nor drawn lines, glued together, at
    least a centimetre across."""
    height, width = rgb.shape[:2]
    marks = (rgb.min(axis=2) < _MARK).astype(np.uint8)
    marks[drawn > 0] = 0
    for word in words:
        marks[
            max(int(word.box.y0 * height) - 2, 0) : int(word.box.y1 * height) + 3,
            max(int(word.box.x0 * width) - 2, 0) : int(word.box.x1 * width) + 3,
        ] = 0
    glue = max(int(_GLUE_PT / scale), 1)
    joined = cv2.dilate(marks, np.ones((glue, glue), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    least = _PICTURE_PT / scale
    regions = []
    for index in range(1, count):
        x, y, w, h, _ = stats[index]
        if w >= least and h >= least:
            regions.append((int(x), int(y), int(x + w), int(y + h)))
    return regions


def _within(box: BoundingBox, regions: list[Region], shape: tuple[int, ...]) -> bool:
    height, width = shape[:2]
    x, y = (box.x0 + box.x1) / 2 * width, (box.y0 + box.y1) / 2 * height
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in regions)


def _holds(region: Region, rule: Rule, scale: float) -> bool:
    x0, y0, x1, y1 = (v * scale for v in region)
    return x0 <= rule.x0 and rule.x1 <= x1 and y0 <= rule.y0 and rule.y1 <= y1


def _pictures(
    image: Image.Image, regions: list[Region], scale: float, page: int, images: dict[str, bytes]
) -> list[ImageBlock]:
    """The pictures cut from the page, floating behind the text where they stand."""
    found = []
    for index, (x0, y0, x1, y1) in enumerate(regions):
        data = BytesIO()
        image.crop((x0, y0, x1, y1)).save(data, format="PNG")
        block_id = f"i{page}-{index}"
        images[block_id] = data.getvalue()
        found.append(
            ImageBlock(
                id=block_id,
                page=page,
                width_mm=round((x1 - x0) * scale / _PT_PER_MM, 2),
                height_mm=round((y1 - y0) * scale / _PT_PER_MM, 2),
                floating=ImagePlacement(
                    horizontal_from="page",
                    x_mm=round(x0 * scale / _PT_PER_MM, 2),
                    vertical_from="page",
                    y_mm=round(y0 * scale / _PT_PER_MM, 2),
                    wrap="none",
                    behind_text=True,
                ),
            )
        )
    return found


_BLACKISH = 60
"""A word whose ink is further than this from black in some channel has a colour of its own."""
_CONTRAST = 50
"""Ink is at least this much darker than the paper or highlight behind the word."""
_WHITE = 235


def _crop(word: TextWord, rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    return rgb[
        int(word.box.y0 * height) : int(word.box.y1 * height) + 1,
        int(word.box.x0 * width) : int(word.box.x1 * width) + 1,
    ]


def _ink(crop: np.ndarray) -> tuple[np.ndarray, float]:
    """Which pixels of a word's box are ink, and the brightness of what lies behind it: ink is
    darker than its own background, so a yellow highlight is not ink (527fca78)."""
    light = crop.mean(axis=-1)
    behind = float(np.percentile(light, 90)) if light.size else 255.0
    return light < min(_INK, behind - _CONTRAST), behind


def _colour(word: TextWord, rgb: np.ndarray) -> str | None:
    """The colour of the word's ink, unless it is black."""
    crop = _crop(word, rgb)
    if crop.size == 0:
        return None
    mask, _ = _ink(crop)
    ink = crop[mask]
    if len(ink) == 0:
        return None
    r, g, b = (int(v) for v in np.median(ink, axis=0))
    if max(r, g, b) <= _BLACKISH:
        return None
    return f"{r:02X}{g:02X}{b:02X}"


def _background(word: TextWord, rgb: np.ndarray) -> str | None:
    """The colour behind the word when it is not the white page: a highlighter mark."""
    crop = _crop(word, rgb)
    if crop.size == 0:
        return None
    mask, behind = _ink(crop)
    if behind >= _WHITE:
        return None
    paper = crop[~mask]
    if len(paper) == 0:
        return None
    r, g, b = (int(v) for v in np.median(paper, axis=0))
    return f"{r:02X}{g:02X}{b:02X}"
