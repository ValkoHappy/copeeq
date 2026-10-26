"""Use case: photos of a paper document -> rendered document file."""

import time
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

from foto2word.application.ports import (
    DocumentRenderer,
    FormFiller,
    FormLibrary,
    ImageCutter,
    LayoutEstimator,
    LayoutFitter,
    LineReader,
    PageRectifier,
    ProfileRepository,
    Provenance,
    UnderstandingContext,
    VisionModel,
)
from foto2word.application.review import ReviewLoop, ReviewReport
from foto2word.application.verify import DocumentVerifier, VerificationReport
from foto2word.domain.catalog import DEFAULT_CATALOG, DocumentType
from foto2word.domain.corrections import (
    CorrectionApplier,
    CorrectionDecision,
    CorrectionOutcome,
    accept_all,
)
from foto2word.domain.document import Document, ImageBlock
from foto2word.domain.extras import NO_EXTRAS, RenderExtras
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine
from foto2word.domain.profile import Profile, RenderMode
from foto2word.domain.templates import Replacement, fill, fragments


@dataclass(frozen=True, slots=True)
class ConversionOptions:
    mode: RenderMode = RenderMode.FAITHFUL
    profile_id: str | None = None
    """Force a profile; by default it is chosen from the recognised document type."""
    document_type_hint: str | None = None
    decide_correction: CorrectionDecision = accept_all
    review: bool = False
    """Run the self-review loop (costs extra model calls; needs a previewer)."""
    extras: RenderExtras = NO_EXTRAS


@dataclass(frozen=True, slots=True)
class ConversionResult:
    understood: Document
    """Document as the model read it (after self-review), before corrections."""
    corrections: CorrectionOutcome
    profile: Profile
    output: bytes
    provenance: Provenance | None
    verification: VerificationReport
    review: ReviewReport | None = None
    seconds: Mapping[str, float] = field(default_factory=dict)
    """How long each step took: read (the model), lines, layout, fit, review, render, verify."""

    @property
    def final(self) -> Document:
        return self.corrections.document


@dataclass(frozen=True, slots=True)
class Analysis:
    """Everything that needs the model: reading and, optionally, self-review."""

    document: Document
    provenance: Provenance
    review: ReviewReport | None = None
    pages: tuple[PageImage, ...] = ()
    """The flattened pages the document's boxes refer to; render and verify against these."""
    form: str | None = None
    """Id of the reference form the document was filled into, if it was recognised."""
    images: Mapping[str, bytes] = field(default_factory=dict)
    """Pixels of the reference form's pictures by block id."""
    unfilled: tuple[Replacement, ...] = ()
    """Values the model read but the reference did not contain: worth a look."""
    seconds: Mapping[str, float] = field(default_factory=dict)


@contextmanager
def _timed(seconds: dict[str, float], step: str) -> Iterator[None]:
    started = time.monotonic()
    try:
        yield
    finally:
        seconds[step] = seconds.get(step, 0.0) + round(time.monotonic() - started, 2)


class ConvertDocument:
    def __init__(
        self,
        vision: VisionModel,
        renderer: DocumentRenderer,
        profiles: ProfileRepository,
        *,
        catalog: tuple[DocumentType, ...] = DEFAULT_CATALOG,
        review_loop: ReviewLoop | None = None,
        verifier: DocumentVerifier | None = None,
        corrections: CorrectionApplier | None = None,
        cutter: ImageCutter | None = None,
        layout: LayoutEstimator | None = None,
        lines: LineReader | None = None,
        rectifier: PageRectifier | None = None,
        fitter: LayoutFitter | None = None,
        forms: FormLibrary | None = None,
        filler: FormFiller | None = None,
    ) -> None:
        self._vision = vision
        self._renderer = renderer
        self._profiles = profiles
        self._catalog = catalog
        self._review_loop = review_loop
        self._verifier = verifier or DocumentVerifier()
        self._corrections = corrections or CorrectionApplier()
        self._cutter = cutter
        self._layout = layout
        self._lines = lines
        self._rectifier = rectifier
        self._fitter = fitter
        self._forms = forms
        self._filler = filler

    @property
    def can_review(self) -> bool:
        return self._review_loop is not None

    def execute(self, pages: Sequence[PageImage], options: ConversionOptions) -> ConversionResult:
        analysis = self.analyze(pages, options)
        options = replace(
            options,
            extras=replace(options.extras, images={**analysis.images, **options.extras.images}),
        )
        return self._finish(
            analysis.document,
            options,
            analysis.provenance,
            analysis.pages,
            analysis.review,
            seconds=dict(analysis.seconds),
        )

    def _text_lines(self, pages: Sequence[PageImage]) -> list[TextLine]:
        """The text layer of PDF pages as it is, OCR for the others; numbered as the pages."""
        scanned = [index for index, page in enumerate(pages) if not page.lines]
        read = (
            self._lines.read_lines([pages[i] for i in scanned])
            if self._lines is not None and scanned
            else []
        )
        lines = [
            line.model_copy(update={"page": scanned[line.page - 1] + 1})
            for line in read
            if 0 < line.page <= len(scanned)
        ]
        for index, page in enumerate(pages):
            lines += [line.model_copy(update={"page": index + 1}) for line in page.lines]
        return sorted(lines, key=lambda line: (line.page, line.box.y0, line.box.x0))

    def analyze(self, pages: Sequence[PageImage], options: ConversionOptions) -> Analysis:
        """The model-dependent part: read the photos and optionally self-review."""
        if not pages:
            raise ValueError("At least one page is required")
        seconds: dict[str, float] = {}
        if self._rectifier is not None:  # a PDF page with its text is flat already
            rectifier = self._rectifier
            with _timed(seconds, "rectify"):
                pages = [page if page.lines else rectifier.rectify(page) for page in pages]
        context = UnderstandingContext(self._catalog, options.document_type_hint)
        measure = self._layout is not None and options.mode is RenderMode.FAITHFUL
        with ThreadPoolExecutor(max_workers=1) as pool:  # the text lines while the model reads
            reading = pool.submit(self._timed_lines, pages, seconds) if measure else None
            with _timed(seconds, "read"):
                understanding = self._vision.understand(pages, context)
            lines = reading.result() if reading is not None else []
        document = understanding.document
        reference = self._reference_form(document, pages)
        if reference is not None:
            return replace(reference, provenance=understanding.provenance, seconds=seconds)
        if measure and self._layout is not None:
            with _timed(seconds, "layout"):
                document = self._layout.estimate(document, pages, lines)
            if self._fitter is not None:
                profile = self._profile(document, options)
                with _timed(seconds, "fit"):
                    document = self._fitter.fit(document, pages, lines, profile, options.extras)
        if not (options.review and self._review_loop is not None):
            return Analysis(document, understanding.provenance, pages=tuple(pages), seconds=seconds)
        profile = self._profile(document, options)
        with _timed(seconds, "review"):
            review = self._review_loop.run(pages, document, profile, context)
        return Analysis(
            review.document, understanding.provenance, review, tuple(pages), seconds=seconds
        )

    def _timed_lines(self, pages: Sequence[PageImage], seconds: dict[str, float]) -> list[TextLine]:
        with _timed(seconds, "lines"):
            return self._text_lines(pages)

    def _reference_form(self, understood: Document, pages: Sequence[PageImage]) -> Analysis | None:
        """A recognised unified form: its reference file with the photo's values written in.
        The layout is the original's, so it is neither measured nor fitted."""
        if self._forms is None or self._filler is None:
            return None
        template = self._forms.match(understood)
        if template is None:
            return None
        form_fill = self._filler.fill_form(pages, fragments(template.document))
        filled, unfilled = fill(template.document, form_fill)
        document = filled.model_copy(
            update={"document_type": understood.document_type, "fields": understood.fields}
        )
        return Analysis(
            document,
            Provenance("", "", ""),
            pages=tuple(pages),
            form=template.id,
            images=template.images,
            unfilled=unfilled,
        )

    def rerender(
        self, document: Document, options: ConversionOptions, pages: Sequence[PageImage] = ()
    ) -> ConversionResult:
        """Render an already understood document without calling the model."""
        return self._finish(document, options, provenance=None, pages=pages, review=None)

    def _profile(self, document: Document, options: ConversionOptions) -> Profile:
        if options.profile_id:
            return self._profiles.get(options.profile_id)
        return self._profiles.for_document_type(document.document_type.id)

    def _finish(
        self,
        document: Document,
        options: ConversionOptions,
        provenance: Provenance | None,
        pages: Sequence[PageImage],
        review: ReviewReport | None,
        *,
        seconds: dict[str, float] | None = None,
    ) -> ConversionResult:
        seconds = seconds if seconds is not None else {}
        outcome = self._corrections.apply(document, options.decide_correction)
        profile = self._profile(document, options)
        extras = self._with_pictures(outcome.document, pages, options)
        with _timed(seconds, "render"):
            output = self._renderer.render(outcome.document, profile, options.mode, extras)
        # Fields describe the printed text, so verify the reading before corrections.
        with _timed(seconds, "verify"):
            verification = self._verifier.verify(document, pages, outcome.failed)
        return ConversionResult(
            document, outcome, profile, output, provenance, verification, review, seconds
        )

    def _with_pictures(
        self, document: Document, pages: Sequence[PageImage], options: ConversionOptions
    ) -> RenderExtras:
        """Pictures cut from the photos by their bbox; pixels given by the caller win."""
        if self._cutter is None:
            return options.extras
        cut = {
            block.id: self._cutter.cut(pages[block.page - 1], block.bbox)
            for block in document.blocks
            if isinstance(block, ImageBlock)
            and block.bbox is not None
            and 0 < block.page <= len(pages)
        }
        return replace(options.extras, images={**cut, **options.extras.images})
