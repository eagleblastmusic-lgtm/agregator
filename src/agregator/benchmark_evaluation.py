from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .label_status import LabelBundleStatus, build_label_bundle_status
from .quality_gate import QualityGateResult, evaluate_quality_gate
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class BenchmarkEvaluationResult:
    label_status: LabelBundleStatus
    quality_gate: QualityGateResult | None
    evaluated: bool
    passed: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_status": self.label_status.to_dict(),
            "quality_gate": self.quality_gate.to_dict() if self.quality_gate else None,
            "evaluated": self.evaluated,
            "passed": self.passed,
            "blockers": list(self.blockers),
        }


def evaluate_labeled_benchmark(
    store: SQLiteStore,
    label_dir: str | Path,
    *,
    min_resolution_f1: float = 0.95,
    min_website_f1: float = 0.95,
    min_contact_macro_f1: float = 0.90,
) -> BenchmarkEvaluationResult:
    """Evaluate a benchmark only after all generated ground-truth rows are labeled."""

    directory = Path(label_dir)
    label_status = build_label_bundle_status(directory)
    if not label_status.ready_for_quality_gate:
        return BenchmarkEvaluationResult(
            label_status=label_status,
            quality_gate=None,
            evaluated=False,
            passed=False,
            blockers=label_status.blockers,
        )

    gate = evaluate_quality_gate(
        store,
        resolution_truth=directory / "company_resolution_truth.csv",
        website_truth=directory / "website_resolution_truth.csv",
        contact_truth=directory / "contact_classification_truth.csv",
        min_resolution_f1=min_resolution_f1,
        min_website_f1=min_website_f1,
        min_contact_macro_f1=min_contact_macro_f1,
    )
    blockers = tuple(
        f"quality_gate_failed:{check.name}:{check.metric}:{check.value}<{check.minimum}"
        for check in gate.checks
        if not check.passed
    )
    return BenchmarkEvaluationResult(
        label_status=label_status,
        quality_gate=gate,
        evaluated=True,
        passed=gate.passed,
        blockers=blockers,
    )
