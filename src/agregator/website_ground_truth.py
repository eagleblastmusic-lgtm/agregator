from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .audit import init_audit_schema
from .company_websites import init_company_website_candidate_schema
from .ground_truth_common import EXCLUDE_LABEL, count_excluded_labels
from .storage import SQLiteStore

NO_WEBSITE = "__none__"


@dataclass(frozen=True, slots=True)
class WebsiteGroundTruthLabel:
    company_id: int
    truth_domain: str | None


@dataclass(frozen=True, slots=True)
class WebsiteEvaluation:
    labeled_rows: int
    matched_rows: int
    missing_rows: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    wrong_domain: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    excluded_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_domain(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text or text == NO_WEBSITE:
        return None
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host or None


def load_website_ground_truth_csv(path: str | Path) -> list[WebsiteGroundTruthLabel]:
    labels: list[WebsiteGroundTruthLabel] = []
    seen: set[int] = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"company_id", "truth_domain"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"website ground truth CSV missing columns: {missing_text}")

        for line_number, row in enumerate(reader, start=2):
            raw_truth = (row.get("truth_domain") or "").strip()
            if not raw_truth:
                continue

            raw_company_id = (row.get("company_id") or "").strip()
            try:
                company_id = int(raw_company_id)
            except ValueError as exc:
                raise ValueError(
                    f"website ground truth CSV has invalid company_id at line {line_number}"
                ) from exc
            if company_id <= 0:
                raise ValueError(
                    f"website ground truth CSV has invalid company_id at line {line_number}"
                )
            if company_id in seen:
                raise ValueError(
                    f"duplicate website ground truth company at line {line_number}: {company_id}"
                )
            seen.add(company_id)

            if raw_truth.lower() == EXCLUDE_LABEL:
                continue

            labels.append(
                WebsiteGroundTruthLabel(
                    company_id=company_id,
                    truth_domain=normalize_domain(raw_truth),
                )
            )
    return labels


def export_website_ground_truth_template(
    store: SQLiteStore,
    output: str | Path,
    *,
    limit: int = 1000,
) -> Path:
    store.init_schema()
    init_audit_schema(store)
    init_company_website_candidate_schema(store)
    path = Path(output)
    with store.connect() as connection:
        rows = connection.execute(
            """
            WITH latest_verification AS (
                SELECT w.*
                FROM website_verification_runs w
                JOIN (
                    SELECT company_id, MAX(id) AS latest_id
                    FROM website_verification_runs
                    GROUP BY company_id
                ) latest ON latest.latest_id = w.id
            )
            SELECT
                c.id AS company_id,
                c.canonical_name,
                c.city,
                c.website_url AS predicted_website_url,
                c.website_confidence,
                lv.id AS latest_verification_id,
                lv.outcome AS verification_outcome,
                lv.resolution_origin AS predicted_resolution_origin,
                lv.resolution_source AS predicted_resolution_source,
                lv.verification_signals_json,
                (
                    SELECT COUNT(*)
                    FROM company_website_candidates cwc
                    WHERE cwc.company_id = c.id
                ) AS source_website_candidate_count,
                COUNT(DISTINCT j.id) AS job_count,
                GROUP_CONCAT(DISTINCT j.source) AS sources
            FROM companies c
            LEFT JOIN job_postings j ON j.company_id = c.id
            LEFT JOIN latest_verification lv ON lv.company_id = c.id
            GROUP BY c.id
            ORDER BY job_count DESC, c.id ASC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()

    fieldnames = [
        "company_id",
        "truth_domain",
        "canonical_name",
        "city",
        "predicted_website_url",
        "predicted_domain",
        "website_confidence",
        "latest_verification_id",
        "verification_outcome",
        "predicted_resolution_origin",
        "predicted_resolution_source",
        "source_website_candidate_count",
        "verification_signals_json",
        "job_count",
        "sources",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "company_id": row["company_id"],
                    "truth_domain": "",
                    "canonical_name": row["canonical_name"],
                    "city": row["city"],
                    "predicted_website_url": row["predicted_website_url"],
                    "predicted_domain": normalize_domain(row["predicted_website_url"]),
                    "website_confidence": row["website_confidence"],
                    "latest_verification_id": row["latest_verification_id"],
                    "verification_outcome": row["verification_outcome"],
                    "predicted_resolution_origin": row["predicted_resolution_origin"],
                    "predicted_resolution_source": row["predicted_resolution_source"],
                    "source_website_candidate_count": row[
                        "source_website_candidate_count"
                    ],
                    "verification_signals_json": row["verification_signals_json"],
                    "job_count": row["job_count"],
                    "sources": row["sources"],
                }
            )
    return path


def evaluate_website_resolution(
    store: SQLiteStore,
    labels: list[WebsiteGroundTruthLabel],
) -> WebsiteEvaluation:
    store.init_schema()
    predictions: dict[int, str | None] = {}
    with store.connect() as connection:
        for label in labels:
            row = connection.execute(
                "SELECT website_url FROM companies WHERE id = ?",
                (label.company_id,),
            ).fetchone()
            if row is not None:
                predictions[label.company_id] = normalize_domain(row["website_url"])

    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    wrong_domain = 0

    for label in labels:
        if label.company_id not in predictions:
            continue
        predicted = predictions[label.company_id]
        truth = label.truth_domain

        if truth is None and predicted is None:
            true_negative += 1
        elif truth is None and predicted is not None:
            false_positive += 1
        elif truth is not None and predicted is None:
            false_negative += 1
        elif truth == predicted:
            true_positive += 1
        else:
            wrong_domain += 1
            false_positive += 1
            false_negative += 1

    matched_rows = len(predictions)
    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    accuracy = _safe_ratio(true_positive + true_negative, matched_rows)

    return WebsiteEvaluation(
        labeled_rows=len(labels),
        matched_rows=matched_rows,
        missing_rows=len(labels) - matched_rows,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=true_negative,
        wrong_domain=wrong_domain,
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=accuracy,
    )


def evaluate_website_resolution_csv(
    store: SQLiteStore,
    path: str | Path,
) -> WebsiteEvaluation:
    result = evaluate_website_resolution(store, load_website_ground_truth_csv(path))
    return replace(
        result,
        excluded_rows=count_excluded_labels(path, "truth_domain"),
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
