from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LabelBlindingResult:
    reference_dir: Path
    company_resolution_reference_path: Path
    website_resolution_reference_path: Path
    contact_classification_reference_path: Path

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: str(value) for key, value in payload.items()}


_COMPANY_BLIND_FIELDS = [
    "source",
    "source_id",
    "truth_company_id",
    "company_name_raw",
    "city",
    "url",
]

_WEBSITE_BLIND_FIELDS = [
    "company_id",
    "truth_domain",
    "canonical_name",
    "city",
    "job_count",
    "sources",
]

_CONTACT_BLIND_FIELDS = [
    "contact_id",
    "truth_decision",
    "truth_purpose",
    "canonical_name",
    "kind",
    "value",
    "evidence_url",
    "evidence_text",
    "latest_evidence_snapshot_id",
    "evidence_content_sha256",
    "evidence_captured_at",
]


def blind_quality_label_files(
    company_resolution_path: str | Path,
    website_resolution_path: str | Path,
    contact_classification_path: str | Path,
    *,
    reference_dir: str | Path,
) -> LabelBlindingResult:
    """Hide model predictions from primary manual-label files.

    The sampled, prediction-rich rows are copied to a separate reference directory
    before the primary CSV files are rewritten with only identifiers, truth fields
    and source/evidence context. The reference files are intended for adjudication
    after an independent label has been recorded, not for primary annotation.
    """

    directory = Path(reference_dir)
    directory.mkdir(parents=True, exist_ok=True)

    company_reference = directory / "company_resolution_reference.csv"
    website_reference = directory / "website_resolution_reference.csv"
    contact_reference = directory / "contact_classification_reference.csv"

    _blind_csv(
        Path(company_resolution_path),
        company_reference,
        blind_fields=_COMPANY_BLIND_FIELDS,
    )
    _blind_csv(
        Path(website_resolution_path),
        website_reference,
        blind_fields=_WEBSITE_BLIND_FIELDS,
    )
    _blind_csv(
        Path(contact_classification_path),
        contact_reference,
        blind_fields=_CONTACT_BLIND_FIELDS,
    )

    return LabelBlindingResult(
        reference_dir=directory,
        company_resolution_reference_path=company_reference,
        website_resolution_reference_path=website_reference,
        contact_classification_reference_path=contact_reference,
    )


def _blind_csv(
    source_path: Path,
    reference_path: Path,
    *,
    blind_fields: list[str],
) -> None:
    fieldnames, rows = _read_csv(source_path)
    missing = [field for field in blind_fields if field not in fieldnames]
    if missing:
        raise ValueError(
            f"cannot blind {source_path.name}; missing columns: {', '.join(missing)}"
        )

    reference_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(reference_path, fieldnames, rows)
    _write_csv(source_path, blind_fields, rows)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
