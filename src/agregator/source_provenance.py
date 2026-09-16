from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .company_identifiers import init_company_identifier_schema
from .company_websites import init_company_website_candidate_schema
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class SourceProvenanceMetrics:
    source: str
    jobs: int
    companies: int
    identifier_observations: int
    identifiers: int
    companies_with_identifiers: int
    identifier_company_rate: float
    identifier_kinds: dict[str, int]
    identifier_evidence_sources: dict[str, int]
    website_candidate_observations: int
    website_candidates: int
    companies_with_website_candidates: int
    website_candidate_company_rate: float
    website_evidence_sources: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_source_provenance_metrics(
    store: SQLiteStore,
) -> dict[str, SourceProvenanceMetrics]:
    """Attribute explicit employer evidence to the job source that supplied it.

    The aggregate company tables intentionally keep the strongest/current representation.
    These diagnostics instead read dedicated observation tables, so evidence supplied by
    two portals for the same company is credited to both portals rather than whichever
    observation last updated the aggregate row.
    """

    store.init_schema()
    init_company_identifier_schema(store)
    init_company_website_candidate_schema(store)

    with store.connect() as connection:
        job_rows = connection.execute(
            """
            SELECT source, COUNT(*) AS jobs, COUNT(DISTINCT company_id) AS companies
            FROM job_postings
            GROUP BY source
            ORDER BY source
            """
        ).fetchall()
        identifier_rows = connection.execute(
            """
            SELECT
                job_source,
                company_id,
                kind,
                value,
                evidence_source,
                observation_count
            FROM company_identifier_observations
            ORDER BY job_source, id
            """
        ).fetchall()
        website_rows = connection.execute(
            """
            SELECT
                job_source,
                company_id,
                url,
                evidence_source,
                observation_count
            FROM company_website_candidate_observations
            ORDER BY job_source, id
            """
        ).fetchall()

    base = {
        str(row["source"]): {
            "jobs": int(row["jobs"]),
            "companies": int(row["companies"]),
        }
        for row in job_rows
    }
    identifier_by_source: dict[str, list[Any]] = {}
    website_by_source: dict[str, list[Any]] = {}
    for row in identifier_rows:
        identifier_by_source.setdefault(str(row["job_source"]), []).append(row)
    for row in website_rows:
        website_by_source.setdefault(str(row["job_source"]), []).append(row)

    sources = sorted(set(base) | set(identifier_by_source) | set(website_by_source))
    result: dict[str, SourceProvenanceMetrics] = {}
    for source in sources:
        jobs = int(base.get(source, {}).get("jobs", 0))
        companies = int(base.get(source, {}).get("companies", 0))
        source_identifiers = identifier_by_source.get(source, [])
        source_websites = website_by_source.get(source, [])

        identifier_companies = {int(row["company_id"]) for row in source_identifiers}
        website_companies = {int(row["company_id"]) for row in source_websites}
        identifier_kinds = Counter(str(row["kind"]) for row in source_identifiers)
        identifier_sources = Counter(
            str(row["evidence_source"]) for row in source_identifiers
        )
        website_sources = Counter(
            str(row["evidence_source"]) for row in source_websites
        )

        result[source] = SourceProvenanceMetrics(
            source=source,
            jobs=jobs,
            companies=companies,
            identifier_observations=sum(
                int(row["observation_count"] or 0) for row in source_identifiers
            ),
            identifiers=len(source_identifiers),
            companies_with_identifiers=len(identifier_companies),
            identifier_company_rate=_ratio(len(identifier_companies), companies),
            identifier_kinds=dict(sorted(identifier_kinds.items())),
            identifier_evidence_sources=dict(sorted(identifier_sources.items())),
            website_candidate_observations=sum(
                int(row["observation_count"] or 0) for row in source_websites
            ),
            website_candidates=len(source_websites),
            companies_with_website_candidates=len(website_companies),
            website_candidate_company_rate=_ratio(len(website_companies), companies),
            website_evidence_sources=dict(sorted(website_sources.items())),
        )

    return result


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
