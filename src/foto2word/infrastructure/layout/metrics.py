"""Text widths from the real typefaces: the most precise clue to the font size on a photo.

The ink height of a line depends on its letters and is a pixel or two at phone resolution; the
width of a known text is hundreds of pixels. Knowing what the line says (the model read it), the
size is the one at which this text, set in Times or Arial, takes the width it takes on the page.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_REFERENCE_PX = 200
_DARK = 160
"""Grey values darker than this count as ink, as on a scan."""
_DIRS = (
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path("/usr/share/fonts"),
    Path("/Library/Fonts"),
)
_FILES = {
    ("Times New Roman", False): ("times.ttf", "LiberationSerif-Regular.ttf"),
    ("Times New Roman", True): ("timesbd.ttf", "LiberationSerif-Bold.ttf"),
    ("Arial", False): ("arial.ttf", "LiberationSans-Regular.ttf"),
    ("Arial", True): ("arialbd.ttf", "LiberationSans-Bold.ttf"),
    ("Calibri", False): ("calibri.ttf", "Carlito-Regular.ttf"),
    ("Calibri", True): ("calibrib.ttf", "Carlito-Bold.ttf"),
}
FAMILIES = ("Times New Roman", "Arial", "Calibri")
"""Times first: the usual typeface of Russian documents. Calibri: Word's default of 2007-2023."""


@dataclass(frozen=True, slots=True)
class Wrapped:
    lines: int
    last_pt: float
    """Width of the last line."""


@lru_cache(maxsize=8)
def _font(family: str, bold: bool) -> ImageFont.FreeTypeFont | None:
    for name in _FILES.get((family, bold), ()):
        for directory in _DIRS:
            path = directory / name
            if path.is_file():
                return ImageFont.truetype(str(path), _REFERENCE_PX)
    return None


class TextMetrics:
    """Widths of text in points at a given size, from TrueType files on this machine."""

    @staticmethod
    def available(family: str, bold: bool = False) -> bool:
        return _font(family, bold) is not None

    @staticmethod
    def width_pt(text: str, size_pt: float, family: str, bold: bool = False) -> float:
        font = _font(family, bold)
        if font is None:
            raise LookupError(f"No TrueType file for {family}")
        return font.getlength(text) / _REFERENCE_PX * size_pt

    @staticmethod
    def ink_height_em(text: str, family: str, bold: bool = False) -> float:
        """Height of the text's ink (top of the tallest letter to the bottom of the lowest)
        as a share of the font size."""
        font = _font(family, bold)
        if font is None:
            raise LookupError(f"No TrueType file for {family}")
        _, top, _, bottom = font.getbbox(text)
        return (bottom - top) / _REFERENCE_PX

    @staticmethod
    def ink_width_em(text: str, family: str, bold: bool = False) -> float:
        """Width of the text's ink (left edge of its first letter to the right edge of its
        last), as a share of the font size: what an OCR word box spans."""
        font = _font(family, bold)
        if font is None:
            raise LookupError(f"No TrueType file for {family}")
        left, _, right, _ = font.getbbox(text)
        return (right - left) / _REFERENCE_PX

    @staticmethod
    def ink_share(text: str, family: str, bold: bool, size_px: float) -> float:
        """Share of dark pixels in the box of the text's ink, set at this many pixels: bold
        strokes darken more of it, whatever the letters."""
        font = _font(family, bold)
        if font is None:
            raise LookupError(f"No TrueType file for {family}")
        sized = font.font_variant(size=max(round(size_px), 4))
        left, top, right, bottom = sized.getbbox(text)
        if right <= left or bottom <= top:
            return 0.0
        canvas = Image.new("L", (int(right - left), int(bottom - top)), 255)
        ImageDraw.Draw(canvas).text((-left, -top), text, font=sized, fill=0)
        dark = sum(canvas.histogram()[:_DARK])
        return dark / (canvas.width * canvas.height)

    @staticmethod
    def below_baseline_em(text: str, family: str, bold: bool = False) -> float:
        """How far the text's ink reaches below its baseline (a 'р', a comma), as a share of
        the font size; 0 for 'вода'."""
        font = _font(family, bold)
        if font is None:
            raise LookupError(f"No TrueType file for {family}")
        _, _, _, bottom = font.getbbox(text, anchor="ls")
        return max(bottom, 0) / _REFERENCE_PX

    def wrap(
        self,
        text: str,
        size_pt: float,
        width_pt: float,
        family: str,
        *,
        bold: bool = False,
        first_indent_pt: float = 0.0,
    ) -> Wrapped:
        """Greedy word wrap as Word does it for left and justified text; a line break in the
        text starts a new line."""
        space = self.width_pt(" ", size_pt, family, bold)
        lines, last = 0, 0.0
        for paragraph in text.split("\n"):
            lines += 1
            current = first_indent_pt if lines == 1 else 0.0
            empty = True
            for word in paragraph.split():
                word_pt = self.width_pt(word, size_pt, family, bold)
                candidate = current + (0.0 if empty else space) + word_pt
                if empty or candidate <= width_pt:
                    current, empty = candidate, False
                else:
                    lines, current = lines + 1, word_pt
            last = current
        return Wrapped(lines, last)
