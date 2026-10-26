"""Composition root: the only place that knows concrete implementations."""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import Protocol

import anthropic
import openai
from fastapi import FastAPI
from pydantic import SecretStr

from foto2word.application.convert import ConvertDocument
from foto2word.application.ports import (
    DocumentEditor,
    DocumentReviewer,
    FormFiller,
    LineReader,
    Previewer,
    Reviewed,
    Understanding,
    UnderstandingContext,
    VisionModel,
)
from foto2word.application.review import ReviewLoop
from foto2word.application.sessions import SessionService
from foto2word.application.verify import DocumentVerifier, SecondReader
from foto2word.domain.catalog import DEFAULT_CATALOG
from foto2word.domain.document import Document
from foto2word.domain.errors import Foto2WordError
from foto2word.domain.images import PageImage
from foto2word.domain.templates import FormFill
from foto2word.infrastructure.config import ProviderName, Settings
from foto2word.infrastructure.forms import DocxFormLibrary, builtin_forms_dir
from foto2word.infrastructure.images import PillowImageCutter, PillowImageLoader
from foto2word.infrastructure.layout.fit import RenderLayoutFitter
from foto2word.infrastructure.layout.projection import ProjectionLayoutEstimator
from foto2word.infrastructure.ocr.windows import WindowsOcrReader, windows_ocr_available
from foto2word.infrastructure.ocr.yandex import YandexVisionReader
from foto2word.infrastructure.preview import detect_previewer
from foto2word.infrastructure.profiles.yaml_repository import (
    YamlProfileRepository,
    builtin_profiles_dir,
)
from foto2word.infrastructure.providers.anthropic_provider import ClaudeVisionModel
from foto2word.infrastructure.providers.openai_compatible import OpenAICompatibleVisionModel
from foto2word.infrastructure.providers.openai_provider import OpenAIVisionModel
from foto2word.infrastructure.rectify import OpenCvPageRectifier
from foto2word.infrastructure.rendering.docx_renderer import DocxRenderer
from foto2word.infrastructure.session_store import InMemorySessionStore
from foto2word.web.app import create_app


class ConfigurationError(Foto2WordError):
    pass


class VisionProvider(VisionModel, DocumentReviewer, DocumentEditor, FormFiller, Protocol):
    """A model that reads a document, reviews a rendering of it and edits it on request."""


def _openai(settings: Settings) -> VisionProvider:
    return OpenAIVisionModel(
        openai.OpenAI(api_key=_require(settings.openai_api_key, "OPENAI_API_KEY")),
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
        max_output_tokens=settings.openai_max_output_tokens,
        image_detail=settings.openai_image_detail,
    )


def _anthropic(settings: Settings) -> VisionProvider:
    return ClaudeVisionModel(
        anthropic.Anthropic(api_key=_require(settings.anthropic_api_key, "ANTHROPIC_API_KEY")),
        model=settings.claude_model,
        effort=settings.claude_effort,
        max_tokens=settings.claude_max_tokens,
        server_fallbacks=settings.claude_server_fallbacks,
    )


def _compatible(settings: Settings) -> VisionProvider:
    if not settings.compatible_base_url or not settings.compatible_model:
        raise ConfigurationError("Set F2W_COMPATIBLE_BASE_URL and F2W_COMPATIBLE_MODEL in .env.")
    key = settings.compatible_api_key.get_secret_value() if settings.compatible_api_key else ""
    return OpenAICompatibleVisionModel(
        openai.OpenAI(base_url=settings.compatible_base_url, api_key=key or "not-needed"),
        model=settings.compatible_model,
        strict=settings.compatible_strict,
        provider_label=settings.compatible_label,
    )


PROVIDERS: dict[ProviderName, Callable[[Settings], VisionProvider]] = {
    "openai": _openai,
    "anthropic": _anthropic,
    "compatible": _compatible,
}


def _require(secret: SecretStr | None, name: str) -> str:
    value = secret.get_secret_value() if secret else ""
    if not value:
        raise ConfigurationError(f"{name} is not set. Put it into .env (see .env.example).")
    return value


class _LazyProvider:
    """Builds the real client on first use, so offline commands need no API key."""

    def __init__(self, factory: Callable[[], VisionProvider]) -> None:
        self._factory = factory
        self._provider: VisionProvider | None = None

    @property
    def _get(self) -> VisionProvider:
        if self._provider is None:
            self._provider = self._factory()
        return self._provider

    def understand(
        self, pages: Sequence[PageImage], context: UnderstandingContext
    ) -> Understanding:
        return self._get.understand(pages, context)

    def review(
        self,
        originals: Sequence[PageImage],
        rendered: Sequence[PageImage],
        document: Document,
        context: UnderstandingContext,
    ) -> Reviewed:
        return self._get.review(originals, rendered, document, context)

    def edit(self, document: Document, request: str) -> Reviewed:
        return self._get.edit(document, request)

    def fill_form(self, pages: Sequence[PageImage], sample: list[str]) -> FormFill:
        return self._get.fill_form(pages, sample)


def build_vision_model(settings: Settings, provider: ProviderName | None = None) -> VisionProvider:
    factory = PROVIDERS[provider or settings.provider]
    return _LazyProvider(lambda: factory(settings))


def build_previewer(settings: Settings) -> Previewer | None:
    return detect_previewer() if settings.preview == "auto" else None


def build_second_reader(settings: Settings) -> SecondReader | None:
    return _yandex(settings) or _windows_ocr()


def build_line_reader(settings: Settings) -> LineReader | None:
    """Exact text-line geometry for the layout measurement: Yandex Vision OCR if configured,
    else Windows' own offline OCR."""
    return _yandex(settings) or _windows_ocr()


@cache  # one reader: the text check reuses the lines the layout read
def _windows_ocr() -> WindowsOcrReader | None:
    return WindowsOcrReader() if windows_ocr_available() else None


def _yandex(settings: Settings) -> YandexVisionReader | None:
    key = settings.yandex_api_key.get_secret_value() if settings.yandex_api_key else ""
    if not key or not settings.yandex_folder_id:
        return None
    return YandexVisionReader(key, settings.yandex_folder_id)


def build_converter(
    settings: Settings,
    provider: ProviderName | None = None,
    profiles_dir: Path | None = None,
    previewer: Previewer | None = None,
) -> ConvertDocument:
    vision = build_vision_model(settings, provider)
    renderer = DocxRenderer()
    previewer = previewer or build_previewer(settings)
    review_loop = (
        ReviewLoop(vision, previewer, renderer, max_rounds=settings.review_max_rounds)
        if previewer is not None
        else None
    )
    return ConvertDocument(
        vision=vision,
        renderer=renderer,
        profiles=YamlProfileRepository(profiles_dir or builtin_profiles_dir()),
        review_loop=review_loop,
        verifier=DocumentVerifier(build_second_reader(settings)),
        cutter=PillowImageCutter(),
        layout=ProjectionLayoutEstimator(),
        lines=build_line_reader(settings),
        rectifier=OpenCvPageRectifier(),
        fitter=RenderLayoutFitter(renderer, previewer) if previewer is not None else None,
        forms=DocxFormLibrary(builtin_forms_dir()),
        filler=vision,
    )


def build_image_loader(settings: Settings) -> PillowImageLoader:
    return PillowImageLoader(max_side_px=settings.image_max_side_px)


def build_web_app(settings: Settings, workers: int = 2) -> FastAPI:
    """The web service: background analysis on a small thread pool, sessions kept in memory."""
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="f2w-analysis")
    previewer = build_previewer(settings)
    converter = build_converter(settings, previewer=previewer)
    service = SessionService(
        converter,
        InMemorySessionStore(),
        DEFAULT_CATALOG,
        run=lambda job: _submit(executor, job),
        previewer=previewer,
        editor=build_vision_model(settings),
    )
    app = create_app(service, build_image_loader(settings), DEFAULT_CATALOG)
    app.router.on_shutdown.append(lambda: executor.shutdown(wait=False, cancel_futures=True))
    return app


def _submit(executor: ThreadPoolExecutor, job: Callable[[], None]) -> None:
    executor.submit(job)
