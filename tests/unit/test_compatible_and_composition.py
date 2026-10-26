import json
import sys
from types import SimpleNamespace
from typing import Any, cast

import openai
import pytest
from pydantic import SecretStr

from foto2word.application.convert import ConversionOptions
from foto2word.application.ports import UnderstandingContext, Usage
from foto2word.composition import ConfigurationError, build_converter, build_second_reader
from foto2word.domain.catalog import DEFAULT_CATALOG
from foto2word.domain.document import Document
from foto2word.domain.errors import VisionModelError
from foto2word.domain.images import PageImage
from foto2word.infrastructure.config import Settings
from foto2word.infrastructure.ocr.windows import WindowsOcrReader
from foto2word.infrastructure.ocr.yandex import YandexVisionReader
from foto2word.infrastructure.providers.openai_compatible import OpenAICompatibleVisionModel

PAGE = PageImage(b"jpeg", "image/jpeg", "p.jpg")
CONTEXT = UnderstandingContext(DEFAULT_CATALOG)


def _model(
    content: str | None, finish_reason: str = "stop", strict: bool = True
) -> tuple[OpenAICompatibleVisionModel, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        message = SimpleNamespace(content=content, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
            model="qwen-vl",
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    client = cast(
        openai.OpenAI,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    model = OpenAICompatibleVisionModel(
        client, "qwen-vl", strict=strict, provider_label="openrouter"
    )
    return model, captured


def test_compatible_strict_request(act: Document) -> None:
    model, captured = _model(act.model_dump_json())

    understanding = model.understand([PAGE], CONTEXT)

    assert understanding.document == act
    assert understanding.provenance.provider == "openrouter"
    assert understanding.provenance.usage == Usage(7, 3)
    assert captured["response_format"]["json_schema"]["strict"] is True
    user = captured["messages"][1]["content"]
    assert user[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,anBlZw=="},
    }


def test_compatible_non_strict_puts_schema_into_prompt(act: Document) -> None:
    model, captured = _model(act.model_dump_json(), strict=False)

    model.understand([PAGE], CONTEXT)

    assert captured["response_format"] == {"type": "json_object"}
    system = captured["messages"][0]["content"]
    schema = json.loads(system.split("JSON Schema:\n", 1)[1])
    assert "blocks" in schema["properties"]


@pytest.mark.parametrize(("content", "finish"), [(None, "stop"), ("{}", "length"), ("[]", "stop")])
def test_compatible_unusable_answers_raise(content: str | None, finish: str) -> None:
    model, _ = _model(content, finish)

    with pytest.raises(VisionModelError):
        model.understand([PAGE], CONTEXT)


def test_compatible_provider_requires_url_and_model() -> None:
    converter = build_converter(Settings(provider="compatible", _env_file=None), previewer=None)

    with pytest.raises(ConfigurationError, match="COMPATIBLE"):
        converter.execute([PAGE], ConversionOptions())


def test_second_reader_is_yandex_when_configured_else_windows_ocr() -> None:
    fallback = build_second_reader(Settings(_env_file=None))
    assert isinstance(fallback, WindowsOcrReader) if sys.platform == "win32" else fallback is None
    reader = build_second_reader(
        Settings(_env_file=None, yandex_api_key=SecretStr("k"), yandex_folder_id="f")
    )
    assert isinstance(reader, YandexVisionReader)
