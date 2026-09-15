from __future__ import annotations

from dataclasses import dataclass

from .audit import record_discovery_audit
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
            result = await pipeline.discover(
                str(company["canonical_name"]),
                str(company["city"]) if company["city"] else None,
            )
            company_id = int(company["id"])
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
