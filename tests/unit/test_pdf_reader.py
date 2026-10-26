"""The rules that turn a PDF's characters and lines into paragraphs and tables, on made-up
characters: no PDF file and no Word needed."""

from foto2word.domain.document import Alignment
from foto2word.infrastructure.pdf import reader
from foto2word.infrastructure.pdf.tables import Rule, find_grids

SIZE = 12.0
ADVANCE = 6.0  # every letter as wide as this
SPACE = 3.0  # a space a quarter of the size, as in Times


def _line(text: str, x: float, base: float, space: float = SPACE) -> reader._Line:
    chars = []
    for ch in text:
        width = space if ch == " " else ADVANCE
        chars.append(
            reader._Char(
                text=ch,
                x0=x,
                x1=x + width,
                top=base - 9,
                bottom=base + 3,
                base=base,
                size=SIZE,
                font="Times New Roman",
                bold=False,
                italic=False,
                color=None,
            )
        )
        x += width
    return reader._Line(chars, 1)


def test_a_line_continues_its_paragraph_only_when_the_next_word_did_not_fit() -> None:
    full = _line("слово " * 6 + "слово", 100, 100)
    right = full.x1 + 10  # no room for another word
    wrapped = _line("продолжение строки", 100, 114)  # short: its paragraph ends here
    after = _line("новый абзац", 100, 128)

    paragraphs = reader._paragraphs([full, wrapped, after], 100, right)

    assert [len(p.lines) for p in paragraphs] == [2, 1]


def test_right_aligned_lines_each_end_their_paragraph_when_the_left_had_room() -> None:
    right = 500.0
    lines = [
        _line("Исполняющему обязанности", right - (23 * ADVANCE + SPACE), 100),
        _line("генерального директора", right - (21 * ADVANCE + SPACE), 114),
    ]
    assert lines[0].x1 == lines[1].x1 == right
    assert [len(p.lines) for p in reader._paragraphs(lines, 100, right)] == [1, 1]


def test_justified_lines_reach_the_right_edge_and_a_one_word_line_does_not_spoil_it() -> None:
    first = _line("аааа бббб вввв", 100, 100, space=10.0)  # spaces stretched to the edge
    lines = [
        first,
        _line("«Цветущий", 100, 114),  # one word, short: the next one is too long
        _line("город»,____________", 100, 128),
    ]
    assert reader._alignment(lines, 100, first.x1) is Alignment.JUSTIFY
    plain = [_line("аааа бббб вввв", 100, 100), _line("гггг", 100, 114)]
    assert reader._alignment(plain, 100, plain[0].x1) is Alignment.LEFT  # just the longest


def test_centred_lines_are_centred() -> None:
    right = 100 + 40 * ADVANCE
    title = _line("ЗАЯВЛЕНИЕ", 100 + (40 - 9) * ADVANCE / 2, 100)
    assert reader._alignment([title], 100, right) is Alignment.CENTER


def test_a_wide_gap_is_a_tab_but_not_a_stretched_space_of_a_justified_line() -> None:
    right = 400.0
    tabbed = _line("Исх. №", 100, 100)
    date = _line("от 01.01", 300, 100)
    line = reader._Line(tabbed.chars + date.chars, 1)
    assert reader._tabbed(line, right)

    stretched = _line("и ", 100, 120)
    end = _line("следующие", right - 9 * ADVANCE, 120)  # the line reaches the edge
    justified = reader._Line(stretched.chars + end.chars, 1)
    assert not reader._tabbed(justified, right)


def test_crossing_lines_make_a_table_and_a_missing_line_merges_cells() -> None:
    across = [Rule(0, y, 200, y, 0.5, None) for y in (0, 20, 40)]
    down = [Rule(x, 0, x, 40, 0.5, None) for x in (0, 200)]
    down += [Rule(100, 20, 100, 40, 0.5, None)]  # the middle line only in the second row

    (grid,) = find_grids(across + down)

    assert grid.xs == [0, 100, 200]
    assert grid.ys == [0, 20, 40]
    spans = sorted((c.row, c.col, c.col_span) for c in grid.cells)
    assert spans == [(0, 0, 2), (1, 0, 1), (1, 1, 1)]


def test_lines_that_do_not_cross_are_not_a_table() -> None:
    fill_lines = [Rule(0, y, 200, y, 0.5, None) for y in (0, 20, 40)]
    assert find_grids(fill_lines) == []


def test_the_text_area_ends_at_justified_lines_else_within_what_the_wrapping_allows() -> None:
    first = _line("аааа бббб вввв", 100, 100, space=10.0)
    justified = {1: [first, _line("вввввв", 100, 114)]}
    assert reader._right_edge(justified, 100, first.x1) == first.x1

    ragged = {1: [_line("короткая строка", 100, 100), _line("ещё одна", 100, 114)]}
    widest = ragged[1][0].x1
    edge = reader._right_edge(ragged, 100, widest)
    assert widest < edge <= widest + reader._SLACK
