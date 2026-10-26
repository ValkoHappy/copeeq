import random
from io import BytesIO

import pytest
from PIL import Image

from foto2word.domain.document import Document
from foto2word.domain.images import PageImage
from foto2word.evaluation.template_cases import ink_f1
from foto2word.infrastructure.profiles.yaml_repository import YamlProfileRepository
from foto2word.infrastructure.raster.camera import PhoneCamera
from foto2word.infrastructure.raster.fonts import FontNotFoundError, FontSet
from foto2word.infrastructure.raster.page import PageRasterizer
from foto2word.infrastructure.rectify import OpenCvPageRectifier


def _jpeg(image: Image.Image) -> PageImage:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    return PageImage(buffer.getvalue(), "image/jpeg", "photo.jpg")


@pytest.mark.parametrize("seed", range(3))
def test_a_photo_taken_at_an_angle_becomes_a_flat_page(
    seed: int, application: Document, profiles: YamlProfileRepository
) -> None:
    try:
        fonts = FontSet.discover()
    except FontNotFoundError:
        pytest.skip("No Cyrillic TrueType fonts on this machine")
    page = PageRasterizer(fonts, profiles.get("application"), dpi=110).render(application).image
    photo = PhoneCamera(random.Random(seed)).shoot(page)

    flat = OpenCvPageRectifier().rectify(_jpeg(photo))

    result = Image.open(BytesIO(flat.data)).convert("RGB").resize(page.size)
    before = ink_f1(page.convert("RGB"), photo.convert("RGB").resize(page.size))
    after = ink_f1(page.convert("RGB"), result)
    assert after > 0.6
    assert after > before + 0.2


def test_a_scan_without_sheet_edges_is_left_alone() -> None:
    scan = Image.new("RGB", (800, 1131), "white")
    page = _jpeg(scan)

    assert OpenCvPageRectifier().rectify(page) is page
