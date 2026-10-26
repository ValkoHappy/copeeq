"""Loading user photos and normalising them for vision models."""

from io import BytesIO
from pathlib import Path

import pypdfium2
from PIL import Image, ImageOps, UnidentifiedImageError

from foto2word.domain.document import BoundingBox
from foto2word.domain.errors import InvalidImageError
from foto2word.domain.images import PageImage
from foto2word.infrastructure.layout.pdf_lines import pdf_lines

try:  # HEIC/HEIF from iPhones is optional: pip install foto2word[heic]
    from pillow_heif import register_heif_opener  # type: ignore[import-not-found]

    register_heif_opener()
except ImportError:  # pragma: no cover - depends on the environment
    pass


class PillowImageCutter:
    """Cuts a normalised bbox out of a page photo as PNG (stamps keep sharp edges)."""

    def cut(self, page: PageImage, box: BoundingBox) -> bytes:
        with Image.open(BytesIO(page.data)) as source:
            image = source.convert("RGB")
        width, height = image.size
        area = (
            round(min(box.x0, box.x1) * width),
            round(min(box.y0, box.y1) * height),
            max(round(max(box.x0, box.x1) * width), round(min(box.x0, box.x1) * width) + 1),
            max(round(max(box.y0, box.y1) * height), round(min(box.y0, box.y1) * height) + 1),
        )
        buffer = BytesIO()
        image.crop(area).save(buffer, format="PNG")
        return buffer.getvalue()


class PillowImageLoader:
    """Fixes EXIF rotation, converts to RGB JPEG and limits the longest side."""

    def __init__(self, max_side_px: int = 2048, jpeg_quality: int = 90) -> None:
        self._max_side = max_side_px
        self._quality = jpeg_quality

    def load(self, path: Path) -> PageImage:
        return self.load_bytes(path.read_bytes(), path.name)

    def load_bytes(self, data: bytes, name: str) -> PageImage:
        try:
            with Image.open(BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (UnidentifiedImageError, OSError) as error:
            raise InvalidImageError(f"Cannot read image '{name}': {error}") from error

        image.thumbnail((self._max_side, self._max_side), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=self._quality, optimize=True)
        return PageImage(buffer.getvalue(), "image/jpeg", name)

    def load_all(self, paths: list[Path]) -> list[PageImage]:
        return [page for path in paths for page in self.load_document(path.read_bytes(), path.name)]

    def load_document(self, data: bytes, name: str) -> list[PageImage]:
        """A photo is one page; a PDF is its pages, each with its text layer if it has one
        (a scan has none and is read like a photo)."""
        if not data.startswith(b"%PDF"):
            return [self.load_bytes(data, name)]
        try:
            document = pypdfium2.PdfDocument(data)
        except pypdfium2.PdfiumError as error:
            raise InvalidImageError(f"Cannot read PDF '{name}': {error}") from error
        try:
            pages = []
            for index in range(min(len(document), _MAX_PDF_PAGES)):
                page = document[index]
                scale = self._max_side / max(page.get_size())
                image = page.render(scale=scale).to_pil().convert("RGB")
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=self._quality, optimize=True)
                lines = tuple(pdf_lines(data, (index + 1,)))
                text = sum(len(line.text.strip()) for line in lines)
                pages.append(
                    PageImage(
                        buffer.getvalue(),
                        "image/jpeg",
                        f"{name} #{index + 1}",
                        lines if text >= _MIN_TEXT_CHARS else (),
                    )
                )
            return pages
        finally:
            document.close()


_MAX_PDF_PAGES = 20
_MIN_TEXT_CHARS = 20
"""Fewer characters in the text layer: a scan (perhaps with a stamp's caption), read by OCR."""
