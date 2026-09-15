from __future__ import annotations

import csv
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
class LabelBundleStatus:
    label_dir: Path
    files: tuple[LabelFileStatus, ...]
    ready_for_quality_gate: bool
    total_rows: int
    labeled_rows: int
    remaining_rows: int
    completion_rate: float
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_dir": str(self.label_dir),
            "files": [item.to_dict() for item in self.files],
            "ready_for_quality_gate": self.ready_for_quality_gate,
            "total_rows": self.total_rows,
            "labeled_rows": self.labeled_rows,
            "remaining_rows": self.remaining_rows,
            "completion_rate": self.completion_rate,
            "blockers": list(self.blockers),
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

    return LabelBundleStatus(
        label_dir=directory,
        files=files,
        ready_for_quality_gate=not blockers,
        total_rows=total_rows,
        labeled_rows=labeled_rows,
        remaining_rows=remaining_rows,
        completion_rate=_ratio(labeled_rows, total_rows),
        blockers=tuple(blockers),
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


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
