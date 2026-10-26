from foto2word.infrastructure.layout.pdf_lines import _joined, _rows


def test_blanks_below_the_letters_stay_on_their_line() -> None:
    # 'ИНН ________, КПП ____': the underscores lie under the baseline, below the letter boxes
    pieces = [
        (100.0, 100.0, 130.0, 110.0, "ИНН "),
        (130.0, 111.0, 200.0, 112.5, "________"),
        (200.0, 106.5, 203.0, 112.3, ", "),  # lower than the letters, as in a real PDF
        (210.0, 100.0, 240.0, 110.0, "КПП "),
        (240.0, 111.0, 300.0, 112.5, "____"),
        (100.0, 130.0, 160.0, 140.0, "адрес: "),
    ]

    rows = _rows(pieces)

    assert [_joined(row) for row in rows] == ["ИНН ________, КПП ____", "адрес:"]


def test_a_far_piece_on_the_same_row_is_another_line() -> None:
    pieces = [(100.0, 100.0, 160.0, 110.0, "Директор"), (400.0, 100.0, 460.0, 110.0, "Иванов")]

    assert [_joined(row) for row in _rows(pieces)] == ["Директор", "Иванов"]
