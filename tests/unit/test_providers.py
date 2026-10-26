import json
from types import SimpleNamespace
from typing import Any, cast

import anthropic
import openai
import pytest

from foto2word.application.ports import UnderstandingContext
from foto2word.domain.catalog import DEFAULT_CATALOG
from foto2word.domain.document import Document
from foto2word.domain.errors import VisionModelError
from foto2word.domain.images import PageImage
from foto2word.infrastructure.providers.anthropic_provider import ClaudeVisionModel
from foto2word.infrastructure.providers.openai_provider import OpenAIVisionModel
from foto2word.infrastructure.providers.schema import drop_nulls, strict_json_schema

PAGES = [PageImage(b"\xff\xd8jpeg", "image/jpeg", "p1.jpg")]
CONTEXT = UnderstandingContext(DEFAULT_CATALOG, document_type_hint="act")


class Recorder:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def _with_nulls(document: Document) -> dict[str, Any]:
    """Imitates strict-mode output: every optional field present, null when absent."""
    return cast(dict[str, Any], json.loads(document.model_dump_json()))


# --- OpenAI -------------------------------------------------------------------------------


def _openai(response: Any) -> tuple[OpenAIVisionModel, Recorder]:
    create = Recorder(response)
    client = cast(openai.OpenAI, SimpleNamespace(responses=SimpleNamespace(create=create)))
    return OpenAIVisionModel(client, model="gpt-test"), create


def _openai_response(text: str, status: str = "completed") -> SimpleNamespace:
    return SimpleNamespace(
        status=status, output_text=text, model="gpt-test", incomplete_details=None
    )


def test_openai_request_contains_images_schema_and_prompt(act: Document) -> None:
    model, create = _openai(_openai_response(json.dumps(_with_nulls(act))))

    understanding = model.understand(PAGES, CONTEXT)

    assert understanding.document == act
    assert understanding.provenance.provider == "openai"
    request = create.kwargs
    content = request["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert "`act`" in content[-1]["text"]
    assert request["text"]["format"]["strict"] is True
    assert "дословно" in request["instructions"]
    assert "`application`" in request["instructions"]


@pytest.mark.parametrize(
    "response",
    [
        _openai_response("", "completed"),
        _openai_response("{}", "incomplete"),
        _openai_response("{"),
    ],
)
def test_openai_unusable_answers_raise(response: SimpleNamespace) -> None:
    model, _ = _openai(response)

    with pytest.raises(VisionModelError):
        model.understand(PAGES, CONTEXT)


def test_strict_schema_lists_every_property_as_required() -> None:
    schema = strict_json_schema(Document)
    serialized = json.dumps(schema)

    def objects(node: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                found.append(node)
            for value in node.values():
                found += objects(value)
        elif isinstance(node, list):
            for value in node:
                found += objects(value)
        return found

    for obj in objects(schema):
        assert set(obj["required"]) == set(obj["properties"])
        assert obj["additionalProperties"] is False
    for forbidden in ('"default"', '"oneOf"', '"discriminator"', '"const"'):
        assert forbidden not in serialized


def test_drop_nulls_is_recursive() -> None:
    assert drop_nulls({"a": None, "b": [{"c": None, "d": 1}]}) == {"b": [{"d": 1}]}


# --- Anthropic ----------------------------------------------------------------------------


def _claude(response: Any, fallbacks: bool = True) -> tuple[ClaudeVisionModel, Recorder]:
    parse = Recorder(response)
    client = cast(
        anthropic.Anthropic,
        SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse))),
    )
    return ClaudeVisionModel(client, model="claude-test", server_fallbacks=fallbacks), parse


def test_claude_request_and_parsed_output(act: Document) -> None:
    response = SimpleNamespace(stop_reason="end_turn", parsed_output=act, model="claude-test")
    model, parse = _claude(response)

    understanding = model.understand(PAGES, CONTEXT)

    assert understanding.document == act
    request = parse.kwargs
    assert request["output_format"] is Document
    assert request["output_config"] == {"effort": "high"}
    assert request["fallbacks"] == "default"
    assert request["messages"][0]["content"][1]["source"]["media_type"] == "image/jpeg"
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_claude_fallbacks_can_be_disabled(act: Document) -> None:
    response = SimpleNamespace(stop_reason="end_turn", parsed_output=act, model="claude-test")
    model, parse = _claude(response, fallbacks=False)

    model.understand(PAGES, CONTEXT)

    assert "fallbacks" not in parse.kwargs
    assert "betas" not in parse.kwargs


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_refusal_and_truncation_raise(stop_reason: str) -> None:
    response = SimpleNamespace(stop_reason=stop_reason, parsed_output=None, model="claude-test")
    model, _ = _claude(response)

    with pytest.raises(VisionModelError):
        model.understand(PAGES, CONTEXT)
