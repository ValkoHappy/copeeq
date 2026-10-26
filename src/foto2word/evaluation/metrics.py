"""Quality metrics: a predicted Document against a hand-checked expected Document.

All scores are in 0..1 where 1 is perfect, except the CER values (character error rate:
lower is better).
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from foto2word.domain.corrections import CorrectionApplier, accept_all
from foto2word.domain.document import Correction, Document, ExtractedField, TableBlock, plain_text

_SPACES = re.compile(r"\s+")
_TYPOGRAPHY = str.maketrans({"“": '"', "”": '"', "„": '"', "—": "-", "–": "-"})
_FILL_LINE = re.compile(r"_{2,}")
CORRECTION_MATCH_THRESHOLD = 80.0


def normalize(text: str) -> str:
    """Compare text, not typography: NFC, unified quotes/dashes, collapsed whitespace.

    Blanks to fill in ('______') are layout: a model that returns a signature line or a field
    instead of a row of underscores has read the page right.
    """
    text = unicodedata.normalize("NFC", text)
    text = _FILL_LINE.sub(" ", text.translate(_TYPOGRAPHY))
    return _SPACES.sub(" ", text).strip()


def document_text(document: Document) -> str:
    return normalize(" ".join(document.iter_text()))


def cer(predicted: str, expected: str) -> float:
    if not expected:
        return 0.0 if not predicted else 1.0
    return Levenshtein.distance(predicted, expected) / len(expected)


@dataclass(frozen=True, slots=True)
class PrecisionRecall:
    precision: float
    recall: float

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 0.0 if total == 0 else 2 * self.precision * self.recall / total

    @classmethod
    def from_counts(cls, matched: int, predicted: int, expected: int) -> "PrecisionRecall":
        return cls(
            precision=matched / predicted if predicted else (1.0 if not expected else 0.0),
            recall=matched / expected if expected else 1.0,
        )


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    text_cer: float
    """Character error rate of the printed text (before corrections)."""
    final_text_cer: float
    """CER after applying all corrections on both sides: did the edits land correctly?"""
    typo_preservation: float
    """Share of known typos of the original kept verbatim. Below 1 = silent 'fixes'."""
    fields: PrecisionRecall
    corrections: PrecisionRecall
    structure: float
    """Similarity of block kind sequences."""
    tables: float
    type_top1: bool
    type_top3: bool

    def as_row(self) -> dict[str, float]:
        row = {k: v for k, v in asdict(self).items() if isinstance(v, float | bool)}
        row |= {
            "fields_f1": self.fields.f1,
            "corrections_precision": self.corrections.precision,
            "corrections_recall": self.corrections.recall,
        }
        return {k: float(v) for k, v in row.items()}


def evaluate(predicted: Document, expected: Document) -> CaseMetrics:
    return CaseMetrics(
        text_cer=cer(document_text(predicted), document_text(expected)),
        final_text_cer=cer(
            document_text(_corrected(predicted)), document_text(_corrected(expected))
        ),
        typo_preservation=_typo_preservation(predicted, expected),
        fields=_fields(predicted.fields, expected.fields),
        corrections=_corrections(predicted.corrections, expected.corrections),
        structure=_structure(predicted, expected),
        tables=_tables(predicted, expected),
        type_top1=predicted.document_type.id == expected.document_type.id,
        type_top3=expected.document_type.id
        in {predicted.document_type.id, *(t.id for t in predicted.alternative_types[:2])},
    )


def _corrected(document: Document) -> Document:
    return CorrectionApplier().apply(document, accept_all).document


def _typo_preservation(predicted: Document, expected: Document) -> float:
    typos = [normalize(s.text) for s in expected.suggestions]
    if not typos:
        return 1.0
    text = document_text(predicted)
    return sum(typo in text for typo in typos) / len(typos)


def _field_key(field: ExtractedField) -> tuple[str, str]:
    return field.kind.value, normalize(field.value).casefold()


def _fields(
    predicted: Iterable[ExtractedField], expected: Iterable[ExtractedField]
) -> PrecisionRecall:
    p, e = Counter(map(_field_key, predicted)), Counter(map(_field_key, expected))
    return PrecisionRecall.from_counts(sum((p & e).values()), p.total(), e.total())


def _correction_key(correction: Correction) -> str:
    return f"{normalize(correction.before)} -> {normalize(correction.after)}"


def _corrections(
    predicted: tuple[Correction, ...], expected: tuple[Correction, ...]
) -> PrecisionRecall:
    """Greedy one-to-one matching by similarity: the model may choose a different anchor span."""
    remaining = [_correction_key(c) for c in predicted]
    matched = 0
    for key in map(_correction_key, expected):
        scores = [fuzz.token_set_ratio(key, candidate) for candidate in remaining]
        if scores and max(scores) >= CORRECTION_MATCH_THRESHOLD:
            remaining.pop(scores.index(max(scores)))
            matched += 1
    return PrecisionRecall.from_counts(matched, len(predicted), len(expected))


def _structure(predicted: Document, expected: Document) -> float:
    kinds_p = [b.kind for b in predicted.blocks if b.kind != "spacer"]
    kinds_e = [b.kind for b in expected.blocks if b.kind != "spacer"]
    return 1.0 - Levenshtein.normalized_distance(kinds_p, kinds_e)


def _tables(predicted: Document, expected: Document) -> float:
    """Simplified TEDS: grid shape and cell text similarity of tables paired in order."""
    tables_p = [b for b in predicted.blocks if isinstance(b, TableBlock)]
    tables_e = [b for b in expected.blocks if isinstance(b, TableBlock)]
    if not tables_e:
        return 1.0 if not tables_p else 0.0
    scores = [_table_similarity(p, e) for p, e in zip(tables_p, tables_e, strict=False)]
    return sum(scores) / max(len(tables_e), len(tables_p))


def _table_similarity(predicted: TableBlock, expected: TableBlock) -> float:
    cells_p = [normalize(plain_text(c.runs)) for row in predicted.rows for c in row.cells]
    cells_e = [normalize(plain_text(c.runs)) for row in expected.rows for c in row.cells]
    shape = 1.0 - Levenshtein.normalized_distance(
        [len(r.cells) for r in predicted.rows], [len(r.cells) for r in expected.rows]
    )
    text = fuzz.ratio(" | ".join(cells_p), " | ".join(cells_e)) / 100
    return (shape + text) / 2
