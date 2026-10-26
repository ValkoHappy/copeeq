"""Unified forms from a library: the perfect Word file of the form, filled with the photo's values.

Forms like Т-6 or М-2а are a finite set of official blanks. For them the best result is not a
reconstruction but the original layout itself: recognise the form, take its reference file,
and change the values. The reference files are filled samples, so filling is a list of text
replacements — "as in the sample" -> "as on the photo" — and the layout is never touched.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from foto2word.domain.document import Block, Document, Run, TableBlock, plain_text

_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FormTemplate:
    """A reference Word file of a form, already turned into the document model."""

    id: str
    title: str
    document: Document
    images: Mapping[str, bytes] = field(default_factory=dict)
    """Pixels of the reference's pictures by block id."""


class Replacement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    before: str = Field(description="A value exactly as written in the sample (one of its lines).")
    after: str = Field(
        description="The value as written on the photo; empty if the field is blank."
    )


class FormFill(BaseModel):
    """What differs between the sample and the photographed form."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    replacements: tuple[Replacement, ...] = ()


def fragments(document: Document) -> list[str]:
    """The sample's texts as a model should see them: every paragraph and every table cell once,
    in reading order."""
    seen: dict[str, None] = {}
    for block in document.blocks:
        texts = (
            [plain_text(cell.runs) for row in block.rows for cell in row.cells]
            if isinstance(block, TableBlock)
            else [block.text()]
        )
        for text in texts:
            clean = _SPACES.sub(" ", text).strip()
            if clean:
                seen.setdefault(clean, None)
    return list(seen)


def fill(document: Document, form_fill: FormFill) -> tuple[Document, tuple[Replacement, ...]]:
    """The sample with each value replaced; also the replacements not found in it (to report,
    never to guess).

    A whole cell or paragraph equal to the value is replaced first, so a short value like '26'
    does not change '2026' elsewhere; only when there is none is the value replaced inside text.
    """
    blocks = list(document.blocks)
    missing: list[Replacement] = []
    for replacement in form_fill.replacements:
        if not replacement.before or replacement.before == replacement.after:
            continue
        exact = [_replace_whole(block, replacement) for block in blocks]
        if any(changed is not None for changed in exact):
            blocks = [changed or block for changed, block in zip(exact, blocks, strict=True)]
            continue
        inside = [_replace_inside(block, replacement) for block in blocks]
        if any(changed is not None for changed in inside):
            blocks = [changed or block for changed, block in zip(inside, blocks, strict=True)]
        else:
            missing.append(replacement)
    return document.model_copy(update={"blocks": tuple(blocks)}), tuple(missing)


def _replace_whole(block: Block, replacement: Replacement) -> Block | None:
    """The block, or the table cells, whose whole text is the value."""
    if isinstance(block, TableBlock):
        rows = []
        changed = False
        for row in block.rows:
            cells = []
            for cell in row.cells:
                if _same(plain_text(cell.runs), replacement.before):
                    cells.append(
                        cell.model_copy(update={"runs": _retyped(cell.runs, replacement.after)})
                    )
                    changed = True
                else:
                    cells.append(cell)
            rows.append(row.model_copy(update={"cells": tuple(cells)}))
        return block.model_copy(update={"rows": tuple(rows)}) if changed else None
    if _same(block.text(), replacement.before):
        return block.replace_text(block.text().strip(), replacement.after)
    return None


def _replace_inside(block: Block, replacement: Replacement) -> Block | None:
    changed: Block | None = None
    current = block
    for _ in range(_MAX_OCCURRENCES):
        step = current.replace_text(replacement.before, replacement.after)
        if step is None:
            break
        current = changed = step
    return changed


def _same(text: str, value: str) -> bool:
    return _SPACES.sub(" ", text).strip() == _SPACES.sub(" ", value).strip()


def _retyped(runs: tuple[Run, ...], text: str) -> tuple[Run, ...]:
    """New text in the look of the first run (a filled-in value keeps its colour and size)."""
    look = next((run for run in runs if run.text.strip()), runs[0] if runs else Run(text=""))
    return (look.model_copy(update={"text": text}),) if text else ()


_MAX_OCCURRENCES = 20
"""Guard against a replacement whose result contains its own source text."""
