from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contact_ground_truth import evaluate_contact_classification_csv
from .ground_truth import evaluate_company_resolution_csv
from .storage import SQLiteStore
from .website_ground_truth import evaluate_website_resolution_csv


@dataclass(frozen=True, slots=True)
class QualityCheck:
    name: str
    metric: str
    value: float
    minimum: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    passed: bool
    checks: tuple[QualityCheck, ...]
    reports: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "reports": self.reports,
        }


def evaluate_quality_gate(
    store: SQLiteStore,
    *,
    resolution_truth: str | Path | None = None,
    website_truth: str | Path | None = None,
    contact_truth: str | Path | None = None,
    min_resolution_f1: float = 0.95,
    min_website_f1: float = 0.95,
    min_contact_macro_f1: float = 0.90,
) -> QualityGateResult:
    checks: list[QualityCheck] = []
    reports: dict[str, dict[str, Any]] = {}

    if resolution_truth is not None:
        report = evaluate_company_resolution_csv(store, resolution_truth)
        reports["company_resolution"] = report.to_dict()
        checks.append(
            QualityCheck(
                name="company_resolution",
                metric="f1",
                value=report.f1,
                minimum=min_resolution_f1,
                passed=report.f1 >= min_resolution_f1,
            )
        )

    if website_truth is not None:
        report = evaluate_website_resolution_csv(store, website_truth)
        reports["website_resolution"] = report.to_dict()
        checks.append(
            QualityCheck(
                name="website_resolution",
                metric="f1",
                value=report.f1,
                minimum=min_website_f1,
                passed=report.f1 >= min_website_f1,
            )
        )

    if contact_truth is not None:
        report = evaluate_contact_classification_csv(store, contact_truth)
        reports["contact_classification"] = report.to_dict()
        checks.append(
            QualityCheck(
                name="contact_classification",
                metric="decision_macro_f1",
                value=report.decision_macro_f1,
                minimum=min_contact_macro_f1,
                passed=report.decision_macro_f1 >= min_contact_macro_f1,
            )
        )

    return QualityGateResult(
        passed=bool(checks) and all(check.passed for check in checks),
        checks=tuple(checks),
        reports=reports,
    )
