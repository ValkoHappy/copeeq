"""OpenAI adapter: Responses API with strict structured outputs."""

from typing import Any

import openai
from pydantic import BaseModel

from foto2word.application.ports import Provenance
from foto2word.domain.errors import VisionModelError
from foto2word.domain.images import PageImage
from foto2word.infrastructure.providers.base import (
    Part,
    StructuredVisionModel,
    data_url,
    usage_from,
)
from foto2word.infrastructure.providers.prompting import Prompts
from foto2word.infrastructure.providers.schema import SchemaCache, parse_json

PROVIDER = "openai"


class OpenAIVisionModel(StructuredVisionModel):
    def __init__(
        self,
        client: openai.OpenAI,
        model: str,
        *,
        reasoning_effort: str = "high",
        max_output_tokens: int = 32_000,
        image_detail: str = "high",
        prompts: Prompts | None = None,
    ) -> None:
        super().__init__(prompts)
        self._client = client
        self._model = model
        self._effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._detail = image_detail
        self._schemas = SchemaCache()

    def _text(self, text: str) -> Part:
        return {"type": "input_text", "text": text}

    def _image(self, page: PageImage) -> Part:
        return {"type": "input_image", "image_url": data_url(page), "detail": self._detail}

    def _ask[T: BaseModel](
        self, system: str, content: list[Part], output: type[T], prompt_version: str
    ) -> tuple[T, Provenance]:
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": system,
            "input": [{"role": "user", "content": content}],
            "reasoning": {"effort": self._effort},
            "max_output_tokens": self._max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": output.__name__.lower(),
                    "schema": self._schemas.get(output),
                    "strict": True,
                }
            },
            "store": False,
        }
        try:
            response = self._client.responses.create(**request)
        except openai.OpenAIError as error:
            raise VisionModelError(f"OpenAI request failed: {error}") from error

        if response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else "?"
            raise VisionModelError(f"OpenAI response is incomplete: {reason}")
        if not response.output_text:
            raise VisionModelError("OpenAI returned no structured output (refusal or empty)")
        usage = usage_from(response, "input_tokens", "output_tokens")
        provenance = Provenance(PROVIDER, response.model, prompt_version, usage)
        return parse_json(response.output_text, output, PROVIDER), provenance
