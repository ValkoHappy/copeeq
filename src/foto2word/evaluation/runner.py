"""Running a vision model (or saved predictions) over eval cases and collecting metrics."""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from foto2word.application.ports import Provenance, UnderstandingContext, Usage, VisionModel
from foto2word.domain.catalog import DEFAULT_CATALOG, DocumentType
from foto2word.domain.document import Document
from foto2word.domain.errors import Foto2WordError
from foto2word.evaluation.cases import EvalCase
from foto2word.evaluation.metrics import CaseMetrics, evaluate
from foto2word.infrastructure.images import PillowImageLoader

PREDICTION_SUFFIX = ".docmodel.json"


@dataclass(frozen=True, slots=True)
class Prediction:
    document: Document
    provenance: Provenance | None = None
    seconds: float = 0.0


class Predictor(Protocol):
    def predict(self, case: EvalCase) -> Prediction: ...


class LivePredictor:
    def __init__(
        self,
        vision: VisionModel,
        loader: PillowImageLoader,
        catalog: tuple[DocumentType, ...] = DEFAULT_CATALOG,
    ) -> None:
        self._vision = vision
        self._loader = loader
        self._catalog = catalog

    def predict(self, case: EvalCase) -> Prediction:
        pages = self._loader.load_all(list(case.photos))
        started = time.perf_counter()
        understanding = self._vision.understand(pages, UnderstandingContext(self._catalog))
        elapsed = time.perf_counter() - started
        return Prediction(understanding.document, understanding.provenance, elapsed)


class SavedPredictor:
    """Re-scores predictions from an earlier run: metric changes cost nothing."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def predict(self, case: EvalCase) -> Prediction:
        path = self._directory / f"{case.id}{PREDICTION_SUFFIX}"
        if not path.is_file():
            raise Foto2WordError(f"No saved prediction for case '{case.id}' in {self._directory}")
        return Prediction(Document.model_validate_json(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class Pricing:
    """USD per one million tokens."""

    input_per_million: float
    output_per_million: float

    def cost(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_per_million
            + usage.output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    metrics: CaseMetrics | None
    error: str | None = None
    seconds: float = 0.0
    usage: Usage = field(default_factory=Usage)
    model: str | None = None


class EvalRunner:
    def __init__(self, predictor: Predictor, predictions_dir: Path | None = None) -> None:
        self._predictor = predictor
        self._predictions_dir = predictions_dir

    def run(self, cases: list[EvalCase]) -> list[CaseResult]:
        return [self._run_case(case) for case in cases]

    def _run_case(self, case: EvalCase) -> CaseResult:
        try:
            prediction = self._predictor.predict(case)
        except Foto2WordError as error:
            return CaseResult(case.id, metrics=None, error=str(error))
        self._save(case, prediction.document)
        provenance = prediction.provenance
        return CaseResult(
            case.id,
            evaluate(prediction.document, case.expected),
            seconds=prediction.seconds,
            usage=provenance.usage if provenance else Usage(),
            model=f"{provenance.provider}/{provenance.model}" if provenance else None,
        )

    def _save(self, case: EvalCase, document: Document) -> None:
        if self._predictions_dir is None:
            return
        self._predictions_dir.mkdir(parents=True, exist_ok=True)
        path = self._predictions_dir / f"{case.id}{PREDICTION_SUFFIX}"
        path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
