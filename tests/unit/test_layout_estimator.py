from io import BytesIO

import pytest
from PIL import Image

from foto2word.domain.document import BoundingBox, Document, ParagraphBlock, RequisitesBlock
from foto2word.domain.images import PageImage
from foto2word.infrastructure.layout.projection import ProjectionLayoutEstimator
from foto2word.infrastructure.profiles.yaml_repository import YamlProfileRepository
from foto2word.infrastructure.raster.fonts import FontNotFoundError, FontSet
from foto2word.infrastructure.raster.page import PageRasterizer


@pytest.fixture(scope="module")
def fonts() -> FontSet:
    try:
        return FontSet.discover()
    except FontNotFoundError:
        pytest.skip("No Cyrillic TrueType fonts on this machine")


def test_font_size_and_alignment_are_measured_on_the_photo(
    fonts: FontSet, application: Document, profiles: YamlProfileRepository
) -> None:
    profile = profiles.get("application")
    raster = PageRasterizer(fonts, profile, dpi=150).render(application)
    width, height = raster.image.size
    boxes = {
        block_id: BoundingBox(x0=x0 / width, y0=y0 / height, x1=x1 / width, y1=y1 / height)
        for block_id, (x0, y0, x1, y1) in raster.block_boxes.items()
    }
    # what a model returns: the text and where it is, no sizes or spacing
    read = application.model_copy(
        update={
            "blocks": tuple(
                b.model_copy(update={"bbox": boxes.get(b.id), "layout": None})
                for b in application.blocks
            )
        }
    )
    photo = BytesIO()
    raster.image.save(photo, format="JPEG", quality=90)

    measured = ProjectionLayoutEstimator().estimate(
        read, [PageImage(photo.getvalue(), "image/jpeg", "photo.jpg")]
    )

    body = [b for b in measured.blocks if isinstance(b, ParagraphBlock) and len(b.text()) > 100]
    assert body
    assert {r.size_pt for b in body for r in b.runs} == {profile.styles.body.size_pt}
    assert all(b.align == "justify" for b in body)
    requisites = next(b for b in measured.blocks if isinstance(b, RequisitesBlock))
    assert requisites.layout is not None
    assert requisites.layout.left_indent_mm == pytest.approx(95.0, abs=1.5)  # right column
    assert measured.page is not None


def test_tops_of_tall_letters_stay_with_their_line_but_lines_stay_apart() -> None:
    from PIL import Image, ImageDraw

    from foto2word.infrastructure.layout.projection import _lines

    ink = Image.new("L", (400, 120), 0)
    draw = ImageDraw.Draw(ink)
    draw.rectangle((20, 10, 380, 25), fill=255)  # line 1
    draw.rectangle((40, 29, 60, 31), fill=255)  # tops of 'б' and 'й' above line 2
    draw.rectangle((20, 33, 380, 48), fill=255)  # line 2, one empty row below the tops
    draw.rectangle((20, 51, 380, 66), fill=255)  # line 3, two empty rows below line 2

    lines = _lines(ink)

    assert [(line.top, line.bottom) for line in lines] == [(10, 25), (29, 48), (51, 66)]


def test_word_wrap_counts_lines_and_the_last_line() -> None:
    from foto2word.infrastructure.layout.metrics import TextMetrics

    metrics = TextMetrics()
    if not metrics.available("Times New Roman"):
        pytest.skip("No Times New Roman on this machine")
    word = metrics.width_pt("слово", 12, "Times New Roman")
    space = metrics.width_pt(" ", 12, "Times New Roman")

    wrapped = metrics.wrap("слово слово слово", 12, word * 2 + space + 1, "Times New Roman")

    assert wrapped.lines == 2
    assert wrapped.last_pt == pytest.approx(word)
    assert metrics.wrap("а\nб", 12, 500, "Times New Roman").lines == 2


def test_fit_moves_each_block_by_what_is_left_after_the_moves_above() -> None:
    from foto2word.domain.document import (
        DocumentTypeGuess,
        ParagraphLayout,
        Run,
        SpacerBlock,
    )
    from foto2word.infrastructure.layout.fit import _move

    layout = ParagraphLayout(space_before_pt=0.0)
    document = Document(
        document_type=DocumentTypeGuess(id="other", title="Заявление", confidence=1.0),
        blocks=(
            ParagraphBlock(id="b1", runs=(Run(text="Шапка"),), layout=layout),
            SpacerBlock(id="b2", height_pt=10.0),
            ParagraphBlock(id="b3", runs=(Run(text="Текст"),), layout=layout),
            ParagraphBlock(id="b4", runs=(Run(text="Подпись"),), layout=layout),
        ),
    )
    # b3 is 6 pt too high; b4 is 6.5 pt too high: only half a point is its own error
    moved = _move(document, {"b1": 50, "b3": 100, "b4": 150}, {"b1": 50, "b3": 94, "b4": 143.5})

    spacer, third, fourth = moved.blocks[1], moved.blocks[2], moved.blocks[3]
    assert isinstance(spacer, SpacerBlock)
    assert spacer.height_pt == 16.0
    assert isinstance(third, ParagraphBlock)
    assert third.layout == layout
    assert isinstance(fourth, ParagraphBlock)
    assert fourth.layout == layout  # 0.5 pt is reading noise


def test_a_tab_wide_gap_counts_as_one_space_in_the_text_width() -> None:
    from PIL import Image, ImageDraw

    from foto2word.infrastructure.layout.projection import _text_span

    band = Image.new("L", (600, 20), 0)
    draw = ImageDraw.Draw(band)
    draw.rectangle((0, 0, 99, 19), fill=255)  # 'Город'
    draw.rectangle((104, 0, 199, 19), fill=255)  # a word space of 4 px stays
    draw.rectangle((450, 0, 549, 19), fill=255)  # a tab of 250 px becomes one space

    assert _text_span(band, height=20) == 100 + 4 + 96 + 6 + 100


@pytest.mark.parametrize("family", ["Times New Roman", "Arial"])
def test_the_typeface_is_told_by_where_the_gaps_between_words_fall(family: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    from foto2word.domain.document import Orientation
    from foto2word.domain.ocr import TextLine
    from foto2word.infrastructure.layout import projection
    from foto2word.infrastructure.layout.metrics import _font

    font = _font(family, False)
    if font is None or _font("Times New Roman", False) is None or _font("Arial", False) is None:
        pytest.skip("Times New Roman and Arial are needed")
    sentences = [
        "Прошу предоставить мне ежегодный оплачиваемый отпуск",
        "с первого сентября на четырнадцать календарных дней",
        "в связи с семейными обстоятельствами и переездом",
        "Генеральному директору общества с ограниченной ответственностью",
    ]
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    face = ImageFont.truetype(font.path, 25)
    lines = []
    for index, text in enumerate(sentences):
        top = 200 + index * 60
        draw.text((150, top), text, fill="black", font=face)
        left, upper, right, lower = draw.textbbox((150, top), text, font=face)
        box = BoundingBox(x0=left / 1240, y0=upper / 1754, x1=right / 1240, y1=lower / 1754)
        lines.append(TextLine(page=1, text=text, box=box))
    photo = BytesIO()
    page.save(photo, format="PNG")
    measured = ProjectionLayoutEstimator()._page(
        PageImage(photo.getvalue(), "image/png", "p.png"), Orientation.PORTRAIT, None
    )

    assert projection._typeface_on_photo(lines, [measured]) == family


def test_each_photo_starts_a_new_page() -> None:
    from PIL import Image

    from foto2word.domain.document import DocumentTypeGuess, Run

    blank = BytesIO()
    Image.new("RGB", (620, 877), "white").save(blank, format="JPEG")
    photo = PageImage(blank.getvalue(), "image/jpeg", "photo.jpg")
    read = Document(
        document_type=DocumentTypeGuess(id="letter", title="Письмо", confidence=0.9),
        blocks=tuple(
            ParagraphBlock(id=f"b{n}", page=page, runs=(Run(text=f"Абзац {n}"),))
            for n, page in ((1, 1), (2, 1), (3, 2))
        ),
    )

    measured = ProjectionLayoutEstimator().estimate(read, [photo, photo])

    assert [b.page_break_before for b in measured.blocks] == [False, False, True]


def test_ink_height_counts_the_tails_and_accents_of_capitals() -> None:
    from foto2word.infrastructure.layout import projection
    from foto2word.infrastructure.layout.metrics import TextMetrics

    if not TextMetrics.available("Times New Roman"):
        pytest.skip("Times New Roman is needed")
    text = "БЛАНКОВ ТРУДОВЫХ КНИЖЕК И ВКЛАДЫШЕЙ"  # Д, Щ below the line, Й above the capitals
    ink_px = round(12.0 * TextMetrics.ink_height_em(text, "Times New Roman") / 0.72)  # 0.72 pt/px
    page = projection._Page(
        ink=Image.new("L", (800, 1100)),
        single=1.15,
        lines=[],
        mm_per_px=0.72 / 72 * 25.4,
        width_px=800,
        height_px=1100,
        left_px=80,
        right_px=720,
    )
    line = projection._Line(top=100, bottom=100 + ink_px - 1, left=100, right=600, text=text)

    assert projection._ink_size([line], page, text) == 12.0


def test_a_stamp_over_text_floats_at_its_place_a_logo_above_it_does_not() -> None:
    from PIL import Image, ImageDraw

    from foto2word.domain.document import DocumentTypeGuess, ImageBlock, Run
    from foto2word.domain.ocr import TextLine

    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((150, 100, 350, 200), fill="black")  # logo, alone at the top
    draw.rectangle((150, 400, 900, 420), fill="black")  # a line of text
    draw.rectangle((600, 360, 800, 470), outline="black", width=4)  # stamp over the line
    photo = BytesIO()
    page.save(photo, format="PNG")

    def box(x0: float, y0: float, x1: float, y1: float) -> BoundingBox:
        return BoundingBox(x0=x0 / 1240, y0=y0 / 1754, x1=x1 / 1240, y1=y1 / 1754)

    read = Document(
        document_type=DocumentTypeGuess(id="act", title="Акт", confidence=0.9),
        blocks=(
            ImageBlock(id="logo", description="логотип", bbox=box(150, 100, 350, 200)),
            ParagraphBlock(id="sign", runs=(Run(text="Директор Иванов И. И. подпись"),)),
            ImageBlock(id="stamp", description="печать", bbox=box(600, 360, 800, 470)),
        ),
    )
    lines = [TextLine(page=1, text="Директор Иванов И. И. подпись", box=box(150, 400, 900, 420))]

    measured = ProjectionLayoutEstimator().estimate(
        read, [PageImage(photo.getvalue(), "image/png", "p.png")], lines
    )

    logo, _, stamp = measured.blocks
    assert isinstance(logo, ImageBlock)
    assert isinstance(stamp, ImageBlock)
    assert logo.floating is None
    assert stamp.floating is not None
    assert stamp.floating.horizontal_from == stamp.floating.vertical_from == "page"
    assert stamp.floating.x_mm == pytest.approx(600 / 1240 * 210, abs=1.0)
    assert stamp.floating.y_mm == pytest.approx(360 / 1754 * 297, abs=1.0)
    assert stamp.width_mm == pytest.approx(200 / 1240 * 210, abs=1.0)


def test_a_dark_edge_left_by_flattening_is_not_text() -> None:
    from PIL import Image, ImageDraw

    from foto2word.domain.document import Orientation

    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((0, 0, 1239, 1753), outline=(60, 55, 50), width=3)  # the table at the edges
    draw.rectangle((150, 400, 1090, 420), fill="black")  # a line of text
    photo = BytesIO()
    page.save(photo, format="PNG")

    measured = ProjectionLayoutEstimator()._page(
        PageImage(photo.getvalue(), "image/png", "p.png"), Orientation.PORTRAIT, None
    )

    assert measured.left_px == pytest.approx(150, abs=2)
    assert measured.right_px == pytest.approx(1090, abs=2)
