import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from foto2word.application.ports import Provenance, Usage
from foto2word.cli.main import app
from foto2word.domain.document import (
    Correction,
    Document,
    DocumentTypeGuess,
    ExtractedField,
    FieldKind,
    HeadingBlock,
    ParagraphBlock,
    Run,
)
from foto2word.domain.errors import Foto2WordError
from foto2word.evaluation.cases import EvalCase, load_cases
from foto2word.evaluation.metrics import cer, evaluate, normalize
from foto2word.evaluation.report import EvalReport
from foto2word.evaluation.runner import (
    EvalRunner,
    Prediction,
    Pricing,
    SavedPredictor,
)
from tests.conftest import CASES


def _replace_block_text(document: Document, index: int, text: str) -> Document:
    blocks = list(document.blocks)
    block = blocks[index]
    assert isinstance(block, HeadingBlock | ParagraphBlock)
    blocks[index] = block.model_copy(update={"runs": (Run(text=text),)})
    return document.model_copy(update={"blocks": tuple(blocks)})


def test_perfect_prediction_scores_perfectly(act: Document) -> None:
    metrics = evaluate(act, act)

    assert metrics.text_cer == metrics.final_text_cer == 0.0
    assert metrics.typo_preservation == 1.0
    assert metrics.fields.f1 == metrics.corrections.f1 == 1.0
    assert metrics.structure == metrics.tables == 1.0
    assert metrics.type_top1
    assert metrics.type_top3


def test_silently_fixed_typo_is_detected(act: Document) -> None:
    fixed = _replace_block_text(act, 10, "Результаты испытаний и осмотра следующие:")

    metrics = evaluate(fixed, act)

    assert metrics.typo_preservation == pytest.approx(3 / 4)
    assert 0 < metrics.text_cer < 0.01


def test_correction_with_different_anchor_still_matches(act: Document) -> None:
    other_anchor = act.model_copy(
        update={
            "corrections": (
                Correction(id="x1", block_id="b2", before="2026гг", after="2027 г"),
                act.corrections[1],
            )
        }
    )

    metrics = evaluate(other_anchor, act)

    assert metrics.corrections.recall == 1.0


def test_missed_correction_and_wrong_field_lower_scores(act: Document) -> None:
    wrong = act.model_copy(
        update={
            "corrections": act.corrections[:1],
            "fields": (
                *act.fields[:-1],
                ExtractedField(kind=FieldKind.NUMBER, value="12", block_id="b12"),
            ),
        }
    )

    metrics = evaluate(wrong, act)

    assert metrics.corrections.recall == 0.5
    assert metrics.corrections.precision == 1.0
    assert metrics.fields.f1 < 1.0
    assert metrics.final_text_cer > 0


def test_document_type_top3_uses_alternatives(act: Document) -> None:
    guess = act.model_copy(
        update={
            "document_type": DocumentTypeGuess(id="protocol", title="x", confidence=0.5),
            "alternative_types": (DocumentTypeGuess(id="act", title="x", confidence=0.4),),
        }
    )

    metrics = evaluate(guess, act)

    assert not metrics.type_top1
    assert metrics.type_top3


def test_text_helpers() -> None:
    assert normalize("  «Тест»  —  да ") == "«Тест» - да"
    assert normalize("25.08.2023 ________ Егорова Е.Е.") == "25.08.2023 Егорова Е.Е."
    assert cer("abc", "abd") == pytest.approx(1 / 3)
    assert cer("", "") == 0.0


class FixedPredictor:
    def __init__(self, documents: dict[str, Document]) -> None:
        self.documents = documents

    def predict(self, case: EvalCase) -> Prediction:
        if case.id not in self.documents:
            raise Foto2WordError("model failed")
        provenance = Provenance("fake", "m1", "v1", Usage(1000, 500))
        return Prediction(self.documents[case.id], provenance, seconds=1.5)


def test_runner_saves_predictions_and_reports_errors(act: Document, tmp_path: Path) -> None:
    cases = load_cases(CASES)
    runner = EvalRunner(FixedPredictor({"act-hydro-001": act}), tmp_path)

    results = runner.run(cases)
    report = EvalReport(tuple(results), Pricing(2.0, 10.0))

    by_id = {r.case_id: r for r in results}
    assert by_id["act-hydro-001"].metrics is not None
    assert by_id["application-001"].error == "model failed"
    assert (tmp_path / "act-hydro-001.docmodel.json").is_file()
    assert report.averages()["text_cer"] == 0.0
    markdown = report.to_markdown()
    assert "error: model failed" in markdown
    assert "Cost: $0.0070 total" in markdown
    assert json.loads(report.to_json())["targets"]["text_cer"] is True


def test_saved_predictor_rescoring(act: Document, tmp_path: Path) -> None:
    (tmp_path / "act-hydro-001.docmodel.json").write_text(act.model_dump_json(), "utf-8")
    case = next(c for c in load_cases(CASES) if c.id == "act-hydro-001")

    assert SavedPredictor(tmp_path).predict(case).document == act
    with pytest.raises(Foto2WordError):
        SavedPredictor(tmp_path / "missing").predict(case)


def test_cli_eval_rescores_saved_predictions(tmp_path: Path) -> None:
    predictions = tmp_path / "pred"
    predictions.mkdir()
    for case in load_cases(CASES):
        path = predictions / f"{case.id}.docmodel.json"
        path.write_text(case.expected.model_dump_json(), "utf-8")

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--cases",
            str(CASES),
            "--predictions",
            str(predictions),
            "--out",
            str(tmp_path / "run"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "run" / "report.md").is_file()
    assert "| text_cer | 0.0000 |" in result.output
