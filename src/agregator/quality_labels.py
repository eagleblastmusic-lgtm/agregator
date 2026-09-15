from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contact_ground_truth import export_contact_ground_truth_template
from .ground_truth import export_ground_truth_template
from .label_sampling import (
    DEFAULT_SAMPLING_SEED,
    sample_quality_label_files,
    write_sampling_manifest,
)
from .storage import SQLiteStore
from .website_ground_truth import export_website_ground_truth_template


@dataclass(frozen=True, slots=True)
class QualityLabelBundle:
    output_dir: Path
    company_resolution_path: Path
    website_resolution_path: Path
    contact_classification_path: Path
    sampling_manifest_path: Path

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
    sampling_seed: str = DEFAULT_SAMPLING_SEED,
) -> QualityLabelBundle:
    """Export deterministic, stratified manual-label templates.

    The source exporters first create complete candidate pools. The pools are then
    deterministically sampled so a benchmark is not accidentally dominated by the
    first rows inserted into SQLite. The sampling manifest records population and
    sample counts per stratum for auditability.
    """

    if min(job_limit, company_limit, contact_limit) < 1:
        raise ValueError("quality label limits must be >= 1")
    if not sampling_seed.strip():
        raise ValueError("sampling_seed cannot be empty")

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    store.init_schema()

    with store.connect() as connection:
        job_population = _count(connection, "job_postings")
        company_population = _count(connection, "companies")
        contact_population = _count(connection, "contact_channels")

    company_resolution_path = export_ground_truth_template(
        store,
        directory / "company_resolution_truth.csv",
        limit=max(1, job_population),
    )
    website_resolution_path = export_website_ground_truth_template(
        store,
        directory / "website_resolution_truth.csv",
        limit=max(1, company_population),
    )
    contact_classification_path = export_contact_ground_truth_template(
        store,
        directory / "contact_classification_truth.csv",
        limit=max(1, contact_population),
    )

    sampling_manifest = sample_quality_label_files(
        company_resolution_path,
        website_resolution_path,
        contact_classification_path,
        job_limit=job_limit,
        company_limit=company_limit,
        contact_limit=contact_limit,
        seed=sampling_seed.strip(),
    )
    sampling_manifest_path = write_sampling_manifest(
        directory / "sampling_manifest.json",
        sampling_manifest,
    )

    return QualityLabelBundle(
        output_dir=directory,
        company_resolution_path=company_resolution_path,
        website_resolution_path=website_resolution_path,
        contact_classification_path=contact_classification_path,
        sampling_manifest_path=sampling_manifest_path,
    )


def _count(connection: Any, table: str) -> int:
    if table not in {"job_postings", "companies", "contact_channels"}:
        raise ValueError(f"unsupported label population table: {table}")
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row is not None else 0
