from dataclasses import dataclass

from foto2word.domain.ocr import TextLine


@dataclass(frozen=True, slots=True)
class PageImage:
    """One photographed page, already normalised for a vision model."""

    data: bytes
    media_type: str
    source_name: str
    lines: tuple[TextLine, ...] = ()
    """The page's text exactly, when it comes from a PDF with a text layer: no OCR is needed,
    and the page is flat already. Line page numbers are set when the pages are put together."""
