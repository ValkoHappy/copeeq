"""Verification: deterministic checks that tell a human where to look before trusting the result."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from foto2word.domain.document import Correction, Document, ExtractedField, FieldKind
from foto2word.domain.images import PageImage
from foto2word.domain.validation import VALIDATORS

_DIGIT_KINDS = frozenset(
    {
        FieldKind.DATE,
        FieldKind.MONEY,
        FieldKind.INN,
        FieldKind.PASSPORT,
        FieldKind.PHONE,
        FieldKind.NUMBER,
    }
)
_NOT_TEXT = re.compile(r"[\s\"'«»“”„.,:;]+")


class FlagKind(StrEnum):
    INVALID_VALUE = "invalid_value"
    """The value fails a format or checksum check (INN, date, phone...)."""
    NOT_IN_TEXT = "not_in_text"
    """The model reported a field that is not present in its own block text."""
    SECOND_READER_MISMATCH = "second_reader_mismatch"
    """An independent OCR engine did not see this value on the photo."""
    LOW_CONFIDENCE = "low_confidence"
    CORRECTION_FAILED = "correction_failed"


@dataclass(frozen=True, slots=True)
class Flag:
    kind: FlagKind
    block_id: str
    message: str
    value: str = ""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    flags: tuple[Flag, ...] = ()
    checked_with_second_reader: bool = False

    @property
    def ok(self) -> bool:
        return not self.flags


class SecondReader(Protocol):
    """An independent text recogniser (classic OCR), used only to cross-check values."""

    def read_text(self, pages: Sequence[PageImage]) -> str: ...


def _squash(text: str) -> str:
    return _NOT_TEXT.sub("", text).casefold()


class DocumentVerifier:
    def __init__(
        self, second_reader: SecondReader | None = None, low_confidence: float = 0.8
    ) -> None:
        self._second_reader = second_reader
        self._low_confidence = low_confidence

    def verify(
        self,
        document: Document,
        pages: Sequence[PageImage] = (),
        failed_corrections: Sequence[Correction] = (),
    ) -> VerificationReport:
        flags: list[Flag] = []
        texts = {block.id: _squash(block.text()) for block in document.blocks}
        for field in document.fields:
            flags += self._check_field(field, texts)
        flags += [
            Flag(FlagKind.LOW_CONFIDENCE, b.id, f"Неуверенное чтение ({b.confidence:.0%})")
            for b in document.blocks
            if b.confidence < self._low_confidence
        ]
        flags += [
            Flag(FlagKind.CORRECTION_FAILED, c.block_id, "Правку не удалось применить", c.before)
            for c in failed_corrections
        ]
        checked = False
        if self._second_reader is not None and pages:
            flags += self._cross_check(document.fields, self._second_reader.read_text(pages))
            checked = True
        return VerificationReport(tuple(flags), checked)

    @staticmethod
    def _check_field(field: ExtractedField, texts: dict[str, str]) -> list[Flag]:
        flags = []
        validator = VALIDATORS.get(field.kind)
        if validator is not None and not validator(field.value):
            flags.append(
                Flag(
                    FlagKind.INVALID_VALUE,
                    field.block_id,
                    f"Некорректное значение: {field.kind}",
                    field.value,
                )
            )
        if _squash(field.value) not in texts.get(field.block_id, ""):
            flags.append(
                Flag(
                    FlagKind.NOT_IN_TEXT, field.block_id, "Значения нет в тексте блока", field.value
                )
            )
        return flags

    @staticmethod
    def _cross_check(fields: Sequence[ExtractedField], ocr_text: str) -> list[Flag]:
        seen = _squash(ocr_text)
        return [
            Flag(
                FlagKind.SECOND_READER_MISMATCH,
                field.block_id,
                "Второе распознавание прочитало это значение иначе",
                field.value,
            )
            for field in fields
            if field.kind in _DIGIT_KINDS and _squash(field.value) not in seen
        ]
