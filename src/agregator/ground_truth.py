from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from pathlib import Path
from typing import Any

from .ground_truth_common import EXCLUDE_LABEL, count_excluded_labels
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class GroundTruthLabel:
    source: str
    source_id: str
    truth_company_id: str


@dataclass(frozen=True, slots=True)
class ResolutionEvaluation:
    labeled_rows: int
    matched_rows: int
    missing_rows: int
    evaluated_pairs: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: float
    recall: float
    f1: float
    excluded_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_ground_truth_csv(path: str | Path) -> list[GroundTruthLabel]:
    labels: list[GroundTruthLabel] = []
    seen: set[tuple[str, str]] = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"source", "source_id", "truth_company_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"ground truth CSV missing columns: {missing_text}")

        for line_number, row in enumerate(reader, start=2):
            source = (row.get("source") or "").strip()
            source_id = (row.get("source_id") or "").strip()
            truth_company_id = (row.get("truth_company_id") or "").strip()
            if not source or not source_id or not truth_company_id:
                raise ValueError(f"ground truth CSV has empty required value at line {line_number}")

            key = (source, source_id)
            if key in seen:
                raise ValueError(
                    f"duplicate ground truth job at line {line_number}: {source}/{source_id}"
                )
            seen.add(key)

            if truth_company_id.lower() == EXCLUDE_LABEL:
                continue

            labels.append(
                GroundTruthLabel(
                    source=source,
                    source_id=source_id,
                    truth_company_id=truth_company_id,
                )
            )
    return labels


def export_ground_truth_template(
    store: SQLiteStore,
    output: str | Path,
    *,
    limit: int = 1000,
) -> Path:
    store.init_schema()
    path = Path(output)
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                j.source,
                j.source_id,
                j.company_name_raw,
                j.city,
                j.url,
                j.company_id AS predicted_company_id,
                j.company_resolution_method,
                j.company_resolution_confidence
            FROM job_postings j
            ORDER BY j.id ASC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()

    fieldnames = [
        "source",
        "source_id",
        "truth_company_id",
        "company_name_raw",
        "city",
        "url",
        "predicted_company_id",
        "company_resolution_method",
        "company_resolution_confidence",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source": row["source"],
                    "source_id": row["source_id"],
                    "truth_company_id": "",
                    "company_name_raw": row["company_name_raw"],
                    "city": row["city"],
                    "url": row["url"],
                    "predicted_company_id": row["predicted_company_id"],
                    "company_resolution_method": row["company_resolution_method"],
                    "company_resolution_confidence": row[
                        "company_resolution_confidence"
                    ],
                }
            )
    return path


def evaluate_company_resolution(
    store: SQLiteStore,
    labels: list[GroundTruthLabel],
) -> ResolutionEvaluation:
    store.init_schema()
    predicted: list[tuple[GroundTruthLabel, int]] = []

    with store.connect() as connection:
        for label in labels:
            row = connection.execute(
                """
                SELECT company_id
                FROM job_postings
                WHERE source = ? AND source_id = ?
                """,
                (label.source, label.source_id),
            ).fetchone()
            if row is not None:
                predicted.append((label, int(row["company_id"])))

    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0

    for left, right in combinations(predicted, 2):
        left_label, left_company_id = left
        right_label, right_company_id = right
        truth_same = left_label.truth_company_id == right_label.truth_company_id
        predicted_same = left_company_id == right_company_id

        if truth_same and predicted_same:
            true_positive += 1
        elif not truth_same and predicted_same:
            false_positive += 1
        elif truth_same and not predicted_same:
            false_negative += 1
        else:
            true_negative += 1

    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)

    return ResolutionEvaluation(
        labeled_rows=len(labels),
        matched_rows=len(predicted),
        missing_rows=len(labels) - len(predicted),
        evaluated_pairs=(len(predicted) * (len(predicted) - 1)) // 2,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=true_negative,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def evaluate_company_resolution_csv(
    store: SQLiteStore,
    path: str | Path,
) -> ResolutionEvaluation:
    result = evaluate_company_resolution(store, load_ground_truth_csv(path))
    return replace(
        result,
        excluded_rows=count_excluded_labels(path, "truth_company_id"),
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
