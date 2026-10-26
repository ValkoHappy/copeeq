"""Targeted edits proposed by the review stage. Patches, not a rewrite of the whole document."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from foto2word.domain.document import Block, Correction, Document


class PatchOp(StrEnum):
    REPLACE = "replace"
    INSERT_AFTER = "insert_after"
    DELETE = "delete"


class BlockPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    op: PatchOp
    target_id: str = Field(
        description="Existing block id. For insert_after use '' to insert at the very beginning."
    )
    block: Block | None = Field(
        default=None, description="New block for replace/insert_after; null for delete."
    )
    reason: str = Field(description="What differs from the photo, in one short sentence.")


class ReviewResult(BaseModel):
    """What the reviewer found when comparing the photo with the rendered document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    patches: tuple[BlockPatch, ...] = ()
    missing_corrections: tuple[Correction, ...] = Field(
        default=(), description="Handwritten edits visible on the photo but absent in the model."
    )


@dataclass(frozen=True, slots=True)
class PatchOutcome:
    document: Document
    applied: tuple[BlockPatch, ...]
    skipped: tuple[BlockPatch, ...]


class DocumentPatcher:
    def apply(self, document: Document, review: ReviewResult) -> PatchOutcome:
        blocks = list(document.blocks)
        applied: list[BlockPatch] = []
        skipped: list[BlockPatch] = []
        for patch in review.patches:
            if self._apply_one(blocks, patch):
                applied.append(patch)
            else:
                skipped.append(patch)

        known = {c.id for c in document.corrections}
        new_corrections = tuple(c for c in review.missing_corrections if c.id not in known)
        updated = document.model_copy(
            update={
                "blocks": tuple(blocks),
                "corrections": (*document.corrections, *new_corrections),
            }
        )
        return PatchOutcome(updated, tuple(applied), tuple(skipped))

    def _apply_one(self, blocks: list[Block], patch: BlockPatch) -> bool:
        handlers = {
            PatchOp.INSERT_AFTER: self._insert_after,
            PatchOp.REPLACE: self._replace,
            PatchOp.DELETE: self._delete,
        }
        return handlers[patch.op](blocks, patch)

    @staticmethod
    def _insert_after(blocks: list[Block], patch: BlockPatch) -> bool:
        ids = [b.id for b in blocks]
        if patch.block is None or patch.block.id in ids:
            return False
        if patch.target_id == "":
            blocks.insert(0, patch.block)
            return True
        if patch.target_id not in ids:
            return False
        blocks.insert(ids.index(patch.target_id) + 1, patch.block)
        return True

    @staticmethod
    def _replace(blocks: list[Block], patch: BlockPatch) -> bool:
        ids = [b.id for b in blocks]
        if patch.block is None or patch.target_id not in ids:
            return False
        blocks[ids.index(patch.target_id)] = patch.block.model_copy(update={"id": patch.target_id})
        return True

    @staticmethod
    def _delete(blocks: list[Block], patch: BlockPatch) -> bool:
        ids = [b.id for b in blocks]
        if patch.target_id not in ids:
            return False
        del blocks[ids.index(patch.target_id)]
        return True
