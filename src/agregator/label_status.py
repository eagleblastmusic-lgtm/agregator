from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LabelFileStatus:
    name: str
    path: Path
    label_field: str
    exists: bool
    total_rows: int
    labeled_rows: int
    remaining_rows: int
    completion_rate: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


@dataclass(frozen=True, slots=True)
class SamplingManifestStatus:
    path: Path
    exists: bool
    valid: bool
    schema_version: str | None = None
    seed: str | None = None
    strategy: str | None = None
    file_count: int = 0
    sampled_rows_by_name: dict[str, int] | None = None
    matches_label_files: bool | None = None
    mismatches: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        payload["mismatches"] = list(self.mismatches)
        return payload


@dataclass(frozen=True, slots=True)
class LabelBundleStatus:
    label_dir: Path
    files: tuple[LabelFileStatus, ...]
    sampling_manifest: SamplingManifestStatus
    ready_for_quality_gate: bool
    total_rows: int
    labeled_rows: int
    remaining_rows: int
    completion_rate: float
    blockers: tuple[str, ...]
    audit_warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_dir": str(self.label_dir),
            "files": [item.to_dict() for item in self.files],
            "sampling_manifest": self.sampling_manifest.to_dict(),
            "ready_for_quality_gate": self.ready_for_quality_gate,
            "total_rows": self.total_rows,
            "labeled_rows": self.labeled_rows,
            "remaining_rows": self.remaining_rows,
            "completion_rate": self.completion_rate,
            "blockers": list(self.blockers),
            "audit_warnings": list(self.audit_warnings),
        }


_LABEL_FILES = (
    ("company_resolution", "company_resolution_truth.csv", "truth_company_id"),
    ("website_resolution", "website_resolution_truth.csv", "truth_domain"),
    ("contact_classification", "contact_classification_truth.csv", "truth_decision"),
)


def build_label_bundle_status(label_dir: str | Path) -> LabelBundleStatus:
    directory = Path(label_dir)
    files = tuple(
        _inspect_label_file(directory / filename, name=name, label_field=label_field)
        for name, filename, label_field in _LABEL_FILES
    )
    sampling_manifest = _inspect_sampling_manifest(directory / "sampling_manifest.json")
    if sampling_manifest.valid:
        sampling_manifest = _compare_sampling_manifest_to_labels(sampling_manifest, files)

    total_rows = sum(item.total_rows for item in files)
    labeled_rows = sum(item.labeled_rows for item in files)
    remaining_rows = sum(item.remaining_rows for item in files)
    blockers: list[str] = []

    for item in files:
        if not item.exists:
            blockers.append(f"missing_file:{item.name}")
        elif item.error:
            blockers.append(f"invalid_file:{item.name}:{item.error}")
        elif item.total_rows == 0:
            blockers.append(f"empty_file:{item.name}")
        elif item.remaining_rows > 0:
            blockers.append(f"labels_remaining:{item.name}:{item.remaining_rows}")

    audit_warnings: list[str] = []
    if not sampling_manifest.exists:
        audit_warnings.append("missing_sampling_manifest")
    elif not sampling_manifest.valid:
        audit_warnings.append(
            f"invalid_sampling_manifest:{sampling_manifest.error or 'unknown_error'}"
        )
    elif sampling_manifest.matches_label_files is False:
        audit_warnings.extend(
            f"sampling_manifest_row_mismatch:{item}"
            for item in sampling_manifest.mismatches
        )

    return LabelBundleStatus(
        label_dir=directory,
        files=files,
        sampling_manifest=sampling_manifest,
        ready_for_quality_gate=not blockers,
        total_rows=total_rows,
        labeled_rows=labeled_rows,
        remaining_rows=remaining_rows,
        completion_rate=_ratio(labeled_rows, total_rows),
        blockers=tuple(blockers),
        audit_warnings=tuple(audit_warnings),
    )


def _inspect_label_file(
    path: Path,
    *,
    name: str,
    label_field: str,
) -> LabelFileStatus:
    if not path.exists():
        return LabelFileStatus(
            name=name,
            path=path,
            label_field=label_field,
            exists=False,
            total_rows=0,
            labeled_rows=0,
            remaining_rows=0,
            completion_rate=0.0,
        )

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or [])
            if label_field not in fieldnames:
                return LabelFileStatus(
                    name=name,
                    path=path,
                    label_field=label_field,
                    exists=True,
                    total_rows=0,
                    labeled_rows=0,
                    remaining_rows=0,
                    completion_rate=0.0,
                    error=f"missing_column:{label_field}",
                )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return LabelFileStatus(
            name=name,
            path=path,
            label_field=label_field,
            exists=True,
            total_rows=0,
            labeled_rows=0,
            remaining_rows=0,
            completion_rate=0.0,
            error=type(exc).__name__,
        )

    total_rows = len(rows)
    labeled_rows = sum(1 for row in rows if (row.get(label_field) or "").strip())
    remaining_rows = total_rows - labeled_rows
    return LabelFileStatus(
        name=name,
        path=path,
        label_field=label_field,
        exists=True,
        total_rows=total_rows,
        labeled_rows=labeled_rows,
        remaining_rows=remaining_rows,
        completion_rate=_ratio(labeled_rows, total_rows),
    )


def _inspect_sampling_manifest(path: Path) -> SamplingManifestStatus:
    if not path.exists():
        return SamplingManifestStatus(path=path, exists=False, valid=False)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return SamplingManifestStatus(
            path=path,
            exists=True,
            valid=False,
            error=type(exc).__name__,
        )

    if not isinstance(payload, dict):
        return SamplingManifestStatus(
            path=path,
            exists=True,
            valid=False,
            error="root_not_object",
        )

    schema_version = str(payload.get("schema_version") or "").strip()
    seed = str(payload.get("seed") or "").strip()
    strategy = str(payload.get("strategy") or "").strip()
    files = payload.get("files")
    missing: list[str] = []
    if not schema_version:
        missing.append("schema_version")
    if not seed:
        missing.append("seed")
    if not strategy:
        missing.append("strategy")
    if not isinstance(files, list):
        missing.append("files")
    if missing:
        return SamplingManifestStatus(
            path=path,
            exists=True,
            valid=False,
            schema_version=schema_version or None,
            seed=seed or None,
            strategy=strategy or None,
            file_count=len(files) if isinstance(files, list) else 0,
            error=f"missing_or_invalid:{','.join(missing)}",
        )

    sampled_rows_by_name: dict[str, int] = {}
    invalid_entries: list[str] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            invalid_entries.append(str(index))
            continue
        name = str(item.get("name") or "").strip()
        sampled_rows = item.get("sampled_rows")
        if not name or isinstance(sampled_rows, bool) or not isinstance(sampled_rows, int):
            invalid_entries.append(str(index))
            continue
        if sampled_rows < 0:
            invalid_entries.append(str(index))
            continue
        sampled_rows_by_name[name] = sampled_rows

    if invalid_entries:
        return SamplingManifestStatus(
            path=path,
            exists=True,
            valid=False,
            schema_version=schema_version,
            seed=seed,
            strategy=strategy,
            file_count=len(files),
            sampled_rows_by_name=sampled_rows_by_name,
            error=f"invalid_file_entries:{','.join(invalid_entries)}",
        )

    return SamplingManifestStatus(
        path=path,
        exists=True,
        valid=True,
        schema_version=schema_version,
        seed=seed,
        strategy=strategy,
        file_count=len(files),
        sampled_rows_by_name=sampled_rows_by_name,
    )


def _compare_sampling_manifest_to_labels(
    manifest: SamplingManifestStatus,
    files: tuple[LabelFileStatus, ...],
) -> SamplingManifestStatus:
    declared = manifest.sampled_rows_by_name or {}
    mismatches: list[str] = []
    for item in files:
        expected = declared.get(item.name)
        if expected is None:
            mismatches.append(f"{item.name}:missing_in_manifest")
            continue
        if item.exists and item.error is None and expected != item.total_rows:
            mismatches.append(f"{item.name}:expected={expected}:actual={item.total_rows}")

    return SamplingManifestStatus(
        path=manifest.path,
        exists=manifest.exists,
        valid=manifest.valid,
        schema_version=manifest.schema_version,
        seed=manifest.seed,
        strategy=manifest.strategy,
        file_count=manifest.file_count,
        sampled_rows_by_name=manifest.sampled_rows_by_name,
        matches_label_files=not mismatches,
        mismatches=tuple(mismatches),
        error=manifest.error,
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
