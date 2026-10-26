from datetime import date

import pytest

from foto2word.domain.document import FieldKind
from foto2word.domain.validation import (
    VALIDATORS,
    complete_inn12,
    is_valid_inn,
    parse_date,
)


@pytest.mark.parametrize("inn", ["000000000000", "7707083893"])
def test_valid_inns(inn: str) -> None:
    assert is_valid_inn(inn)


@pytest.mark.parametrize("inn", ["000000000001", "7707083894", "12345", ""])
def test_invalid_inns(inn: str) -> None:
    assert not is_valid_inn(inn)


def test_complete_inn12_produces_valid_inn() -> None:
    assert is_valid_inn(complete_inn12("0000000000"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("13.05.2022", date(2022, 5, 13)),
        ("1/2/24", date(2024, 2, 1)),
        ("«12» Января 2026г", date(2026, 1, 12)),
        ("«19» октября 2027 г.", date(2027, 10, 19)),
        ("31.02.2024", None),
        ("«5» мартобря 2024", None),
        ("нет даты", None),
    ],
)
def test_parse_date(text: str, expected: date | None) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("kind", "value", "ok"),
    [
        (FieldKind.PASSPORT, "0000 000000", True),
        (FieldKind.PASSPORT, "00 00 № 000000", True),
        (FieldKind.PASSPORT, "0000 00000", False),
        (FieldKind.PHONE, "80000000000", True),
        (FieldKind.PHONE, "+7 (000) 000-00-00", True),
        (FieldKind.PHONE, "000-00-00", False),
        (FieldKind.EMAIL, "person@example.test", True),
        (FieldKind.EMAIL, "person@example", False),
    ],
)
def test_field_validators(kind: FieldKind, value: str, ok: bool) -> None:
    assert VALIDATORS[kind](value) is ok
