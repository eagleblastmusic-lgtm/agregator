from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .ground_truth_common import EXCLUDE_LABEL
from .models import ChannelPurpose, Decision
from .website_ground_truth import NO_WEBSITE, normalize_domain


class LabelKind(StrEnum):
    COMPANY_RESOLUTION = "company_resolution"
    WEBSITE_RESOLUTION = "website_resolution"
    CONTACT_CLASSIFICATION = "contact_classification"


@dataclass(frozen=True, slots=True)
class LabelRow:
    kind: LabelKind
    path: Path
    row_number: int
    label_field: str
    row: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "path": str(self.path),
            "row_number": self.row_number,
            "label_field": self.label_field,
            "row": self.row,
        }


@dataclass(frozen=True, slots=True)
class LabelUpdate:
    kind: LabelKind
    path: Path
    row_number: int
    label_field: str
    previous_value: str
    new_value: str
    purpose_value: str | None
    remaining_rows: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["path"] = str(self.path)
        return payload


@dataclass(frozen=True, slots=True)
class _LabelSpec:
    filename: str
    label_field: str


_SPECS = {
    LabelKind.COMPANY_RESOLUTION: _LabelSpec(
        filename="company_resolution_truth.csv",
        label_field="truth_company_id",
    ),
    LabelKind.WEBSITE_RESOLUTION: _LabelSpec(
        filename="website_resolution_truth.csv",
        label_field="truth_domain",
    ),
    LabelKind.CONTACT_CLASSIFICATION: _LabelSpec(
        filename="contact_classification_truth.csv",
        label_field="truth_decision",
    ),
}


def next_unlabeled_row(label_dir: str | Path, kind: LabelKind | str) -> LabelRow | None:
    """Return the first unlabeled blind-primary row without consulting predictions."""

    label_kind = LabelKind(kind)
    path, fieldnames, rows = _read_rows(label_dir, label_kind)
    del fieldnames
    label_field = _SPECS[label_kind].label_field
    for index, row in enumerate(rows, start=1):
        if not (row.get(label_field) or "").strip():
            return LabelRow(
                kind=label_kind,
                path=path,
                row_number=index,
                label_field=label_field,
                row=dict(row),
            )
    return None


def set_row_label(
    label_dir: str | Path,
    kind: LabelKind | str,
    row_number: int,
    *,
    value: str | None = None,
    purpose: str | None = None,
    exclude: bool = False,
    overwrite: bool = False,
) -> LabelUpdate:
    """Persist one independent truth decision into the blind primary CSV.

    Predictions are intentionally unavailable here. The benchmark keeps model outputs in
    `prediction_reference/`; this workflow edits only primary ground-truth files so the
    operator cannot accidentally accept a prediction while creating the independent label.
    """

    label_kind = LabelKind(kind)
    if row_number < 1:
        raise ValueError("row_number must be >= 1")

    explicit_value = (value or "").strip()
    modes = int(bool(explicit_value)) + int(exclude)
    if modes != 1:
        raise ValueError("choose exactly one labeling mode: value or exclude")

    path, fieldnames, rows = _read_rows(label_dir, label_kind)
    if row_number > len(rows):
        raise ValueError(f"row_number out of range: {row_number} > {len(rows)}")

    spec = _SPECS[label_kind]
    row = rows[row_number - 1]
    previous = (row.get(spec.label_field) or "").strip()
    if previous and not overwrite:
        raise ValueError(
            f"row {row_number} is already labeled as {previous!r}; use overwrite=True"
        )

    new_value, purpose_value = _resolve_label(
        label_kind,
        explicit_value=explicit_value,
        purpose=purpose,
        exclude=exclude,
    )
    row[spec.label_field] = new_value
    if label_kind == LabelKind.CONTACT_CLASSIFICATION:
        row["truth_purpose"] = purpose_value or ""

    _write_rows(path, fieldnames, rows)
    remaining_rows = sum(
        1
        for item in rows
        if not (item.get(spec.label_field) or "").strip()
    )
    return LabelUpdate(
        kind=label_kind,
        path=path,
        row_number=row_number,
        label_field=spec.label_field,
        previous_value=previous,
        new_value=new_value,
        purpose_value=purpose_value,
        remaining_rows=remaining_rows,
    )


def _resolve_label(
    kind: LabelKind,
    *,
    explicit_value: str,
    purpose: str | None,
    exclude: bool,
) -> tuple[str, str | None]:
    if exclude:
        return EXCLUDE_LABEL, None

    if kind == LabelKind.COMPANY_RESOLUTION:
        if purpose:
            raise ValueError("purpose is only valid for contact_classification")
        if not explicit_value:
            raise ValueError("company truth label cannot be empty")
        if explicit_value.lower() == NO_WEBSITE:
            raise ValueError("__none__ is not valid for company_resolution")
        return explicit_value, None

    if kind == LabelKind.WEBSITE_RESOLUTION:
        if purpose:
            raise ValueError("purpose is only valid for contact_classification")
        raw = explicit_value
        if raw.lower() == NO_WEBSITE:
            return NO_WEBSITE, None
        if raw.lower() == EXCLUDE_LABEL:
            return EXCLUDE_LABEL, None
        domain = normalize_domain(raw)
        if not domain:
            raise ValueError(f"invalid website truth domain: {raw!r}")
        return domain, None

    if kind == LabelKind.CONTACT_CLASSIFICATION:
        decision_text = explicit_value.lower()
        valid_decisions = {item.value for item in Decision}
        if decision_text not in valid_decisions:
            raise ValueError(
                f"invalid contact truth decision: {decision_text!r}; "
                f"expected one of {sorted(valid_decisions)}"
            )

        raw_purpose = (purpose or "").strip().lower()
        if raw_purpose:
            valid_purposes = {item.value for item in ChannelPurpose}
            if raw_purpose not in valid_purposes:
                raise ValueError(
                    f"invalid contact truth purpose: {raw_purpose!r}; "
                    f"expected one of {sorted(valid_purposes)}"
                )
        return decision_text, raw_purpose or None

    raise ValueError(f"unsupported label kind: {kind}")


def _read_rows(
    label_dir: str | Path,
    kind: LabelKind,
) -> tuple[Path, list[str], list[dict[str, str]]]:
    spec = _SPECS[kind]
    path = Path(label_dir) / spec.filename
    if not path.exists():
        raise ValueError(f"label file does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if spec.label_field not in fieldnames:
            raise ValueError(f"label file missing column: {spec.label_field}")
        if kind == LabelKind.CONTACT_CLASSIFICATION and "truth_purpose" not in fieldnames:
            raise ValueError("label file missing column: truth_purpose")
        rows = [dict(row) for row in reader]
    return path, fieldnames, rows


def _write_rows(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
