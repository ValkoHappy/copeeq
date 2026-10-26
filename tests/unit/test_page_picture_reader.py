"""A page picture read into the content a PDF gives: face, size and weight of words drawn in a
known face, and the lines drawn on the page."""

import pytest
from PIL import Image, ImageDraw, ImageFont

from foto2word.domain.document import BoundingBox
from foto2word.domain.ocr import TextWord
from foto2word.infrastructure.layout.metrics import TextMetrics
from foto2word.infrastructure.pdf.from_image import page_content

DPI = 200
WIDTH_PT, HEIGHT_PT = 595.0, 842.0
PX = DPI / 72

_TIMES = "Times New Roman"
needs_times = pytest.mark.skipif(
    not (TextMetrics.available(_TIMES) and TextMetrics.available(_TIMES, True)),
    reason="no Times New Roman on this machine",
)


def _page(
    lines: list[list[tuple[str, bool]]], size_pt: float, *, rule: bool = False
) -> tuple[Image.Image, list[TextWord]]:
    """Lines of words drawn in Times at this size, with their ink boxes as an OCR gives."""
    page = Image.new("RGB", (round(WIDTH_PT * PX), round(HEIGHT_PT * PX)), "white")
    draw = ImageDraw.Draw(page)
    found = []
    for number, words in enumerate(lines):
        found += _draw_line(draw, words, size_pt, number, page.size)
    if rule:
        draw.rectangle((100 * PX, 300 * PX, 400 * PX, 300 * PX + 1), fill="black")
    return page, found


def _draw_line(
    draw: ImageDraw.ImageDraw,
    words: list[tuple[str, bool]],
    size_pt: float,
    number: int,
    size: tuple[int, int],
) -> list[TextWord]:
    found = []
    x, y = 100 * PX, (150 + number * 20) * PX
    for text, bold in words:
        name = "timesbd.ttf" if bold else "times.ttf"
        font = ImageFont.truetype(name, round(size_pt * PX))
        draw.text((x, y), text, font=font, fill="black", anchor="ls")
        left, top, right, bottom = draw.textbbox((x, y), text, font=font, anchor="ls")
        found.append(
            TextWord(
                page=1,
                line=number,
                text=text,
                box=BoundingBox(
                    x0=left / size[0], y0=top / size[1], x1=right / size[0], y1=bottom / size[1]
                ),
            )
        )
        x = right + font.getlength(" ")
    return found


@needs_times
def test_the_face_size_and_weight_of_words_come_from_their_widths_and_their_ink() -> None:
    picture, words = _page(
        [
            [("Заявление", True), ("работника", True)],
            [("Прошу", False), ("предоставить", False), ("мне", False), ("ежегодный", False)],
            [("оплачиваемый", False), ("отпуск", False), ("продолжительностью", False)],
        ],
        14,
    )

    content = page_content(picture, words, WIDTH_PT, HEIGHT_PT, boxes=(1.0, 1.0))

    letters = [c for c in content.chars if c.text.strip()]
    assert {c.font for c in letters} == {"Times New Roman"}
    assert all(abs(c.size - 14) <= 0.5 for c in letters)
    title = [c for c in letters if c.base < 155 * 1.0 + 1]  # the first line
    assert title
    assert all(c.bold for c in title)
    assert not any(c.bold for c in letters if c not in title)


@needs_times
def test_a_long_thin_run_of_ink_is_a_drawn_line() -> None:
    picture, words = _page([[("Подпись", False)]], 12, rule=True)

    content = page_content(picture, words, WIDTH_PT, HEIGHT_PT, boxes=(1.0, 1.0))

    (line,) = content.rules
    assert line.horizontal
    assert abs(line.x0 - 100) < 1
    assert abs(line.x1 - 400) < 1
    assert abs(line.y0 - 300) < 1
