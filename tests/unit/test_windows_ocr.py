import io
import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

from foto2word.domain.images import PageImage
from foto2word.domain.ocr import TextLine, TextWord
from foto2word.infrastructure.ocr.windows import WindowsOcrReader


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' own OCR")
def test_windows_ocr_gives_each_line_with_its_box() -> None:
    image = Image.new("RGB", (1200, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("arial.ttf", 48)
    draw.text((100, 100), "Должностная инструкция", fill="black", font=font)
    draw.text((600, 400), "Страница 1 из 4", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    lines = WindowsOcrReader().read_lines([PageImage(buffer.getvalue(), "image/png", "p.png")])

    assert [line.text for line in lines] == ["Должностная инструкция", "Страница 1 из 4"]
    first, second = (line.box for line in lines)
    assert first.x0 == pytest.approx(100 / 1200, abs=0.02)
    assert first.y0 == pytest.approx(110 / 600, abs=0.03)
    assert second.x0 == pytest.approx(600 / 1200, abs=0.02)
    assert all(line.page == 1 for line in lines)


def test_the_same_pages_are_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = WindowsOcrReader()
    calls: list[int] = []

    def recognize(pages: list[PageImage]) -> tuple[list[TextLine], list[TextWord]]:
        calls.append(len(pages))
        return [], []

    monkeypatch.setattr(reader, "_recognize", recognize)
    page = PageImage(b"photo", "image/jpeg", "p.jpg")

    reader.read_lines([page])
    reader.read_text([page])  # the text check after the layout: no second OCR
    reader.read_lines([PageImage(b"other", "image/jpeg", "q.jpg")])

    assert len(calls) == 2
