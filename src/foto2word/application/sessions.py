"""Interactive conversion: analyse once in the background, then let the user decide and rebuild.

Every user decision (type, corrections, typo fixes, text edits, mode) only re-renders the
document; the model is called once per session.
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from foto2word.application.convert import (
    Analysis,
    ConversionOptions,
    ConversionResult,
    ConvertDocument,
)
from foto2word.application.ports import DocumentEditor, Previewer
from foto2word.domain.catalog import DocumentType
from foto2word.domain.corrections import CorrectionApplier
from foto2word.domain.dates import DateShifter
from foto2word.domain.document import Correction, Document, DocumentTypeGuess
from foto2word.domain.errors import Foto2WordError
from foto2word.domain.extras import RenderExtras, SignatureMode
from foto2word.domain.images import PageImage
from foto2word.domain.patches import DocumentPatcher, PatchOutcome
from foto2word.domain.profile import RenderMode


class SessionStatus(StrEnum):
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Decisions:
    document_type_id: str | None = None
    mode: RenderMode = RenderMode.FAITHFUL
    rejected_corrections: frozenset[str] = frozenset()
    accepted_suggestions: frozenset[int] = frozenset()
    """Indexes into Document.suggestions the user chose to fix."""
    block_edits: tuple[tuple[str, str], ...] = ()
    field_values: tuple[tuple[int, str], ...] = ()
    """New values for Document.fields by index ("fill the document again")."""
    shift_years: int = 0
    """Move every current date and year by this many years."""
    signature_mode: SignatureMode = SignatureMode.BLANK
    signed_blocks: frozenset[str] = frozenset()
    attach_scan: bool = False
    editable: bool = False
    """Comfortable to fill in: fixed heights and sizes of the original only set a minimum."""


@dataclass(slots=True)
class Session:
    id: str
    pages: tuple[PageImage, ...]
    review: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: SessionStatus = SessionStatus.ANALYZING
    analysis: Analysis | None = None
    decisions: Decisions = field(default_factory=Decisions)
    result: ConversionResult | None = None
    signature_png: bytes | None = None
    """The user's own signature, uploaded with an explicit 'this is my signature' consent."""
    previews: list[PageImage] = field(default_factory=list)
    error: str | None = None


class SessionStore(Protocol):
    def save(self, session: Session) -> None: ...

    def get(self, session_id: str) -> Session | None: ...

    def delete(self, session_id: str) -> None: ...


class SessionNotFoundError(Foto2WordError):
    pass


class SessionNotReadyError(Foto2WordError):
    pass


logger = logging.getLogger(__name__)

Runner = Callable[[Callable[[], None]], None]
"""Executes a job, e.g. on a thread pool. Tests pass a synchronous runner."""


class SessionService:
    def __init__(
        self,
        converter: ConvertDocument,
        store: SessionStore,
        catalog: tuple[DocumentType, ...],
        *,
        run: Runner,
        previewer: Previewer | None = None,
        editor: DocumentEditor | None = None,
    ) -> None:
        self._converter = converter
        self._store = store
        self._catalog = {t.id: t for t in catalog}
        self._run = run
        self._previewer = previewer
        self._editor = editor

    def start(self, pages: Sequence[PageImage], review: bool = False) -> Session:
        if not pages:
            raise ValueError("At least one page is required")
        session = Session(id=uuid.uuid4().hex, pages=tuple(pages), review=review)
        self._store.save(session)
        self._run(lambda: self._analyze(session.id))
        return session

    def get(self, session_id: str) -> Session:
        session = self._store.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{session_id}' not found or expired")
        return session

    def decide(self, session_id: str, decisions: Decisions) -> Session:
        session = self.get(session_id)
        if session.analysis is None:
            raise SessionNotReadyError("The document is still being analysed")
        session.decisions = decisions
        self._build(session)
        self._store.save(session)
        return session

    def instruct(self, session_id: str, request: str) -> tuple[Session, PatchOutcome]:
        """Apply a plain-language request; edits are kept as part of the analysed document."""
        session = self.get(session_id)
        if session.analysis is None:
            raise SessionNotReadyError("The document is still being analysed")
        if self._editor is None:
            raise SessionNotReadyError("Editing by request is not configured")
        reviewed = self._editor.edit(session.analysis.document, request)
        outcome = DocumentPatcher().apply(session.analysis.document, reviewed.result)
        session.analysis = replace(session.analysis, document=outcome.document)
        self._build(session)
        self._store.save(session)
        return session, outcome

    @property
    def can_export_pdf(self) -> bool:
        return self._previewer is not None

    def export_pdf(self, session_id: str) -> bytes | None:
        session = self.get(session_id)
        if session.result is None:
            raise SessionNotReadyError("The document is still being analysed")
        return self._previewer.to_pdf(session.result.output) if self._previewer else None

    def set_signature(self, session_id: str, png: bytes) -> Session:
        session = self.get(session_id)
        session.signature_png = png
        if session.analysis is not None:
            self._build(session)
        self._store.save(session)
        return session

    def delete(self, session_id: str) -> None:
        self._store.delete(session_id)

    def _analyze(self, session_id: str) -> None:
        session = self.get(session_id)
        try:
            session.analysis = self._converter.analyze(
                session.pages, ConversionOptions(review=session.review)
            )
            # from now on the flattened pages: the boxes, cut-outs and the scan refer to them
            session.pages = session.analysis.pages or session.pages
            self._build(session)
        except Foto2WordError as error:
            session.status, session.error = SessionStatus.FAILED, str(error)
        except Exception:
            logger.exception("Analysis of session %s crashed", session_id)
            session.status, session.error = SessionStatus.FAILED, "Внутренняя ошибка сервиса"
        self._store.save(session)

    def _build(self, session: Session) -> None:
        analysis = session.analysis
        if analysis is None:
            raise SessionNotReadyError("The document is still being analysed")
        decisions = session.decisions
        document = self._decided_document(analysis.document, decisions)
        extras = RenderExtras(
            signature_mode=decisions.signature_mode,
            signature_png=session.signature_png,
            signed_blocks=decisions.signed_blocks,
            appendix=session.pages if decisions.attach_scan else (),
            editable=decisions.editable,
            images=analysis.images,  # pictures of a reference form, if one was used
        )
        options = ConversionOptions(
            mode=decisions.mode,
            decide_correction=lambda c: c.id not in decisions.rejected_corrections,
            extras=extras,
        )
        session.result = self._converter.rerender(document, options, session.pages)
        session.result = replace(session.result, provenance=analysis.provenance)
        session.previews = self._previewer.preview(session.result.output) if self._previewer else []
        session.status = SessionStatus.READY

    def _decided_document(self, document: Document, decisions: Decisions) -> Document:
        for block_id, text in decisions.block_edits:
            document = document.with_block_text(block_id, text)
        typo_fixes = tuple(
            suggestion.as_correction(f"s{index}")
            for index, suggestion in enumerate(document.suggestions)
            if index in decisions.accepted_suggestions
        )
        field_fixes = tuple(
            Correction(
                id=f"f{index}",
                block_id=document.fields[index].block_id,
                before=document.fields[index].value,
                after=value,
            )
            for index, value in decisions.field_values
            if 0 <= index < len(document.fields) and value != document.fields[index].value
        )
        corrections = (*document.corrections, *typo_fixes, *field_fixes)
        if decisions.shift_years:
            # Shift the text as it will read after the other edits, so both never collide.
            staged = document.model_copy(update={"corrections": corrections})
            decide = lambda c: c.id not in decisions.rejected_corrections  # noqa: E731
            staged = CorrectionApplier().apply(staged, decide).document
            corrections += DateShifter().propose(staged, decisions.shift_years)
        update: dict[str, object] = {"corrections": corrections}
        chosen = self._catalog.get(decisions.document_type_id or "")
        if chosen is not None and chosen.id != document.document_type.id:
            update["document_type"] = DocumentTypeGuess(
                id=chosen.id, title=chosen.title, confidence=1.0
            )
        return document.model_copy(update=update)
