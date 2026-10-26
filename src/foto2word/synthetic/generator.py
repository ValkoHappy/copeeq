"""Writes synthetic eval cases: a phone-like photo plus the exact expected DocModel."""

import random
from dataclasses import dataclass
from pathlib import Path

from foto2word.application.ports import ProfileRepository
from foto2word.evaluation.cases import EXPECTED_FILE
from foto2word.infrastructure.raster.camera import PhoneCamera
from foto2word.infrastructure.raster.fonts import FontSet
from foto2word.infrastructure.raster.page import PageRasterizer
from foto2word.infrastructure.raster.pencil import PencilAnnotator
from foto2word.synthetic.factory import DocumentFactory


@dataclass(frozen=True, slots=True)
class SyntheticCase:
    directory: Path
    document_type: str
    corrections: int


class SyntheticCaseGenerator:
    def __init__(self, fonts: FontSet, profiles: ProfileRepository, seed: int = 0) -> None:
        self._fonts = fonts
        self._profiles = profiles
        self._seed = seed

    def generate(self, count: int, out_dir: Path) -> list[SyntheticCase]:
        return [self.generate_one(index, out_dir) for index in range(count)]

    def generate_one(self, index: int, out_dir: Path) -> SyntheticCase:
        rng = random.Random(self._seed * 1_000_003 + index)
        document = DocumentFactory(rng).create()
        profile = self._profiles.for_document_type(document.document_type.id)
        page = PageRasterizer(self._fonts, profile).render(document)
        drawn = PencilAnnotator(self._fonts, rng).annotate(page, document)
        # Only edits that really appear on the photo belong to the ground truth.
        expected = document.model_copy(update={"corrections": tuple(drawn)})
        photo = PhoneCamera(rng).shoot(page.image)

        case_dir = out_dir / f"synth-{self._seed:03d}-{index:04d}"
        case_dir.mkdir(parents=True, exist_ok=True)
        photo.save(case_dir / "photo-1.jpg", quality=92)
        (case_dir / EXPECTED_FILE).write_text(expected.model_dump_json(indent=2), encoding="utf-8")
        return SyntheticCase(case_dir, document.document_type.id, len(drawn))
