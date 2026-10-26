from foto2word.domain.corrections import CorrectionApplier, accept_all, reject_all
from foto2word.domain.document import (
    Correction,
    CorrectionStatus,
    Document,
    DocumentTypeGuess,
    ParagraphBlock,
    Run,
)


def _doc(*corrections: Correction) -> Document:
    return Document(
        document_type=DocumentTypeGuess(id="other", title="x", confidence=1.0),
        blocks=(ParagraphBlock(id="b1", runs=(Run(text="на 2026 год"),)),),
        corrections=corrections,
    )


def test_accepts_all_corrections_of_the_act(act: Document) -> None:
    outcome = CorrectionApplier().apply(act, accept_all)

    texts = list(outcome.document.iter_text())
    assert [c.id for c in outcome.applied] == ["c1", "c2"]
    assert "отопительном периоде 2027 г." in texts[1]
    assert texts[2] == "г.Тестовый\t«19» октября 2027 г."
    assert all(c.status is CorrectionStatus.ACCEPTED for c in outcome.document.corrections)


def test_rejected_corrections_leave_text_untouched(act: Document) -> None:
    outcome = CorrectionApplier().apply(act, reject_all)

    assert outcome.document.blocks == act.blocks
    assert len(outcome.rejected) == 2
    assert all(c.status is CorrectionStatus.REJECTED for c in outcome.document.corrections)


def test_correction_with_missing_fragment_is_reported_as_failed() -> None:
    missing = Correction(id="c1", block_id="b1", before="2025", after="2027")
    unknown_block = Correction(id="c2", block_id="b9", before="2026", after="2027")

    outcome = CorrectionApplier().apply(_doc(missing, unknown_block), accept_all)

    assert outcome.failed == (missing, unknown_block)
    assert outcome.document.blocks == _doc().blocks


def test_already_resolved_corrections_are_kept_as_is() -> None:
    done = Correction(
        id="c1", block_id="b1", before="2026", after="2027", status=CorrectionStatus.REJECTED
    )

    outcome = CorrectionApplier().apply(_doc(done), accept_all)

    assert outcome.applied == ()
    assert outcome.document.corrections == (done,)
