"""The user's own signature: from a photo or a finger drawing to a clean transparent PNG."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from foto2word.domain.errors import InvalidImageError

INK = (20, 40, 120)
_MAX_WIDTH_PX = 800
_INK_THRESHOLD = 170
"""Pixels darker than this (0-255) count as ink."""
_MIN_INK_PIXELS = 30


def prepare_signature(data: bytes) -> bytes:
    """Keep only the ink: transparent background, tight crop, uniform pen colour."""
    try:
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                # A drawing from the web page: ink is wherever the canvas is not transparent.
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                gray = Image.alpha_composite(background, rgba).convert("L")
            else:
                gray = image.convert("L")
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidImageError(f"Cannot read the signature image: {error}") from error

    gray = ImageOps.autocontrast(gray)
    alpha = gray.point(lambda v: 0 if v >= _INK_THRESHOLD else min(255, (_INK_THRESHOLD - v) * 3))
    box = alpha.getbbox()
    if box is None or sum(alpha.histogram()[1:]) < _MIN_INK_PIXELS:
        raise InvalidImageError("No signature found in the image")

    alpha = alpha.crop(box)
    signature = Image.new("RGBA", alpha.size, (*INK, 0))
    signature.putalpha(alpha)
    if signature.width > _MAX_WIDTH_PX:
        height = round(signature.height * _MAX_WIDTH_PX / signature.width)
        signature = signature.resize((_MAX_WIDTH_PX, height), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    signature.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
