"""Profiles stored as YAML files with single inheritance via `extends`."""

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from foto2word.domain.errors import InvalidProfileError, ProfileNotFoundError
from foto2word.domain.profile import Profile

_META_KEYS = ("extends", "abstract")
DEFAULT_PROFILE_ID = "generic"


def builtin_profiles_dir() -> Path:
    return Path(str(files("foto2word") / "profiles"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class YamlProfileRepository:
    def __init__(self, directory: Path, default_profile_id: str = DEFAULT_PROFILE_ID) -> None:
        raw = self._read_all(directory)
        self._profiles = {
            profile_id: self._build(profile_id, raw)
            for profile_id, data in raw.items()
            if not data.get("abstract", False)
        }
        if default_profile_id not in self._profiles:
            raise ProfileNotFoundError(f"Default profile '{default_profile_id}' is missing")
        self._default_id = default_profile_id

    def get(self, profile_id: str) -> Profile:
        try:
            return self._profiles[profile_id]
        except KeyError:
            known = ", ".join(sorted(self._profiles))
            raise ProfileNotFoundError(f"Unknown profile '{profile_id}'. Known: {known}") from None

    def for_document_type(self, document_type_id: str) -> Profile:
        for profile in self._profiles.values():
            if document_type_id in profile.applies_to:
                return profile
        return self._profiles[self._default_id]

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    @staticmethod
    def _read_all(directory: Path) -> dict[str, dict[str, Any]]:
        raw: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "id" not in data:
                raise InvalidProfileError(f"{path.name}: a profile must be a mapping with an 'id'")
            raw[data["id"]] = data
        return raw

    def _build(self, profile_id: str, raw: dict[str, dict[str, Any]]) -> Profile:
        merged = self._resolve(profile_id, raw, chain=())
        data = {key: value for key, value in merged.items() if key not in _META_KEYS}
        try:
            return Profile.model_validate(data)
        except ValidationError as error:
            raise InvalidProfileError(f"Profile '{profile_id}' is invalid:\n{error}") from error

    def _resolve(
        self, profile_id: str, raw: dict[str, dict[str, Any]], chain: tuple[str, ...]
    ) -> dict[str, Any]:
        if profile_id in chain:
            raise InvalidProfileError(f"Cyclic 'extends': {' -> '.join((*chain, profile_id))}")
        if profile_id not in raw:
            raise ProfileNotFoundError(f"Profile '{profile_id}' is not defined")
        data = raw[profile_id]
        parent_id = data.get("extends")
        if parent_id is None:
            return data
        parent = self._resolve(parent_id, raw, (*chain, profile_id))
        own = {key: value for key, value in data.items() if key != "abstract"}
        return _deep_merge(parent, own)
