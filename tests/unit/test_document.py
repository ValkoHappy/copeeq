from pydantic import TypeAdapter

from foto2word.domain.document import (
    Document,
    HeadingBlock,
    LabeledLineBlock,
    RequisitesBlock,
    Run,
    SpacerBlock,
    TableBlock,
    TableCell,
    TableRow,
)


def test_eval_cases_round_trip(act: Document, application: Document) -> None:
    for document in (act, application):
        assert Document.model_validate_json(document.model_dump_json()) == document


def test_replace_text_in_runs_keeps_formatting_of_other_runs() -> None:
    block = HeadingBlock(id="b1", runs=(Run(text="до 10 кг/см"), Run(text="2", superscript=True)))

    replaced = block.replace_text("10", "12")

    assert replaced is not None
    assert replaced.runs[0].text == "до 12 кг/см"
    assert replaced.runs[1] == block.runs[1]


def test_replace_text_returns_none_when_fragment_is_missing() -> None:
    assert HeadingBlock(id="b1", runs=(Run(text="АКТ"),)).replace_text("2026", "2027") is None
    assert SpacerBlock(id="b2").replace_text("", "x") is None


def test_replace_text_in_structured_blocks() -> None:
    labeled = LabeledLineBlock(id="b1", label="Председатель:", value="Сидоров С.С.")
    requisites = RequisitesBlock(id="b2", lines=("Директору", "тел: 123"))
    table = TableBlock(
        id="b3",
        rows=(
            TableRow(cells=(TableCell(runs=(Run(text="a"),)), TableCell(runs=(Run(text="2026"),)))),
        ),
    )

    assert labeled.replace_text("Сидоров", "Петров") == labeled.model_copy(
        update={"value": "Петров С.С."}
    )
    replaced_requisites = requisites.replace_text("123", "456")
    assert replaced_requisites is not None
    assert replaced_requisites.lines == ("Директору", "тел: 456")
    replaced_table = table.replace_text("2026", "2027")
    assert replaced_table is not None
    assert replaced_table.text() == "a\t2027"


def test_block_kind_is_required_in_the_json_schema() -> None:
    schema = TypeAdapter(Document).json_schema()

    heading = schema["$defs"]["HeadingBlock"]

    assert "kind" in heading["required"]
    assert heading["properties"]["kind"]["enum"] == ["heading"]
