"""The library of unified forms: reference Word files recognised by the marks printed on them."""

import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml

from foto2word.domain.document import Document
from foto2word.domain.templates import FormTemplate
from foto2word.infrastructure.importing.docx_importer import DocxImporter

_NOT_TEXT = re.compile(r"[\W_]+")


def builtin_forms_dir() -> Path:
    return Path(str(files("foto2word") / "forms"))


@dataclass(frozen=True, slots=True)
class _Entry:
    id: str
    title: str
    file: Path
    marks: tuple[str, ...]


class DocxFormLibrary:
    """A form is recognised when the photo's text holds one of its marks — the OKUD code or the
    'Унифицированная форма № …' line — compared on whole words of letters and digits, so Т-8
    is not found in Т-8а nor an OKUD code inside a longer number."""

    def __init__(self, directory: Path) -> None:
        manifest = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
        self._entries = [
            _Entry(
                id=str(item["id"]),
                title=str(item["title"]),
                file=directory / str(item["file"]),
                marks=tuple(_squash(str(mark)) for mark in item["marks"]),
            )
            for item in manifest
        ]

    def match(self, document: Document) -> FormTemplate | None:
        text = f" {_squash(' '.join(document.iter_text()))} "
        scored = [(sum(f" {mark} " in text for mark in e.marks), e) for e in self._entries]
        hits, entry = max(scored, key=lambda pair: pair[0], default=(0, None))
        if entry is None or hits == 0:
            return None
        importer = DocxImporter(document.document_type.id, entry.title)
        reference = importer.load(entry.file)
        return FormTemplate(entry.id, entry.title, reference, dict(importer.images))


def _squash(text: str) -> str:
    return " ".join(_NOT_TEXT.sub(" ", text).casefold().split())
