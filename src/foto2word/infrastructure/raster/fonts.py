"""TrueType fonts with Cyrillic support for drawing pages and handwriting."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from foto2word.domain.errors import Foto2WordError

_SEARCH_DIRS = (
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    Path("/usr/share/fonts"),
    Path("/Library/Fonts"),
)
_CANDIDATES = {
    "regular": ("times.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"),
    "bold": ("timesbd.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"),
    "handwriting": ("segoepr.ttf", "Inkfree.ttf", "comic.ttf", "DejaVuSans-Oblique.ttf"),
}


class FontNotFoundError(Foto2WordError):
    pass


@lru_cache(maxsize=256)
def _load(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


@dataclass(frozen=True, slots=True)
class FontSet:
    regular: Path
    bold: Path
    handwriting: Path

    @classmethod
    def discover(cls, extra_dirs: tuple[Path, ...] = ()) -> "FontSet":
        dirs = (*extra_dirs, *_SEARCH_DIRS)
        return cls(
            regular=cls._find(_CANDIDATES["regular"], dirs),
            bold=cls._find(_CANDIDATES["bold"], dirs),
            handwriting=cls._find(_CANDIDATES["handwriting"], dirs),
        )

    @staticmethod
    def _find(names: tuple[str, ...], dirs: tuple[Path, ...]) -> Path:
        for directory in dirs:
            if not directory.is_dir():
                continue
            for name in names:
                direct = directory / name
                if direct.is_file():
                    return direct
                nested = next(directory.rglob(name), None)
                if nested is not None:
                    return nested
        raise FontNotFoundError(f"None of the fonts {names} found in {[str(d) for d in dirs]}")

    def text(self, size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        return _load(self.bold if bold else self.regular, max(size_px, 1))

    def hand(self, size_px: int) -> ImageFont.FreeTypeFont:
        return _load(self.handwriting, max(size_px, 1))
