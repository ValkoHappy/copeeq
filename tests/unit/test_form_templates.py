from foto2word.domain.document import (
    Document,
    DocumentTypeGuess,
    ParagraphBlock,
    Run,
    TableBlock,
    TableCell,
    TableRow,
)
from foto2word.domain.templates import FormFill, Replacement, fill, fragments
from foto2word.infrastructure.profiles.yaml_repository import YamlProfileRepository


def _sample() -> Document:
    blue = Run(text="26", color="1F6FBF", size_pt=9)
    table = TableBlock(
        id="b2",
        rows=(
            TableRow(
                cells=(TableCell(runs=(Run(text="Табельный номер"),)), TableCell(runs=(blue,)))
            ),
            TableRow(cells=(TableCell(runs=(Run(text="Петрову Петру Петровичу"),)), TableCell())),
        ),
    )
    return Document(
        document_type=DocumentTypeGuess(id="order", title="Т-6", confidence=1.0),
        blocks=(ParagraphBlock(id="b1", runs=(Run(text="Отпуск на 2026 год"),)), table),
    )


def test_the_sample_is_shown_as_its_distinct_texts() -> None:
    assert fragments(_sample()) == [
        "Отпуск на 2026 год",
        "Табельный номер",
        "26",
        "Петрову Петру Петровичу",
    ]


def test_values_are_replaced_whole_cells_first_and_keep_their_look() -> None:
    form_fill = FormFill(
        replacements=(
            Replacement(before="26", after="41"),
            Replacement(before="Петрову Петру Петровичу", after="Сидоровой Анне Ивановне"),
            Replacement(before="Номер приказа 50", after="Номер приказа 51"),
        )
    )

    filled, missing = fill(_sample(), form_fill)

    paragraph, table = filled.blocks
    assert paragraph.text() == "Отпуск на 2026 год"  # '26' inside '2026' is not the value
    assert isinstance(table, TableBlock)
    number = table.rows[0].cells[1].runs[0]
    assert (number.text, number.color, number.size_pt) == ("41", "1F6FBF", 9)
    assert table.rows[1].cells[0].runs[0].text == "Сидоровой Анне Ивановне"
    assert [r.before for r in missing] == ["Номер приказа 50"]


def test_a_field_left_blank_on_the_photo_is_cleared() -> None:
    filled, _ = fill(_sample(), FormFill(replacements=(Replacement(before="26", after=""),)))

    table = filled.blocks[1]
    assert isinstance(table, TableBlock)
    assert table.rows[0].cells[1].runs == ()


def test_the_library_recognises_a_form_by_its_okud_code() -> None:
    from foto2word.infrastructure.forms import DocxFormLibrary, builtin_forms_dir

    library = DocxFormLibrary(builtin_forms_dir())
    read = Document(
        document_type=DocumentTypeGuess(id="order", title="Приказ", confidence=0.9),
        blocks=(ParagraphBlock(id="b1", runs=(Run(text="Форма по ОКУД 0301005"),)),),
    )
    other = read.model_copy(
        update={"blocks": (ParagraphBlock(id="b1", runs=(Run(text="Заявление на отпуск"),)),)}
    )

    template = library.match(read)

    assert template is not None
    assert template.id == "t6"
    assert "Петрову Петру Петровичу" in fragments(template.document)
    assert library.match(other) is None


def test_a_mark_matches_whole_words_only() -> None:
    from foto2word.infrastructure.forms import DocxFormLibrary, builtin_forms_dir

    library = DocxFormLibrary(builtin_forms_dir())

    def read(text: str) -> Document:
        return Document(
            document_type=DocumentTypeGuess(id="order", title="Приказ", confidence=0.9),
            blocks=(ParagraphBlock(id="b1", runs=(Run(text=text),)),),
        )

    t8 = library.match(read("Унифицированная форма №\nТ- 8"))
    assert t8 is not None
    assert t8.id == "t8"
    assert library.match(read("Унифицированная форма № Т-8а")) is None
    assert library.match(read("Код по ОКУД 03010061")) is None


def test_a_recognised_form_is_the_reference_with_the_photos_values(
    profiles: YamlProfileRepository,
) -> None:
    from collections.abc import Sequence

    from foto2word.application.convert import ConversionOptions, ConvertDocument
    from foto2word.application.ports import Provenance, Understanding, UnderstandingContext
    from foto2word.domain.images import PageImage
    from foto2word.infrastructure.forms import DocxFormLibrary, builtin_forms_dir
    from foto2word.infrastructure.rendering.docx_renderer import DocxRenderer

    read = Document(
        document_type=DocumentTypeGuess(id="order", title="Приказ", confidence=0.9),
        blocks=(ParagraphBlock(id="b1", runs=(Run(text="Унифицированная форма № Т-6"),)),),
    )

    class Model:
        def understand(
            self, pages: Sequence[PageImage], context: UnderstandingContext
        ) -> Understanding:
            return Understanding(read, Provenance("fake", "m", "understand.v1"))

        def fill_form(self, pages: Sequence[PageImage], sample: list[str]) -> FormFill:
            return FormFill(
                replacements=(
                    Replacement(before="Петрову Петру Петровичу", after="Сидоровой Анне"),
                )
            )

    model = Model()
    converter = ConvertDocument(
        model,
        DocxRenderer(),
        profiles,
        forms=DocxFormLibrary(builtin_forms_dir()),
        filler=model,
    )

    analysis = converter.analyze(
        [PageImage(b"jpeg", "image/jpeg", "photo.jpg")], ConversionOptions()
    )

    assert analysis.form == "t6"
    texts = fragments(analysis.document)
    assert "Сидоровой Анне" in texts
    assert "Петрову Петру Петровичу" not in texts
    assert analysis.document.document_type.title == "Приказ"


def test_a_value_inside_a_nested_table_is_replaced() -> None:
    from foto2word.domain.document import NestedTable, TableCell, TableRow

    inner = TableBlock(id="t2", rows=(TableRow(cells=(TableCell(runs=(Run(text="Петров"),)),)),))
    outer = TableBlock(
        id="t1",
        rows=(TableRow(cells=(TableCell(tables=(NestedTable(after_line=0, table=inner),)),)),),
    )
    document = Document(
        document_type=DocumentTypeGuess(id="form", title="Бланк", confidence=0.9), blocks=(outer,)
    )

    filled, missing = fill(
        document, FormFill(replacements=(Replacement(before="Петров", after="Сидоров"),))
    )

    assert missing == ()
    assert "Сидоров" in " ".join(filled.iter_text())
