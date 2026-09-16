from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class SourceIdentityMetrics:
    source: str
    jobs: int
    companies: int
    company_to_job_ratio: float
    avg_company_name_confidence: float
    avg_company_resolution_confidence: float
    company_name_confidence_ge_070_rate: float
    resolution_confidence_ge_070_rate: float
    city_coverage_rate: float
    description_coverage_rate: float
    resolution_methods: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_source_identity_metrics(
    store: SQLiteStore,
) -> dict[str, SourceIdentityMetrics]:
    """Build source-level diagnostics from job fields persisted at ingestion time.

    These metrics describe the records originating from each source. They deliberately
    avoid attributing later company-level enrichment (identifiers/websites) back to a
    source when provenance cannot be established at the individual job level.
    """

    store.init_schema()
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                source,
                company_id,
                company_name_confidence,
                company_resolution_confidence,
                company_resolution_method,
                city,
                description
            FROM job_postings
            ORDER BY source, id
            """
        ).fetchall()

    grouped: dict[str, list[Any]] = {}
    for row in rows:
        source = str(row["source"] or "").strip().lower()
        if source:
            grouped.setdefault(source, []).append(row)

    result: dict[str, SourceIdentityMetrics] = {}
    for source, source_rows in sorted(grouped.items()):
        jobs = len(source_rows)
        companies = len({int(row["company_id"]) for row in source_rows})
        name_confidences = [float(row["company_name_confidence"] or 0.0) for row in source_rows]
        resolution_confidences = [
            float(row["company_resolution_confidence"] or 0.0)
            for row in source_rows
        ]
        methods = Counter(
            str(row["company_resolution_method"] or "legacy")
            for row in source_rows
        )
        city_rows = sum(1 for row in source_rows if str(row["city"] or "").strip())
        description_rows = sum(
            1 for row in source_rows if str(row["description"] or "").strip()
        )

        result[source] = SourceIdentityMetrics(
            source=source,
            jobs=jobs,
            companies=companies,
            company_to_job_ratio=_ratio(companies, jobs),
            avg_company_name_confidence=_average(name_confidences),
            avg_company_resolution_confidence=_average(resolution_confidences),
            company_name_confidence_ge_070_rate=_ratio(
                sum(1 for value in name_confidences if value >= 0.70),
                jobs,
            ),
            resolution_confidence_ge_070_rate=_ratio(
                sum(1 for value in resolution_confidences if value >= 0.70),
                jobs,
            ),
            city_coverage_rate=_ratio(city_rows, jobs),
            description_coverage_rate=_ratio(description_rows, jobs),
            resolution_methods=dict(sorted(methods.items())),
        )

    return result


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
