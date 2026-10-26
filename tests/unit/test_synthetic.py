import random
from pathlib import Path

import pytest
from PIL import Image

from foto2word.domain.corrections import CorrectionApplier, accept_all
from foto2word.domain.document import Document
from foto2word.domain.validation import VALIDATORS
from foto2word.evaluation.cases import load_cases
from foto2word.infrastructure.profiles.yaml_repository import YamlProfileRepository
from foto2word.infrastructure.raster.camera import PhoneCamera, _perspective_coefficients
from foto2word.infrastructure.raster.fonts import FontNotFoundError, FontSet
from foto2word.infrastructure.raster.page import PageRasterizer
from foto2word.infrastructure.raster.pencil import PencilAnnotator
from foto2word.synthetic.factory import DocumentFactory
from foto2word.synthetic.generator import SyntheticCaseGenerator


@pytest.fixture(scope="module")
def fonts() -> FontSet:
    try:
        return FontSet.discover()
    except FontNotFoundError:
        pytest.skip("No Cyrillic TrueType fonts on this machine")


@pytest.mark.parametrize("seed", range(30))
def test_factory_documents_are_consistent(seed: int) -> None:
    document = DocumentFactory(random.Random(seed)).create()

    outcome = CorrectionApplier().apply(document, accept_all)

    assert outcome.failed == ()
    block_ids = {b.id for b in document.blocks}
    assert all(f.block_id in block_ids for f in document.fields)
    for field in document.fields:
        validator = VALIDATORS.get(field.kind)
        assert validator is None or validator(field.value), field
    text = " ".join(document.iter_text())
    assert all(s.text in text for s in document.suggestions)


def test_rasterizer_locates_every_correction(
    fonts: FontSet, act: Document, profiles: YamlProfileRepository
) -> None:
    page = PageRasterizer(fonts, profiles.get("act")).render(act)

    for correction in act.corrections:
        box = page.locate(correction.block_id, correction.before)
        assert box is not None
        x0, y0, x1, y1 = box
        assert 0 < x0 < x1 < page.image.width
        assert 0 < y0 < y1 < page.image.height
    assert set(page.block_boxes) == {b.id for b in act.blocks}
    assert page.signature_slots.keys() == {"b19", "b20", "b21"}


def test_pencil_draws_only_locatable_corrections(
    fonts: FontSet, act: Document, profiles: YamlProfileRepository
) -> None:
    page = PageRasterizer(fonts, profiles.get("act")).render(act)
    before = page.image.copy()
    broken = act.model_copy(
        update={
            "corrections": (
                *act.corrections,
                act.corrections[0].model_copy(update={"before": "нет такого"}),
            )
        }
    )

    drawn = PencilAnnotator(fonts, random.Random(1)).annotate(page, broken)

    assert drawn == list(act.corrections)
    assert page.image.tobytes() != before.tobytes()


def test_camera_returns_rgb_photo_larger_than_page() -> None:
    page = Image.new("RGB", (400, 560), "white")

    photo = PhoneCamera(random.Random(3)).shoot(page)

    assert photo.mode == "RGB"
    assert photo.width > page.width


def test_perspective_identity() -> None:
    corners = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]

    coefficients = _perspective_coefficients(corners, corners)

    assert coefficients == pytest.approx((1, 0, 0, 0, 1, 0, 0, 0), abs=1e-9)


def test_generator_writes_loadable_cases(
    fonts: FontSet, profiles: YamlProfileRepository, tmp_path: Path
) -> None:
    created = SyntheticCaseGenerator(fonts, profiles, seed=7).generate(3, tmp_path)

    cases = load_cases(tmp_path)
    assert [c.id for c in cases] == [c.directory.name for c in created]
    assert all(len(c.photos) == 1 for c in cases)
    again = SyntheticCaseGenerator(fonts, profiles, seed=7).generate_one(0, tmp_path / "again")
    assert (again.directory / "expected.docmodel.json").read_text("utf-8") == (
        created[0].directory / "expected.docmodel.json"
    ).read_text("utf-8")
