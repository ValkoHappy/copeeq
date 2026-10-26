"""Optional additions to a rendered document chosen by the user."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from foto2word.domain.images import PageImage


class SignatureMode(StrEnum):
    BLANK = "blank"
    """An empty line to sign by hand."""
    PLACEHOLDER = "placeholder"
    """'/подпись/' where the original was signed, as in certified copies."""
    OWN = "own"
    """The user's own signature image on the lines they chose."""


@dataclass(frozen=True, slots=True)
class RenderExtras:
    signature_mode: SignatureMode = SignatureMode.BLANK
    signature_png: bytes | None = None
    signed_blocks: frozenset[str] = frozenset()
    appendix: tuple[PageImage, ...] = ()
    """Photos of the original attached at the end of the document."""
    images: Mapping[str, bytes] = field(default_factory=dict)
    """Pixels of image blocks by block id: cut from the photo or taken from the source file."""
    editable: bool = False
    """Comfortable to fill in: what the original fixes exactly (row heights, line spacing, box
    sizes) only sets a minimum, so text typed in grows the place instead of being cut off."""


NO_EXTRAS = RenderExtras()
