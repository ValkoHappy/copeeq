"""Shared flow for vision providers that return structured (schema-bound) answers.

Template method: subclasses only know how to format text/image parts and how to send one
request to their API. What to ask, in which order, and with which prompt is decided here,
identically for every provider.
"""

import base64
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel

from foto2word.application.ports import (
    Provenance,
    Reviewed,
    Understanding,
    UnderstandingContext,
    Usage,
)
from foto2word.domain.document import Document
from foto2word.domain.images import PageImage
from foto2word.domain.patches import ReviewResult
from foto2word.domain.templates import FormFill
from foto2word.infrastructure.providers.prompting import Prompts

Part = dict[str, Any]


class StructuredVisionModel(ABC):
    def __init__(self, prompts: Prompts | None = None) -> None:
        self._prompts = prompts or Prompts()

    def understand(
        self, pages: Sequence[PageImage], context: UnderstandingContext
    ) -> Understanding:
        content = [
            *self._images(pages, self._prompts.photo_label),
            self._text(self._prompts.understand_instruction(context)),
        ]
        document, provenance = self._ask(
            self._prompts.understand_system(context),
            content,
            Document,
            self._prompts.understand_version,
        )
        return Understanding(document, provenance)

    def review(
        self,
        originals: Sequence[PageImage],
        rendered: Sequence[PageImage],
        document: Document,
        context: UnderstandingContext,
    ) -> Reviewed:
        content = [
            *self._images(originals, self._prompts.photo_label),
            *self._images(rendered, self._prompts.rendered_label),
            self._text(self._prompts.review_instruction(document)),
        ]
        result, provenance = self._ask(
            self._prompts.review_system(), content, ReviewResult, self._prompts.review_version
        )
        return Reviewed(result, provenance)

    def edit(self, document: Document, request: str) -> Reviewed:
        content = [self._text(self._prompts.edit_instruction(document, request))]
        result, provenance = self._ask(
            self._prompts.edit_system(), content, ReviewResult, self._prompts.edit_version
        )
        return Reviewed(result, provenance)

    def fill_form(self, pages: Sequence[PageImage], sample: list[str]) -> FormFill:
        """Replacements that turn the form's filled sample into the photographed form."""
        content = [
            *self._images(pages, self._prompts.photo_label),
            self._text(self._prompts.fill_instruction(sample)),
        ]
        result, _ = self._ask(
            self._prompts.fill_system(), content, FormFill, self._prompts.fill_version
        )
        return result

    def _images(self, pages: Sequence[PageImage], label: Callable[[int, int], str]) -> list[Part]:
        content: list[Part] = []
        for number, page in enumerate(pages, start=1):
            content += [self._text(label(number, len(pages))), self._image(page)]
        return content

    @abstractmethod
    def _text(self, text: str) -> Part: ...

    @abstractmethod
    def _image(self, page: PageImage) -> Part: ...

    @abstractmethod
    def _ask[T: BaseModel](
        self, system: str, content: list[Part], output: type[T], prompt_version: str
    ) -> tuple[T, Provenance]:
        """Send one request and return the validated answer with its provenance."""


def usage_from(response: Any, input_attr: str, output_attr: str) -> Usage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    return Usage(int(getattr(usage, input_attr, 0) or 0), int(getattr(usage, output_attr, 0) or 0))


def data_url(page: PageImage) -> str:
    encoded = base64.standard_b64encode(page.data).decode("ascii")
    return f"data:{page.media_type};base64,{encoded}"
