"""Windows' own OCR (Windows.Media.Ocr): offline, free, no keys. Gives every text line with its
box, which is what the layout measurement needs; the vision model reads the text itself.

Runs windows_ocr.ps1 in one PowerShell for all the pages of a document.
"""

import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from foto2word.domain.document import BoundingBox
from foto2word.domain.errors import Foto2WordError
from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine, TextWord

SCRIPT = Path(__file__).with_name("windows_ocr.ps1")
_SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg"}


class WindowsOcrError(Foto2WordError):
    pass


def windows_ocr_available() -> bool:
    return sys.platform == "win32"


class WindowsOcrReader:
    def __init__(self, language: str = "ru", timeout_s: float = 120) -> None:
        self._language = language
        self._timeout_s = timeout_s
        self._last: tuple[tuple[bytes, ...], list[TextLine], list[TextWord]] | None = None
        """The pages read last and their lines: the layout and the text check read the same."""

    def read_text(self, pages: Sequence[PageImage]) -> str:
        return "\n".join(line.text for line in self.read_lines(pages))

    def read_lines(self, pages: Sequence[PageImage]) -> list[TextLine]:
        """Every text line with its box, normalised to the page size."""
        return list(self._read(pages)[0])

    def read_words(self, pages: Sequence[PageImage]) -> list[TextWord]:
        """Every word with its box, normalised to the page size, and the index of its line."""
        return list(self._read(pages)[1])

    def _read(self, pages: Sequence[PageImage]) -> tuple[list[TextLine], list[TextWord]]:
        key = tuple(page.data for page in pages)
        if self._last is None or self._last[0] != key:
            self._last = (key, *self._recognize(pages))
        return self._last[1], self._last[2]

    def _recognize(self, pages: Sequence[PageImage]) -> tuple[list[TextLine], list[TextWord]]:
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for number, page in enumerate(pages):
                path = Path(folder) / f"page-{number}{_SUFFIX.get(page.media_type, '.jpg')}"
                path.write_bytes(page.data)
                paths.append(str(path))
            try:
                done = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(SCRIPT),
                        "-Language",
                        self._language,
                    ],
                    input="\n".join(paths).encode("utf-8"),
                    capture_output=True,
                    timeout=self._timeout_s,
                    check=True,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise WindowsOcrError(f"Windows OCR failed: {error}") from error
        found: list[TextLine] = []
        words: list[TextWord] = []
        try:
            for row in done.stdout.decode("utf-8-sig").splitlines():
                if not row.strip():
                    continue
                item = json.loads(row)
                width, height = float(item["width"]), float(item["height"])
                box = BoundingBox(
                    x0=item["x0"] / width, y0=item["y0"] / height,
                    x1=item["x1"] / width, y1=item["y1"] / height,
                )  # fmt: skip
                found.append(TextLine(page=int(item["file"]) + 1, text=item["text"], box=box))
                for text, x, y, w, h in item.get("words") or ():
                    words.append(
                        TextWord(
                            page=int(item["file"]) + 1,
                            line=len(found) - 1,
                            text=str(text),
                            box=BoundingBox(
                                x0=x / width,
                                y0=y / height,
                                x1=(x + w) / width,
                                y1=(y + h) / height,
                            ),
                        )
                    )
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            raise WindowsOcrError(f"Unexpected Windows OCR answer: {error}") from error
        return found, words
