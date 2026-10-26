"""Turns a clean page image into something that looks like a phone photo of paper."""

import io
import random
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class CameraSettings:
    max_corner_shift: float = 0.06
    """Perspective distortion, as a share of the page size."""
    max_blur: float = 1.2
    shadow_strength: float = 0.35
    jpeg_quality: tuple[int, int] = (55, 90)
    background: tuple[int, int, int] = (120, 105, 90)


class PhoneCamera:
    def __init__(self, rng: random.Random, settings: CameraSettings | None = None) -> None:
        self._rng = rng
        self._s = settings or CameraSettings()

    def shoot(self, page: Image.Image) -> Image.Image:
        photo = self._perspective(page)
        photo = self._lighting(photo)
        photo = photo.filter(ImageFilter.GaussianBlur(self._rng.uniform(0, self._s.max_blur)))
        return self._jpeg(photo)

    def _perspective(self, page: Image.Image) -> Image.Image:
        w, h = page.size
        margin = 0.08
        canvas = (round(w * (1 + 2 * margin)), round(h * (1 + 2 * margin)))
        shift = self._s.max_corner_shift

        def jitter(x: float, y: float) -> Point:
            return (
                x + self._rng.uniform(-shift, shift) * w,
                y + self._rng.uniform(-shift, shift) * h,
            )

        ox, oy = w * margin, h * margin
        target = [jitter(ox, oy), jitter(ox + w, oy), jitter(ox + w, oy + h), jitter(ox, oy + h)]
        source = [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]
        coefficients = _perspective_coefficients(target, source)

        background = Image.new("RGB", canvas, self._s.background)
        noise = Image.effect_noise(canvas, 25).convert("RGB")
        background = Image.blend(background, noise, 0.15)
        warped = page.convert("RGBA").transform(
            canvas, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC
        )
        background.paste(warped, (0, 0), warped)
        return background

    def _lighting(self, photo: Image.Image) -> Image.Image:
        w, h = photo.size
        rotated = Image.linear_gradient("L").rotate(self._rng.uniform(0, 360), expand=True)
        # Crop the central square that is fully covered after rotation: no filled corners.
        side = 256 / 2**0.5
        cx, cy = rotated.width / 2, rotated.height / 2
        box = (
            round(cx - side / 2),
            round(cy - side / 2),
            round(cx + side / 2),
            round(cy + side / 2),
        )
        gradient = rotated.crop(box).resize((w, h), Image.Resampling.BILINEAR)
        strength = self._rng.uniform(0, self._s.shadow_strength)
        dark = ImageEnhance.Brightness(photo).enhance(1 - strength)
        photo = Image.composite(photo, dark, gradient)
        return ImageEnhance.Color(photo).enhance(self._rng.uniform(0.8, 1.1))

    def _jpeg(self, photo: Image.Image) -> Image.Image:
        buffer = io.BytesIO()
        photo.save(buffer, format="JPEG", quality=self._rng.randint(*self._s.jpeg_quality))
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")


def _perspective_coefficients(target: list[Point], source: list[Point]) -> tuple[float, ...]:
    """Coefficients mapping output (target) points to input (source) points for PIL."""
    matrix: list[list[float]] = []
    vector: list[float] = []
    for (x, y), (u, v) in zip(target, source, strict=True):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        vector += [u, v]
    return tuple(_solve(matrix, vector))


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for a small dense system."""
    n = len(vector)
    rows = [[*row, value] for row, value in zip(matrix, vector, strict=True)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r != col:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
    return [rows[i][n] / rows[i][i] for i in range(n)]
