"""Anthropic (Claude) adapter: Messages API with structured outputs."""

import base64
from typing import Any

import anthropic
from pydantic import BaseModel

from foto2word.application.ports import Provenance
from foto2word.domain.errors import VisionModelError
from foto2word.domain.images import PageImage
from foto2word.infrastructure.providers.base import Part, StructuredVisionModel, usage_from
from foto2word.infrastructure.providers.prompting import Prompts

PROVIDER = "anthropic"
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeVisionModel(StructuredVisionModel):
    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str,
        *,
        effort: str = "high",
        max_tokens: int = 16_000,
        server_fallbacks: bool = True,
        prompts: Prompts | None = None,
    ) -> None:
        super().__init__(prompts)
        self._client = client
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self._server_fallbacks = server_fallbacks

    def _text(self, text: str) -> Part:
        return {"type": "text", "text": text}

    def _image(self, page: PageImage) -> Part:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": page.media_type,
                "data": base64.standard_b64encode(page.data).decode("ascii"),
            },
        }

    def _ask[T: BaseModel](
        self, system: str, content: list[Part], output: type[T], prompt_version: str
    ) -> tuple[T, Provenance]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": self._effort},
            "output_format": output,
        }
        if self._server_fallbacks:
            request |= {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self._client.beta.messages.parse(**request)
        except anthropic.APIError as error:
            raise VisionModelError(f"Claude request failed: {error}") from error

        if response.stop_reason == "refusal":
            raise VisionModelError("Claude declined to process the document")
        if response.stop_reason == "max_tokens":
            raise VisionModelError("Claude output was truncated; raise F2W_CLAUDE_MAX_TOKENS")
        parsed = response.parsed_output
        if not isinstance(parsed, output):
            raise VisionModelError("Claude returned no structured output")
        usage = usage_from(response, "input_tokens", "output_tokens")
        return parsed, Provenance(PROVIDER, response.model, prompt_version, usage)
