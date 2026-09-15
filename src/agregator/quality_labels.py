from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contact_ground_truth import export_contact_ground_truth_template
from .ground_truth import export_ground_truth_template
from .storage import SQLiteStore
from .website_ground_truth import export_website_ground_truth_template


@dataclass(frozen=True, slots=True)
class QualityLabelBundle:
    output_dir: Path
    company_resolution_path: Path
    website_resolution_path: Path
    contact_classification_path: Path

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: str(value) for key, value in payload.items()}


def export_quality_label_bundle(
    store: SQLiteStore,
    output_dir: str | Path,
    *,
    job_limit: int = 1000,
    company_limit: int = 1000,
    contact_limit: int = 1000,
) -> QualityLabelBundle:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    company_resolution_path = export_ground_truth_template(
        store,
        directory / "company_resolution_truth.csv",
        limit=job_limit,
    )
    website_resolution_path = export_website_ground_truth_template(
        store,
        directory / "website_resolution_truth.csv",
        limit=company_limit,
    )
    contact_classification_path = export_contact_ground_truth_template(
        store,
        directory / "contact_classification_truth.csv",
        limit=contact_limit,
    )

    return QualityLabelBundle(
        output_dir=directory,
        company_resolution_path=company_resolution_path,
        website_resolution_path=website_resolution_path,
        contact_classification_path=contact_classification_path,
    )
