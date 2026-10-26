from pathlib import Path

import pytest

from foto2word.domain.errors import InvalidProfileError, ProfileNotFoundError
from foto2word.infrastructure.profiles.yaml_repository import YamlProfileRepository


def test_child_profile_overrides_only_what_it_declares(profiles: YamlProfileRepository) -> None:
    base_like = profiles.get("act")
    application = profiles.get("application")

    assert application.styles.title.all_caps is False
    assert application.styles.title.font == "Times New Roman"
    assert application.styles.requisites == base_like.styles.requisites
    assert application.page == base_like.page


def test_abstract_profiles_are_not_selectable(profiles: YamlProfileRepository) -> None:
    assert "base" not in profiles.ids()
    with pytest.raises(ProfileNotFoundError):
        profiles.get("base")


def test_profile_is_chosen_by_document_type_with_generic_fallback(
    profiles: YamlProfileRepository,
) -> None:
    assert profiles.for_document_type("act").id == "act"
    assert profiles.for_document_type("contract").id == "generic"


def test_cyclic_extends_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("id: a\nextends: b\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("id: b\nextends: a\n", encoding="utf-8")

    with pytest.raises(InvalidProfileError, match="Cyclic"):
        YamlProfileRepository(tmp_path, default_profile_id="a")


def test_missing_default_profile_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ProfileNotFoundError):
        YamlProfileRepository(tmp_path)
