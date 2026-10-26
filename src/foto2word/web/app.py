"""HTTP API and the single-page frontend."""

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from foto2word.application.convert import ConversionResult
from foto2word.application.sessions import (
    Decisions,
    Session,
    SessionNotFoundError,
    SessionNotReadyError,
    SessionService,
)
from foto2word.domain.catalog import DocumentType
from foto2word.domain.document import (
    HeadingBlock,
    ListItemBlock,
    ParagraphBlock,
    SignatureLineBlock,
    TableBlock,
)
from foto2word.domain.errors import Foto2WordError, InvalidImageError
from foto2word.domain.extras import SignatureMode
from foto2word.domain.images import PageImage
from foto2word.domain.profile import RenderMode
from foto2word.infrastructure.exports import scan_pdf, tables_xlsx
from foto2word.infrastructure.images import PillowImageLoader
from foto2word.infrastructure.signature import prepare_signature

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EDITABLE = (HeadingBlock, ParagraphBlock, ListItemBlock)


class UploadLimits(BaseModel):
    max_files: int = 10
    max_file_bytes: int = 20 * 1024 * 1024


class InstructionIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)


class DecisionsIn(BaseModel):
    document_type_id: str | None = None
    mode: RenderMode = RenderMode.FAITHFUL
    rejected_corrections: list[str] = []
    accepted_suggestions: list[int] = []
    block_edits: dict[str, str] = {}
    field_values: dict[int, str] = {}
    shift_years: int = Field(default=0, ge=-10, le=10)
    signature_mode: SignatureMode = SignatureMode.BLANK
    signed_blocks: list[str] = []
    attach_scan: bool = False
    editable: bool = False

    def to_domain(self) -> Decisions:
        return Decisions(
            document_type_id=self.document_type_id,
            mode=self.mode,
            rejected_corrections=frozenset(self.rejected_corrections),
            accepted_suggestions=frozenset(self.accepted_suggestions),
            block_edits=tuple(self.block_edits.items()),
            field_values=tuple(sorted(self.field_values.items())),
            shift_years=self.shift_years,
            signature_mode=self.signature_mode,
            signed_blocks=frozenset(self.signed_blocks),
            attach_scan=self.attach_scan,
            editable=self.editable,
        )


def session_view(session: Session, service: SessionService) -> dict[str, object]:
    """Everything the page needs to ask the user its questions, in one JSON object."""
    view: dict[str, object] = {
        "id": session.id,
        "status": session.status.value,
        "error": session.error,
        "photos": len(session.pages),
        "previews": len(session.previews),
    }
    if session.analysis is None or session.result is None:
        return view
    document = session.analysis.document
    decisions = session.decisions
    result = session.result
    provenance = result.provenance
    source_texts = {b.id: b.text() for b in document.blocks}
    source_texts.update(decisions.block_edits)
    view |= {
        "document_type": document.document_type.model_dump(),
        "alternative_types": [t.model_dump() for t in document.alternative_types],
        "chosen_type": decisions.document_type_id or document.document_type.id,
        "mode": decisions.mode.value,
        "profile": result.profile.id,
        "corrections": [
            {
                **c.model_dump(include={"id", "block_id", "before", "after"}),
                "accepted": c.id not in decisions.rejected_corrections,
            }
            for c in document.corrections
        ],
        "suggestions": [
            {**s.model_dump(), "index": i, "accepted": i in decisions.accepted_suggestions}
            for i, s in enumerate(document.suggestions)
        ],
        "fields": [
            {**f.model_dump(), "index": i, "current": dict(decisions.field_values).get(i, f.value)}
            for i, f in enumerate(document.fields)
        ],
        "date_changes": [
            {"before": c.before, "after": c.after}
            for c in result.corrections.applied
            if c.id.startswith("y")
        ],
        "shift_years": decisions.shift_years,
        "signature_mode": decisions.signature_mode.value,
        "signed_blocks": sorted(decisions.signed_blocks),
        "has_signature": session.signature_png is not None,
        "attach_scan": decisions.attach_scan,
        "editable": decisions.editable,
        "signature_lines": [
            {"id": b.id, "label": b.label, "name": b.name, "signed_on_photo": b.has_signature_mark}
            for b in document.blocks
            if isinstance(b, SignatureLineBlock)
        ],
        "has_tables": any(isinstance(b, TableBlock) for b in document.blocks),
        "pdf_available": service.can_export_pdf,
        "flags": [
            {"kind": f.kind.value, "block_id": f.block_id, "message": f.message, "value": f.value}
            for f in result.verification.flags
        ],
        "blocks": [
            {
                "id": b.id,
                "kind": b.kind,
                "text": b.text(),
                "source_text": source_texts.get(b.id, b.text()),
                "editable": isinstance(b, _EDITABLE),
            }
            for b in result.final.blocks
        ],
        "edited_blocks": [block_id for block_id, _ in decisions.block_edits],
        "block_edits": dict(decisions.block_edits),
        "review_rounds": len(session.analysis.review.rounds) if session.analysis.review else None,
        "model": f"{provenance.provider}/{provenance.model}" if provenance else None,
    }
    return view


def create_app(
    service: SessionService,
    loader: PillowImageLoader,
    catalog: tuple[DocumentType, ...],
    limits: UploadLimits | None = None,
) -> FastAPI:
    app = FastAPI(title="foto2word", docs_url="/api/docs", openapi_url="/api/openapi.json")
    static = Path(str(files("foto2word.web") / "static"))
    app.mount("/static", StaticFiles(directory=static), name="static")
    copeeq = Path(str(files("foto2word.web") / "copeeq"))
    if (copeeq / "index.html").is_file():
        app.mount("/app", StaticFiles(directory=copeeq, html=True), name="copeeq")
    app.middleware("http")(_revalidate_frontend)
    app.add_exception_handler(SessionNotFoundError, _status_handler(404))
    app.add_exception_handler(SessionNotReadyError, _status_handler(409))
    app.add_exception_handler(Foto2WordError, _status_handler(400))
    app.include_router(_pages_router(static, catalog, copeeq))
    app.include_router(_sessions_router(service, loader, limits or UploadLimits()))
    app.include_router(_exports_router(service))
    return app


async def _revalidate_frontend(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        # Revalidate the page and assets (cheap thanks to ETag) so a release shows up at once.
        response.headers["Cache-Control"] = "no-cache"
    return response


def _status_handler(status: int) -> Callable[[Request, Exception], Response]:
    def handle(_: Request, error: Exception) -> Response:
        return JSONResponse({"detail": str(error)}, status_code=status)

    return handle


def _pages_router(static: Path, catalog: tuple[DocumentType, ...], copeeq: Path) -> APIRouter:
    router = APIRouter()
    index_html = _fingerprinted_index(static)

    @router.get("/", include_in_schema=False)
    def index() -> Response:
        if (copeeq / "index.html").is_file():
            return RedirectResponse("/app/", status_code=307)
        return HTMLResponse(index_html)

    @router.get("/classic", include_in_schema=False)
    def classic() -> HTMLResponse:
        return HTMLResponse(index_html)

    @router.get("/api/catalog")
    def get_catalog() -> list[dict[str, str]]:
        return [{"id": t.id, "title": t.title} for t in catalog]

    return router


def _sessions_router(
    service: SessionService, loader: PillowImageLoader, limits: UploadLimits
) -> APIRouter:
    router = APIRouter(prefix="/api/sessions")

    def read_limited(upload: UploadFile) -> bytes:
        data = upload.file.read(limits.max_file_bytes + 1)
        if len(data) > limits.max_file_bytes:
            raise HTTPException(413, f"Файл {upload.filename} слишком большой")
        return data

    @router.post("", status_code=201)
    def create_session(
        photos: Annotated[list[UploadFile], File()],
        review: Annotated[bool, Form()] = False,
    ) -> dict[str, object]:
        if not photos or len(photos) > limits.max_files:
            raise HTTPException(400, f"Загрузите от 1 до {limits.max_files} фото")
        try:
            pages = [
                page
                for p in photos
                for page in loader.load_document(read_limited(p), p.filename or "photo")
            ]
        except InvalidImageError as error:
            raise HTTPException(400, str(error)) from error
        return session_view(service.start(pages, review=review), service)

    @router.get("/{session_id}")
    def get_session(session_id: str) -> dict[str, object]:
        return session_view(service.get(session_id), service)

    @router.post("/{session_id}/decisions")
    def decide(session_id: str, decisions: DecisionsIn) -> dict[str, object]:
        try:
            session = service.decide(session_id, decisions.to_domain())
        except (KeyError, TypeError) as error:
            raise HTTPException(400, f"Некорректная правка блока: {error}") from error
        return session_view(session, service)

    @router.post("/{session_id}/instruction")
    def instruct(session_id: str, body: InstructionIn) -> dict[str, object]:
        session, outcome = service.instruct(session_id, body.text)
        view = session_view(session, service)
        view["instruction_result"] = {
            "applied": [p.reason for p in outcome.applied],
            "skipped": len(outcome.skipped),
        }
        return view

    @router.post("/{session_id}/signature")
    def upload_signature(
        session_id: str,
        image: Annotated[UploadFile, File()],
        own_signature: Annotated[bool, Form()] = False,
    ) -> dict[str, object]:
        if not own_signature:
            raise HTTPException(400, "Подтвердите, что это ваша собственная подпись")
        try:
            png = prepare_signature(read_limited(image))
        except InvalidImageError as error:
            raise HTTPException(400, str(error)) from error
        return session_view(service.set_signature(session_id, png), service)

    @router.get("/{session_id}/preview/{number}")
    def preview(session_id: str, number: int) -> Response:
        return _image(service.get(session_id).previews, number)

    @router.get("/{session_id}/photo/{number}")
    def photo(session_id: str, number: int) -> Response:
        return _image(service.get(session_id).pages, number)

    @router.delete("/{session_id}", status_code=204)
    def delete(session_id: str) -> Response:
        service.delete(session_id)
        return Response(status_code=204)

    return router


def _exports_router(service: SessionService) -> APIRouter:
    router = APIRouter(prefix="/api/sessions/{session_id}")

    def ready_result(session_id: str) -> ConversionResult:
        result = service.get(session_id).result
        if result is None:
            raise SessionNotReadyError("The document is still being analysed")
        return result

    @router.get("/document.docx")
    def download_docx(session_id: str) -> Response:
        return _attachment(ready_result(session_id).output, DOCX_MEDIA_TYPE, "document.docx")

    @router.get("/document.pdf")
    def download_pdf(session_id: str) -> Response:
        pdf = service.export_pdf(session_id)
        if pdf is None:
            raise HTTPException(501, "PDF недоступен: на сервере нет Word или LibreOffice")
        return _attachment(pdf, "application/pdf", "document.pdf")

    @router.get("/scan.pdf")
    def download_scan(session_id: str) -> Response:
        return _attachment(scan_pdf(service.get(session_id).pages), "application/pdf", "scan.pdf")

    @router.get("/tables.xlsx")
    def download_tables(session_id: str) -> Response:
        workbook = tables_xlsx(ready_result(session_id).final)
        if workbook is None:
            raise HTTPException(404, "В документе нет таблиц")
        return _attachment(workbook, XLSX_MEDIA_TYPE, "tables.xlsx")

    return router


def _attachment(data: bytes, media_type: str, filename: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(data, media_type=media_type, headers=headers)


def _fingerprinted_index(static: Path) -> str:
    """Append a content hash to asset URLs so browsers never run a stale script after a release."""
    html = (static / "index.html").read_text(encoding="utf-8")
    for asset in ("app.js", "styles.css"):
        digest = hashlib.sha256((static / asset).read_bytes()).hexdigest()[:12]
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={digest}")
    return html


def _image(images: Sequence[PageImage], number: int) -> Response:
    if not 1 <= number <= len(images):
        raise HTTPException(404, "No such page")
    page = images[number - 1]
    return Response(page.data, media_type=page.media_type, headers={"Cache-Control": "no-store"})
