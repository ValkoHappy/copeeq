"""«Update for a new period»: finds dates and years in the text and proposes shifted ones.

Deterministic, no model involved. Dates that describe the past (passport issue, birth)
are left alone; the user can still toggle every proposal.
"""

import re
from dataclasses import dataclass
from datetime import date

from foto2word.domain.document import Correction, CorrectionKind, Document
from foto2word.domain.validation import MONTHS_GENITIVE

_MONTHS = "|".join(MONTHS_GENITIVE)
_TEXT_DATE = re.compile(rf"«?\s?(\d{{1,2}})\s?»?\s+({_MONTHS})\s+(\d{{4}})", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_YEAR = re.compile(r"(?<![\d.])((?:19|20)\d{2})(?=\s*(?:г\.|гг\.|г\b|год|года|году|$|[\s,.;)]))")
_HISTORICAL = re.compile(r"(выдан|выдано|рожд|р\.|от\s*$|договор[а-я]*\s+№)", re.IGNORECASE)
_CONTEXT_CHARS = 25
_LEAP_DAY = 29


@dataclass(frozen=True, slots=True)
class _Match:
    start: int
    end: int
    text: str
    shifted: str


def _shift_day(day: int, month: int, year: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:  # 29 February in a non-leap year
        return date(year, month, day - 1)


class DateShifter:
    """Proposes corrections that move every 'current' date/year by N years."""

    def propose(self, document: Document, years: int = 1) -> tuple[Correction, ...]:
        if years == 0:
            return ()
        proposals: list[Correction] = []
        for block in document.blocks:
            block_text = block.text()
            for line in block_text.split("\n"):
                for part in line.split("\t"):
                    for match in self._matches(part, years):
                        if block_text.count(match.text) != 1:
                            continue  # a correction replaces only the first occurrence
                        proposals.append(
                            Correction(
                                id=f"y{len(proposals) + 1}",
                                block_id=block.id,
                                kind=CorrectionKind.REPLACE,
                                before=match.text,
                                after=match.shifted,
                            )
                        )
        return tuple(proposals)

    def _matches(self, text: str, years: int) -> list[_Match]:
        found: list[_Match] = []
        taken: list[tuple[int, int]] = []

        def free(start: int, end: int) -> bool:
            return all(end <= a or start >= b for a, b in taken)

        def historical(start: int) -> bool:
            return bool(_HISTORICAL.search(text[max(0, start - _CONTEXT_CHARS) : start]))

        for m in _TEXT_DATE.finditer(text):
            day, year = int(m.group(1)), int(m.group(3))
            if historical(m.start()):
                continue
            new = m.group(0).replace(m.group(3), str(year + years))
            if day == _LEAP_DAY and m.group(2).lower() == "февраля":
                new = new.replace(str(day), str(_shift_day(day, 2, year + years).day), 1)
            found.append(_Match(m.start(), m.end(), m.group(0), new))
            taken.append((m.start(), m.end()))
        for m in _NUMERIC_DATE.finditer(text):
            if not free(m.start(), m.end()) or historical(m.start()):
                continue
            day, month, year = (int(g) for g in m.groups())
            try:
                shifted = _shift_day(day, month, year + years)
            except ValueError:
                continue
            new = f"{shifted.day:0{len(m.group(1))}d}.{m.group(2)}.{shifted.year}"
            found.append(_Match(m.start(), m.end(), m.group(0), new))
            taken.append((m.start(), m.end()))
        for m in _YEAR.finditer(text):
            if not free(m.start(), m.end()) or historical(m.start()):
                continue
            new = str(int(m.group(1)) + years)
            found.append(_Match(m.start(), m.end(), m.group(1), new))
            taken.append((m.start(), m.end()))
        return sorted(found, key=lambda x: x.start)
