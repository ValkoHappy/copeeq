"""Eval cases on disk: `<cases_dir>/<case_id>/photo-*.<ext>` + `expected.docmodel.json`."""

from dataclasses import dataclass
from pathlib import Path

from foto2word.domain.document import Document

EXPECTED_FILE = "expected.docmodel.json"
PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    photos: tuple[Path, ...]
    expected: Document


def load_cases(directory: Path) -> list[EvalCase]:
    cases = []
    for case_dir in sorted(p for p in directory.iterdir() if (p / EXPECTED_FILE).is_file()):
        photos = tuple(
            sorted(
                p
                for p in case_dir.iterdir()
                if p.name.startswith("photo") and p.suffix.lower() in PHOTO_SUFFIXES
            )
        )
        expected = Document.model_validate_json(
            (case_dir / EXPECTED_FILE).read_text(encoding="utf-8")
        )
        cases.append(EvalCase(case_dir.name, photos, expected))
    return cases
