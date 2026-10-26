from pathlib import Path

import pytest

from foto2word.domain.document import Document
from foto2word.infrastructure.profiles.yaml_repository import (
    YamlProfileRepository,
    builtin_profiles_dir,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "fixtures" / "cases"


def load_case(case_id: str) -> Document:
    text = (CASES / case_id / "expected.docmodel.json").read_text(encoding="utf-8")
    return Document.model_validate_json(text)


@pytest.fixture
def act() -> Document:
    return load_case("act-hydro-001")


@pytest.fixture
def application() -> Document:
    return load_case("application-001")


@pytest.fixture
def profiles() -> YamlProfileRepository:
    return YamlProfileRepository(builtin_profiles_dir())
