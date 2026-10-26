"""Interfaces the application layer depends on. Implementations live in infrastructure."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from foto2word.domain.catalog import DocumentType
from foto2word.domain.document import BoundingBox, Document
from foto2word.domain.extras import NO_EXTRAS, RenderExtras
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine
from foto2word.domain.patches import ReviewResult
from foto2word.domain.profile import Profile, RenderMode
from foto2word.domain.templates import FormFill, FormTemplate


@dataclass(frozen=True, slots=True)
class UnderstandingContext:
    catalog: tuple[DocumentType, ...]
    document_type_hint: str | None = None
    """Type confirmed by the user, if any."""


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True, slots=True)
class Provenance:
    provider: str
    model: str
    prompt_version: str
    usage: Usage = Usage()


@dataclass(frozen=True, slots=True)
class Understanding:
    document: Document
    provenance: Provenance


class VisionModel(Protocol):
    """Turns page photos into a Document. The only non-deterministic stage."""

    def understand(
        self, pages: Sequence[PageImage], context: UnderstandingContext
    ) -> Understanding: ...


class DocumentRenderer(Protocol):
    def render(
        self,
        document: Document,
        profile: Profile,
        mode: RenderMode,
        extras: RenderExtras = NO_EXTRAS,
    ) -> bytes:
        """Return the rendered file content (e.g. .docx bytes)."""
        ...


class ProfileRepository(Protocol):
    def get(self, profile_id: str) -> Profile: ...

    def for_document_type(self, document_type_id: str) -> Profile:
        """Best profile for the type, falling back to the generic one."""
        ...


@dataclass(frozen=True, slots=True)
class Reviewed:
    result: ReviewResult
    provenance: Provenance


class DocumentReviewer(Protocol):
    """Compares the original photos with pictures of the rendered document."""

    def review(
        self,
        originals: Sequence[PageImage],
        rendered: Sequence[PageImage],
        document: Document,
        context: UnderstandingContext,
    ) -> Reviewed: ...


class DocumentEditor(Protocol):
    """Applies a request in plain language ("замени дату на ...") as block patches."""

    def edit(self, document: Document, request: str) -> Reviewed: ...


class LayoutEstimator(Protocol):
    """Measures on the photos what a model cannot name: font sizes, spacing, indents, margins.
    Fills only what the reading left empty."""

    def estimate(
        self, document: Document, pages: Sequence[PageImage], lines: Sequence[TextLine] = ()
    ) -> Document: ...


class LayoutFitter(Protocol):
    """Renders the document, finds where its blocks landed and moves them to where they are on
    the photo. Needs a previewer; costs a rendering per round."""

    def fit(
        self,
        document: Document,
        pages: Sequence[PageImage],
        lines: Sequence[TextLine],
        profile: Profile,
        extras: RenderExtras = NO_EXTRAS,
    ) -> Document: ...


class FormLibrary(Protocol):
    """Reference Word files of unified forms, recognised by the marks printed on them."""

    def match(self, document: Document) -> FormTemplate | None: ...


class FormFiller(Protocol):
    """Reads the photographed form as replacements of the reference sample's values."""

    def fill_form(self, pages: Sequence[PageImage], sample: list[str]) -> FormFill: ...


class PageRectifier(Protocol):
    """Phone photo -> flat, upright page; a page that is already flat comes back unchanged."""

    def rectify(self, page: PageImage) -> PageImage: ...


class LineReader(Protocol):
    """A classic OCR engine: text lines with their exact place on the photo. Geometry comes from
    it, not from the vision model, whose boxes are approximate."""

    def read_lines(self, pages: Sequence[PageImage]) -> list[TextLine]: ...


class ImageCutter(Protocol):
    """Cuts a region out of a page photo: logos, stamps and pictures go into the document as
    they are on the paper, never redrawn."""

    def cut(self, page: PageImage, box: BoundingBox) -> bytes: ...


class Previewer(Protocol):
    """Turns a rendered file into page pictures exactly as the user will see it."""

    def preview(self, rendered: bytes) -> list[PageImage]: ...

    def to_pdf(self, rendered: bytes) -> bytes:
        """The same rendering as a PDF file for download."""
        ...
