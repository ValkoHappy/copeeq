"""Eval report: per-case rows, averages and pass/fail against the v1 targets."""

import json
from dataclasses import dataclass
from statistics import fmean

from foto2word.application.ports import Usage
from foto2word.evaluation.runner import CaseResult, Pricing


@dataclass(frozen=True, slots=True)
class Target:
    metric: str
    threshold: float
    higher_is_better: bool = True

    def passed(self, value: float) -> bool:
        return value >= self.threshold if self.higher_is_better else value <= self.threshold


# Targets from docs/ARCHITECTURE.md §8.1.
V1_TARGETS: tuple[Target, ...] = (
    Target("text_cer", 0.01, higher_is_better=False),
    Target("typo_preservation", 0.98),
    Target("fields_f1", 0.995),
    Target("corrections_recall", 0.90),
    Target("corrections_precision", 0.95),
    Target("tables", 0.90),
    Target("type_top1", 0.85),
    Target("type_top3", 0.97),
)


@dataclass(frozen=True, slots=True)
class EvalReport:
    results: tuple[CaseResult, ...]
    pricing: Pricing | None = None

    @property
    def scored(self) -> list[CaseResult]:
        return [r for r in self.results if r.metrics is not None]

    def averages(self) -> dict[str, float]:
        rows = [r.metrics.as_row() for r in self.scored if r.metrics]
        if not rows:
            return {}
        return {key: fmean(row[key] for row in rows) for key in rows[0]}

    def total_usage(self) -> Usage:
        total = Usage()
        for result in self.results:
            total += result.usage
        return total

    def to_json(self) -> str:
        payload = {
            "averages": self.averages(),
            "targets": {
                t.metric: t.passed(v)
                for t in V1_TARGETS
                if (v := self.averages().get(t.metric)) is not None
            },
            "cases": [
                {
                    "case": r.case_id,
                    "model": r.model,
                    "seconds": r.seconds,
                    "input_tokens": r.usage.input_tokens,
                    "output_tokens": r.usage.output_tokens,
                    "error": r.error,
                    "metrics": r.metrics.as_row() if r.metrics else None,
                }
                for r in self.results
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        averages = self.averages()
        lines = ["# Eval report", "", f"Cases: {len(self.results)}, scored: {len(self.scored)}", ""]
        lines += ["| Metric | Average | Target | OK |", "|---|---|---|---|"]
        for target in V1_TARGETS:
            value = averages.get(target.metric)
            if value is None:
                continue
            sign = ">=" if target.higher_is_better else "<="
            mark = "yes" if target.passed(value) else "**no**"
            lines.append(f"| {target.metric} | {value:.4f} | {sign} {target.threshold} | {mark} |")

        lines += ["", "| Case | CER | Final CER | Typos kept | Fields F1 | Corr. R/P | Type | s |"]
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in self.results:
            if r.metrics is None:
                lines.append(f"| {r.case_id} | error: {r.error} |||||||")
                continue
            m = r.metrics
            lines.append(
                f"| {r.case_id} | {m.text_cer:.4f} | {m.final_text_cer:.4f} | "
                f"{m.typo_preservation:.2f} | {m.fields.f1:.2f} | "
                f"{m.corrections.recall:.2f}/{m.corrections.precision:.2f} | "
                f"{'ok' if m.type_top1 else 'miss'} | {r.seconds:.1f} |"
            )

        usage = self.total_usage()
        lines += ["", f"Tokens: in {usage.input_tokens}, out {usage.output_tokens}"]
        if self.pricing and self.results:
            cost = self.pricing.cost(usage)
            lines.append(f"Cost: ${cost:.4f} total, ${cost / len(self.results):.4f} per case")
        return "\n".join(lines) + "\n"
