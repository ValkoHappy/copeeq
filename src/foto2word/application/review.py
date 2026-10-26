"""Self-review loop: render -> look at it next to the photo -> patch -> repeat."""

from collections.abc import Sequence
from dataclasses import dataclass

from foto2word.application.ports import (
    DocumentRenderer,
    DocumentReviewer,
    Previewer,
    UnderstandingContext,
    Usage,
)
from foto2word.domain.document import Document
from foto2word.domain.images import PageImage
from foto2word.domain.patches import DocumentPatcher, PatchOutcome
from foto2word.domain.profile import Profile, RenderMode


@dataclass(frozen=True, slots=True)
class ReviewReport:
    document: Document
    rounds: tuple[PatchOutcome, ...]
    usage: Usage


class ReviewLoop:
    def __init__(
        self,
        reviewer: DocumentReviewer,
        previewer: Previewer,
        renderer: DocumentRenderer,
        max_rounds: int = 2,
        patcher: DocumentPatcher | None = None,
    ) -> None:
        self._reviewer = reviewer
        self._previewer = previewer
        self._renderer = renderer
        self._max_rounds = max_rounds
        self._patcher = patcher or DocumentPatcher()

    def run(
        self,
        pages: Sequence[PageImage],
        document: Document,
        profile: Profile,
        context: UnderstandingContext,
    ) -> ReviewReport:
        rounds: list[PatchOutcome] = []
        usage = Usage()
        for _ in range(self._max_rounds):
            # Corrections are not applied yet: the render shows the printed text, like the photo.
            rendered = self._renderer.render(document, profile, RenderMode.FAITHFUL)
            previews = self._previewer.preview(rendered)
            reviewed = self._reviewer.review(pages, previews, document, context)
            usage += reviewed.provenance.usage
            if not reviewed.result.patches and not reviewed.result.missing_corrections:
                break
            outcome = self._patcher.apply(document, reviewed.result)
            rounds.append(outcome)
            if not outcome.applied and outcome.document == document:
                break
            document = outcome.document
        return ReviewReport(document, tuple(rounds), usage)
