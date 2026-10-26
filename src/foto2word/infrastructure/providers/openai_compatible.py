"""Any OpenAI-compatible Chat Completions endpoint with vision.

One adapter for many backends: OpenRouter (Qwen-VL, Gemini, ...), Yandex AI Studio,
self-hosted vLLM / Ollama. Servers without strict JSON Schema support can be used with
`strict=False`: the schema then goes into the prompt and the answer is validated locally.
"""

import json
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

PROVIDER = "compatible"


class OpenAICompatibleVisionModel(StructuredVisionModel):
    def __init__(
        self,
        client: openai.OpenAI,
        model: str,
        *,
        strict: bool = True,
        max_tokens: int = 32_000,
        provider_label: str = PROVIDER,
        prompts: Prompts | None = None,
    ) -> None:
        super().__init__(prompts)
        self._client = client
        self._model = model
        self._strict = strict
        self._max_tokens = max_tokens
        self._label = provider_label
        self._schemas = SchemaCache()

    def _text(self, text: str) -> Part:
        return {"type": "text", "text": text}

    def _image(self, page: PageImage) -> Part:
        return {"type": "image_url", "image_url": {"url": data_url(page)}}

    def _ask[T: BaseModel](
        self, system: str, content: list[Part], output: type[T], prompt_version: str
    ) -> tuple[T, Provenance]:
        schema = self._schemas.get(output)
        if self._strict:
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {"name": output.__name__.lower(), "schema": schema, "strict": True},
            }
        else:
            response_format = {"type": "json_object"}
            system += "\n\nОтветь одним JSON-объектом строго по этой JSON Schema:\n" + json.dumps(
                schema, ensure_ascii=False
            )
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_tokens": self._max_tokens,
            "response_format": response_format,
        }
        try:
            response = self._client.chat.completions.create(**request)
        except openai.OpenAIError as error:
            raise VisionModelError(f"{self._label} request failed: {error}") from error

        if not response.choices:
            raise VisionModelError(f"{self._label} returned no choices")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise VisionModelError(f"{self._label} output was truncated")
        message = choice.message
        if getattr(message, "refusal", None) or not message.content:
            raise VisionModelError(f"{self._label} returned no structured output")
        usage = usage_from(response, "prompt_tokens", "completion_tokens")
        provenance = Provenance(self._label, response.model, prompt_version, usage)
        return parse_json(message.content, output, self._label), provenance
