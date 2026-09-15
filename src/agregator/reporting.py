from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .company_identifiers import init_company_identifier_schema
from .employer_score import rank_companies
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    jobs_total: int
    companies_total: int
    sources_total: int
    high_confidence_companies: int
    enriched_companies: int
    websites_found: int
    company_identifiers_total: int
    companies_with_identifiers: int
    identifier_conflicts: int
    contact_channels_total: int
    green_channels: int
    review_channels: int
    ignored_channels: int
    company_to_job_ratio: float
    website_find_rate: float
    identifier_company_rate: float
    green_company_rate: float
    employer_score_average: float
    employer_score_ge_60: int
    employer_score_distribution: dict[str, int]
    source_job_counts: dict[str, int]
    company_resolution_counts: dict[str, int]
    source_run_metrics: dict[str, dict[str, int | float]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_benchmark_report(
    store: SQLiteStore,
    *,
    high_confidence_threshold: float = 0.7,
) -> BenchmarkReport:
    store.init_schema()
    init_company_identifier_schema(store)
    with store.connect() as connection:
        jobs_total = _scalar(connection, "SELECT COUNT(*) FROM job_postings")
        companies_total = _scalar(connection, "SELECT COUNT(*) FROM companies")
        sources_total = _scalar(
            connection,
            "SELECT COUNT(DISTINCT source) FROM job_postings",
        )
        high_confidence_companies = _scalar(
            connection,
            "SELECT COUNT(*) FROM companies WHERE identity_confidence >= ?",
            (high_confidence_threshold,),
        )
        enriched_companies = _scalar(
            connection,
            "SELECT COUNT(*) FROM companies WHERE enriched_at IS NOT NULL",
        )
        websites_found = _scalar(
            connection,
            "SELECT COUNT(*) FROM companies WHERE website_url IS NOT NULL",
        )
        company_identifiers_total = _scalar(
            connection,
            "SELECT COUNT(*) FROM company_identifiers",
        )
        companies_with_identifiers = _scalar(
            connection,
            "SELECT COUNT(DISTINCT company_id) FROM company_identifiers",
        )
        identifier_conflicts = _scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM (
                SELECT kind, value
                FROM company_identifiers
                GROUP BY kind, value
                HAVING COUNT(DISTINCT company_id) > 1
            ) conflicts
            """,
        )
        contact_channels_total = _scalar(
            connection,
            "SELECT COUNT(*) FROM contact_channels",
        )
        green_channels = _scalar(
            connection,
            "SELECT COUNT(*) FROM contact_channels WHERE decision = 'green'",
        )
        review_channels = _scalar(
            connection,
            "SELECT COUNT(*) FROM contact_channels WHERE decision = 'review'",
        )
        ignored_channels = _scalar(
            connection,
            "SELECT COUNT(*) FROM contact_channels WHERE decision = 'ignore'",
        )
        green_companies = _scalar(
            connection,
            """
            SELECT COUNT(DISTINCT company_id)
            FROM contact_channels
            WHERE decision = 'green'
            """,
        )
        source_rows = connection.execute(
            """
            SELECT source, COUNT(*) AS jobs
            FROM job_postings
            GROUP BY source
            ORDER BY jobs DESC, source ASC
            """
        ).fetchall()
        resolution_rows = connection.execute(
            """
            SELECT
                COALESCE(company_resolution_method, 'legacy') AS method,
                COUNT(*) AS jobs
            FROM job_postings
            GROUP BY COALESCE(company_resolution_method, 'legacy')
            ORDER BY jobs DESC, method ASC
            """
        ).fetchall()
        run_rows = connection.execute(
            """
            SELECT
                source,
                COUNT(*) AS runs_total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successful_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                SUM(pages_processed) AS pages_processed,
                SUM(jobs_seen) AS jobs_seen,
                SUM(jobs_inserted) AS jobs_inserted,
                SUM(jobs_updated) AS jobs_updated,
                SUM(companies_created) AS companies_created,
                AVG(
                    CASE WHEN finished_at IS NOT NULL THEN
                        (julianday(finished_at) - julianday(started_at)) * 86400.0
                    END
                ) AS avg_seconds_per_run,
                SUM(
                    CASE WHEN finished_at IS NOT NULL THEN
                        (julianday(finished_at) - julianday(started_at)) * 86400.0
                    ELSE 0
                    END
                ) AS total_seconds
            FROM source_runs
            GROUP BY source
            ORDER BY source ASC
            """
        ).fetchall()

    source_job_counts = {str(row["source"]): int(row["jobs"]) for row in source_rows}
    company_resolution_counts = {
        str(row["method"]): int(row["jobs"]) for row in resolution_rows
    }
    source_run_metrics = _source_run_metrics(run_rows)
    employer_scores = rank_companies(store, min_score=0, limit=max(1, companies_total))
    score_values = [item.score for item in employer_scores]

    return BenchmarkReport(
        jobs_total=jobs_total,
        companies_total=companies_total,
        sources_total=sources_total,
        high_confidence_companies=high_confidence_companies,
        enriched_companies=enriched_companies,
        websites_found=websites_found,
        company_identifiers_total=company_identifiers_total,
        companies_with_identifiers=companies_with_identifiers,
        identifier_conflicts=identifier_conflicts,
        contact_channels_total=contact_channels_total,
        green_channels=green_channels,
        review_channels=review_channels,
        ignored_channels=ignored_channels,
        company_to_job_ratio=_ratio(companies_total, jobs_total),
        website_find_rate=_ratio(websites_found, enriched_companies),
        identifier_company_rate=_ratio(companies_with_identifiers, companies_total),
        green_company_rate=_ratio(green_companies, enriched_companies),
        employer_score_average=_average(score_values),
        employer_score_ge_60=sum(1 for score in score_values if score >= 60),
        employer_score_distribution=_score_distribution(score_values),
        source_job_counts=source_job_counts,
        company_resolution_counts=company_resolution_counts,
        source_run_metrics=source_run_metrics,
    )


def export_green_channels(
    store: SQLiteStore,
    output: str | Path,
    *,
    format: str | None = None,
    limit: int = 100_000,
) -> Path:
    store.init_schema()
    path = Path(output)
    export_format = (format or path.suffix.lstrip(".") or "json").lower()
    rows = store.list_green_channels(limit=limit)

    path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "json":
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    if export_format == "csv":
        fieldnames = [
            "canonical_name",
            "city",
            "website_url",
            "kind",
            "value",
            "purpose",
            "confidence",
            "evidence_url",
            "evidence_text",
            "verified_at",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    raise ValueError(f"unsupported export format: {export_format}")


def _source_run_metrics(rows: list[Any]) -> dict[str, dict[str, int | float]]:
    metrics: dict[str, dict[str, int | float]] = {}
    for row in rows:
        runs_total = int(row["runs_total"] or 0)
        successful_runs = int(row["successful_runs"] or 0)
        failed_runs = int(row["failed_runs"] or 0)
        jobs_seen = int(row["jobs_seen"] or 0)
        total_seconds = float(row["total_seconds"] or 0.0)
        metrics[str(row["source"])] = {
            "runs_total": runs_total,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": _ratio(successful_runs, runs_total),
            "pages_processed": int(row["pages_processed"] or 0),
            "jobs_seen": jobs_seen,
            "jobs_inserted": int(row["jobs_inserted"] or 0),
            "jobs_updated": int(row["jobs_updated"] or 0),
            "companies_created": int(row["companies_created"] or 0),
            "avg_seconds_per_run": round(float(row["avg_seconds_per_run"] or 0.0), 4),
            "total_seconds": round(total_seconds, 4),
            "seconds_per_job_seen": _ratio_float(total_seconds, jobs_seen),
        }
    return metrics


def _score_distribution(values: list[int]) -> dict[str, int]:
    buckets = {
        "0-24": 0,
        "25-49": 0,
        "50-74": 0,
        "75-100": 0,
    }
    for value in values:
        if value < 25:
            buckets["0-24"] += 1
        elif value < 50:
            buckets["25-49"] += 1
        elif value < 75:
            buckets["50-74"] += 1
        else:
            buckets["75-100"] += 1
    return buckets


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _scalar(connection: Any, query: str, params: tuple[object, ...] = ()) -> int:
    row = connection.execute(query, params).fetchone()
    return int(row[0]) if row is not None else 0


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _ratio_float(numerator: float, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
