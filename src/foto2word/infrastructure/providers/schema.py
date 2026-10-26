"""JSON Schema helpers for providers with strict structured outputs (e.g. OpenAI).

Strict mode requires every property to be listed in `required`, forbids defaults and
`oneOf`, and needs `additionalProperties: false`. Optional fields become nullable;
nulls are dropped again before validation so that domain defaults apply.
"""

import copy
import json
from typing import Any

from pydantic import BaseModel, ValidationError

from foto2word.domain.errors import VisionModelError

_NULL = {"type": "null"}


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = copy.deepcopy(model.model_json_schema())
    _make_strict(schema)
    return schema


def drop_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: drop_nulls(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [drop_nulls(item) for item in value]
    return value


def _make_strict(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _make_strict(item)
        return
    if not isinstance(node, dict):
        return

    if "oneOf" in node:
        node["anyOf"] = node.pop("oneOf")
    node.pop("discriminator", None)
    if "const" in node:
        node["enum"] = [node.pop("const")]

    properties = node.get("properties")
    if node.get("type") == "object" and isinstance(properties, dict):
        required = set(node.get("required", ()))
        for name in list(properties):
            prop = properties[name]
            prop.pop("default", None)
            if name not in required and not _is_nullable(prop):
                properties[name] = _nullable(prop)
        node["required"] = list(properties)
        node["additionalProperties"] = False

    for child in node.values():
        _make_strict(child)


def _is_nullable(prop: dict[str, Any]) -> bool:
    return _NULL in prop.get("anyOf", ())


def _nullable(prop: dict[str, Any]) -> dict[str, Any]:
    description = prop.pop("description", None)
    wrapped: dict[str, Any] = {"anyOf": [prop, dict(_NULL)]}
    if description:
        wrapped["description"] = description
    return wrapped


class SchemaCache:
    def __init__(self) -> None:
        self._schemas: dict[type[BaseModel], dict[str, Any]] = {}

    def get(self, output: type[BaseModel]) -> dict[str, Any]:
        if output not in self._schemas:
            self._schemas[output] = strict_json_schema(output)
        return self._schemas[output]


def parse_json[T: BaseModel](text: str, output: type[T], provider: str) -> T:
    """Validate a strict-mode JSON answer, letting domain defaults replace nulls."""
    try:
        return output.model_validate(drop_nulls(json.loads(text)))
    except (json.JSONDecodeError, ValidationError) as error:
        raise VisionModelError(
            f"{provider} output does not match {output.__name__}: {error}"
        ) from error
