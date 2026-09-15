from __future__ import annotations

from dataclasses import dataclass

from .audit import record_discovery_audit
from .company_websites import list_company_website_candidates
from .models import DiscoveryResult, WebsiteVerificationAttempt
from .pipeline import EmployerDiscoveryPipeline
from .storage import SQLiteStore


@dataclass(slots=True)
class EnrichmentStats:
    candidates: int = 0
    enriched: int = 0
    websites_found: int = 0
    channels_found: int = 0
    green_channels: int = 0
    evidence_snapshots: int = 0
    source_website_candidates_checked: int = 0
    source_website_candidates_verified: int = 0
    search_fallbacks: int = 0
    failed: int = 0


async def enrich_pending_companies(
    store: SQLiteStore,
    pipeline: EmployerDiscoveryPipeline,
    *,
    limit: int = 20,
    min_identity_confidence: float = 0.7,
    refresh: bool = False,
) -> EnrichmentStats:
    store.init_schema()
    candidates = store.companies_for_enrichment(
        limit=limit,
        min_identity_confidence=min_identity_confidence,
        refresh=refresh,
    )
    stats = EnrichmentStats(candidates=len(candidates))

    for company in candidates:
        try:
            company_id = int(company["id"])
            company_name = str(company["canonical_name"])
            city = str(company["city"]) if company["city"] else None
            result = await _discover_company(
                store,
                pipeline,
                company_id,
                company_name,
                city,
                stats,
            )
            store.save_discovery_result(company_id, result)
            audit_stats = record_discovery_audit(store, company_id, result)
        except Exception:
            stats.failed += 1
            continue

        stats.enriched += 1
        stats.evidence_snapshots += audit_stats.evidence_snapshots_recorded
        if result.company.website_url:
            stats.websites_found += 1
        stats.channels_found += len(result.channels)
        stats.green_channels += sum(
            1 for channel in result.channels if channel.decision.value == "green"
        )

    return stats


async def _discover_company(
    store: SQLiteStore,
    pipeline: EmployerDiscoveryPipeline,
    company_id: int,
    company_name: str,
    city: str | None,
    stats: EnrichmentStats,
) -> DiscoveryResult:
    source_attempts: list[WebsiteVerificationAttempt] = []
    source_candidates = list_company_website_candidates(store, company_id, limit=3)

    for candidate in source_candidates:
        stats.source_website_candidates_checked += 1
        source = str(candidate.get("source") or "source")
        try:
            result = await pipeline.verify_website_candidate(
                company_name,
                str(candidate["url"]),
                city,
                candidate_confidence=float(candidate["confidence"]),
                source_signal=f"source_website_candidate:{source}",
            )
        except Exception:
            continue

        source_attempts.extend(result.website_attempts)
        if result.company.website_url:
            stats.source_website_candidates_verified += 1
            return result

    stats.search_fallbacks += 1
    result = await pipeline.discover(company_name, city)
    if not source_attempts:
        return result

    return result.model_copy(
        update={"website_attempts": [*source_attempts, *result.website_attempts]}
    )
