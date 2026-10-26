from foto2word.domain.document import BoundingBox, ParagraphBlock, RequisitesBlock, Run
from foto2word.domain.ocr import TextLine, anchor


def _line(text: str, y: float) -> TextLine:
    return TextLine(page=1, text=text, box=BoundingBox(x0=0.1, y0=y, x1=0.9, y1=y + 0.02))


def test_blocks_are_found_by_their_text_not_by_position() -> None:
    lines = [
        _line("Генеральному директору", 0.05),
        _line("ООО «Ромашка»", 0.08),
        _line("Прошу предоставить мне ежегодный оплачиваемый", 0.30),
        _line("отпуск с 01.09.2023 на 14 дней.", 0.33),
        _line("25.08.2023 _______ Егорова Е.Е.", 0.40),
    ]
    head = RequisitesBlock(id="b1", lines=("Генеральному директору", 'ООО "Ромашка"'))
    body = ParagraphBlock(
        id="b2",
        runs=(
            Run(
                text="Прошу предоставить мне ежегодный оплачиваемый отпуск с 01.09.2023 на 14 дней."
            ),
        ),
    )
    sign = ParagraphBlock(id="b3", runs=(Run(text="25.08.2023 Егорова Е.Е."),))
    missing = ParagraphBlock(id="b4", runs=(Run(text="Этого текста на странице нет"),))

    found = anchor([head, body, sign, missing], lines)

    assert found == {"b1": [0, 1], "b2": [2, 3], "b3": [4]}


def test_a_block_out_of_reading_order_is_still_found() -> None:
    lines = [_line("Правая колонка текста", 0.1), _line("Левая колонка текста", 0.1)]
    left = ParagraphBlock(id="b1", runs=(Run(text="Левая колонка текста"),))
    right = ParagraphBlock(id="b2", runs=(Run(text="Правая колонка текста"),))

    assert anchor([left, right], lines) == {"b1": [1], "b2": [0]}
