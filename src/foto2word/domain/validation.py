"""Deterministic checks of extracted values. A failed check means "a human must look here"."""

import re
from collections.abc import Callable
from datetime import date

from foto2word.domain.document import FieldKind

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
INN_LEGAL_LENGTH = 10
INN_PERSONAL_LENGTH = 12
_PHONE_FULL_LENGTH = 11
_PHONE_LOCAL_LENGTH = 10
_CENTURY = 2000
_TWO_DIGIT_YEAR_LIMIT = 100
_INN10_WEIGHTS = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_WEIGHTS_1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_WEIGHTS_2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)

_NUMERIC_DATE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
_TEXT_DATE = re.compile(r"«?\s*(\d{1,2})\s*»?\s+([а-яё]+)\s+(\d{4})", re.IGNORECASE)
_PASSPORT = re.compile(r"^\d{2}\s?\d{2}\s?№?\s?\d{6}$")
_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def inn_check_digit(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def is_valid_inn(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) == INN_LEGAL_LENGTH:
        return inn_check_digit(digits, _INN10_WEIGHTS) == int(digits[9])
    if len(digits) == INN_PERSONAL_LENGTH:
        return inn_check_digit(digits, _INN12_WEIGHTS_1) == int(digits[10]) and inn_check_digit(
            digits, _INN12_WEIGHTS_2
        ) == int(digits[11])
    return False


def complete_inn12(first_ten: str) -> str:
    """Append the two check digits to the first ten digits of a personal INN."""
    with_11 = first_ten + str(inn_check_digit(first_ten, _INN12_WEIGHTS_1))
    return with_11 + str(inn_check_digit(with_11, _INN12_WEIGHTS_2))


def parse_date(value: str) -> date | None:
    """Understands '13.05.2022', '13/05/22' and '«12» января 2026 г.'; None if not a real date."""
    numeric = _NUMERIC_DATE.search(value)
    if numeric:
        day, month, year = (int(g) for g in numeric.groups())
    else:
        text = _TEXT_DATE.search(value)
        if not text:
            return None
        month_name = text.group(2).lower()
        if month_name not in MONTHS_GENITIVE:
            return None
        day, month, year = (
            int(text.group(1)),
            MONTHS_GENITIVE.index(month_name) + 1,
            int(text.group(3)),
        )
    if year < _TWO_DIGIT_YEAR_LIMIT:
        year += _CENTURY
    try:
        return date(year, month, day)
    except ValueError:
        return None


def is_valid_passport(value: str) -> bool:
    return bool(_PASSPORT.match(value.strip()))


def is_valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    full = len(digits) == _PHONE_FULL_LENGTH and digits[0] in "78"
    local = len(digits) == _PHONE_LOCAL_LENGTH and digits[0] == "9"
    return full or local


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL.match(value.strip()))


VALIDATORS: dict[FieldKind, Callable[[str], bool]] = {
    FieldKind.INN: is_valid_inn,
    FieldKind.DATE: lambda value: parse_date(value) is not None,
    FieldKind.PASSPORT: is_valid_passport,
    FieldKind.PHONE: is_valid_phone,
    FieldKind.EMAIL: is_valid_email,
}
