"""Imitation of handwritten edits and signatures on top of a rendered page."""

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw

from foto2word.domain.document import Correction, Document, SignatureLineBlock
from foto2word.infrastructure.raster.fonts import FontSet
from foto2word.infrastructure.raster.page import RasterPage

PENCIL = (95, 95, 105)
PEN = (30, 45, 140)


@dataclass(frozen=True, slots=True)
class PencilStyle:
    color: tuple[int, int, int] = PENCIL
    strike_probability: float = 0.6
    """Otherwise the new value is only written above the printed one."""


class PencilAnnotator:
    def __init__(
        self, fonts: FontSet, rng: random.Random, style: PencilStyle | None = None
    ) -> None:
        self._fonts = fonts
        self._rng = rng
        self._style = style or PencilStyle()

    def annotate(self, page: RasterPage, document: Document) -> list[Correction]:
        """Draw every correction that can be located; return the ones actually drawn."""
        drawn = []
        for correction in document.corrections:
            box = page.locate(correction.block_id, correction.before)
            if box is None:
                continue
            self._write_over(page.image, box, correction.after)
            drawn.append(correction)
        for block in document.blocks:
            slot = page.signature_slots.get(block.id)
            if isinstance(block, SignatureLineBlock) and block.has_signature_mark and slot:
                self._signature(page.image, slot)
        return drawn

    def _write_over(self, image: Image.Image, box: tuple[float, ...], text: str) -> None:
        x0, y0, x1, y1 = box
        draw = ImageDraw.Draw(image)
        if self._rng.random() < self._style.strike_probability:
            mid = (y0 + y1) / 2 + self._rng.uniform(-3, 3)
            draw.line((x0 - 3, mid + 2, x1 + 3, mid - 2), fill=self._style.color, width=3)
        height = y1 - y0
        font = self._fonts.hand(round(height * self._rng.uniform(0.7, 0.95)))
        width = font.getlength(text) + 10
        layer = Image.new("RGBA", (round(width), round(height * 1.4)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((4, 0), text, font=font, fill=(*self._style.color, 235))
        layer = layer.rotate(
            self._rng.uniform(-6, 6), expand=True, resample=Image.Resampling.BICUBIC
        )
        x = round(x0 + self._rng.uniform(-10, 20))
        y = round(y0 - layer.height * self._rng.uniform(0.75, 1.0))
        image.paste(layer, (x, max(y, 0)), layer)

    def _signature(self, image: Image.Image, slot: tuple[float, ...]) -> None:
        x0, y0, x1, y1 = slot
        draw = ImageDraw.Draw(image)
        points = []
        steps = 40
        loops = self._rng.uniform(2.5, 4.5)
        for i in range(steps):
            t = i / (steps - 1)
            x = x0 + (x1 - x0) * (0.1 + 0.8 * t)
            y = (y0 + y1) / 2 + math.sin(t * math.pi * loops) * (y1 - y0) * 0.35
            points.append((x + self._rng.uniform(-2, 2), y + self._rng.uniform(-2, 2)))
        draw.line(points, fill=PEN, width=3, joint="curve")
