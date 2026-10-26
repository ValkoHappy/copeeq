"""Applying handwritten corrections to a document."""

from collections.abc import Callable
from dataclasses import dataclass

from foto2word.domain.document import Correction, CorrectionStatus, Document

CorrectionDecision = Callable[[Correction], bool]
"""Returns True to accept a proposed correction."""


def accept_all(_: Correction) -> bool:
    return True


def reject_all(_: Correction) -> bool:
    return False


@dataclass(frozen=True, slots=True)
class CorrectionOutcome:
    document: Document
    applied: tuple[Correction, ...]
    rejected: tuple[Correction, ...]
    failed: tuple[Correction, ...]
    """Accepted, but `before` was not found in the target block."""


class CorrectionApplier:
    """Applies accepted corrections to block text and records every decision."""

    def apply(self, document: Document, decide: CorrectionDecision) -> CorrectionOutcome:
        blocks = list(document.blocks)
        resolved: list[Correction] = []
        applied: list[Correction] = []
        rejected: list[Correction] = []
        failed: list[Correction] = []

        for correction in document.corrections:
            if correction.status is not CorrectionStatus.PROPOSED:
                resolved.append(correction)
                continue
            if not decide(correction):
                rejected.append(self._with_status(correction, CorrectionStatus.REJECTED))
                resolved.append(rejected[-1])
                continue

            index = document.block_index(correction.block_id)
            new_block = (
                None
                if index is None
                else blocks[index].replace_text(correction.before, correction.after)
            )
            if index is None or new_block is None:
                failed.append(correction)
                resolved.append(correction)
                continue

            blocks[index] = new_block
            applied.append(self._with_status(correction, CorrectionStatus.ACCEPTED))
            resolved.append(applied[-1])

        new_document = document.model_copy(
            update={"blocks": tuple(blocks), "corrections": tuple(resolved)}
        )
        return CorrectionOutcome(new_document, tuple(applied), tuple(rejected), tuple(failed))

    @staticmethod
    def _with_status(correction: Correction, status: CorrectionStatus) -> Correction:
        return correction.model_copy(update={"status": status})
