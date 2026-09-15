from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from .enrich import enrich_pending_companies
from .ingest import ingest_source
from .lead_export import export_company_leads_xlsx
from .pipeline import EmployerDiscoveryPipeline
from .source_health import build_source_health
from .sources import default_registry
from .sources.registry import SourceRegistry
from .storage import SQLiteStore


@dataclass(slots=True)
class WorkflowResult:
    db: str
    output: str
    status: str
    requested_sources: list[str] = field(default_factory=list)
    selected_sources: list[str] = field(default_factory=list)
    skipped_sources: list[dict[str, Any]] = field(default_factory=list)
    successful_sources: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)
    source_results: list[dict[str, Any]] = field(default_factory=list)
    source_health: list[dict[str, Any]] = field(default_factory=list)
    enrichment: dict[str, Any] = field(default_factory=dict)
    export: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_workflow_sources(
    registry: SourceRegistry,
    source_value: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Resolve implemented sources and skip only adapters missing required credentials."""

    env = os.environ if environment is None else environment
    requested = [item.strip().lower() for item in source_value.split(",") if item.strip()]
    if not requested or requested == ["all"]:
        requested = registry.names()
    else:
        unknown = sorted(set(requested) - set(registry.names()))
        if unknown:
            raise ValueError("Nieznane źródła: " + ", ".join(unknown))
        requested = list(dict.fromkeys(requested))

    selected: list[str] = []
    skipped: list[dict[str, Any]] = []
    for source_name in requested:
        registration = registry.describe(source_name)
        missing = [name for name in registration.required_env if not str(env.get(name, "")).strip()]
        if missing:
            skipped.append(
                {
                    "source": source_name,
                    "status": "skipped",
                    "reason": "missing_required_environment",
                    "missing_env": missing,
                    "access_mode": registration.access_mode,
                }
            )
            continue
        selected.append(source_name)

    return requested, selected, skipped


async def run_end_to_end_workflow(
    *,
    db: str,
    output: str,
    pipeline: EmployerDiscoveryPipeline,
    sources: str = "all",
    pages_per_source: int = 1,
    fresh_sources: bool = False,
    fail_fast: bool = False,
    enrichment_limit: int = 100,
    min_identity_confidence: float = 0.7,
    refresh_enrichment: bool = False,
    registry: SourceRegistry | None = None,
    environment: Mapping[str, str] | None = None,
) -> WorkflowResult:
    """Run one resumable collection -> enrichment -> lead-export slice.

    Source cursors, company `enriched_at`, source runs, evidence history and website
    verification are already persisted by the underlying components. Re-running this
    workflow therefore continues from the previous state unless the explicit refresh
    options are enabled.
    """

    registry = registry or default_registry()
    requested, selected, skipped = resolve_workflow_sources(
        registry,
        sources,
        environment=environment,
    )

    store = SQLiteStore(db)
    store.init_schema()
    source_results: list[dict[str, Any]] = []
    successful: list[str] = []
    failed: list[str] = []

    for source_name in selected:
        registration = registry.describe(source_name)
        try:
            source = registry.create(source_name)
            ingest = await ingest_source(
                source,
                store,
                pages=max(1, pages_per_source),
                resume=not fresh_sources,
            )
            successful.append(source_name)
            source_results.append(
                {
                    "source": source_name,
                    "status": "success",
                    "access_mode": registration.access_mode,
                    "experimental": registration.experimental,
                    **asdict(ingest.stats),
                    "pages": ingest.pages,
                    "next_cursor": ingest.next_cursor,
                    "run_id": ingest.run_id,
                }
            )
        except Exception as exc:
            failed.append(source_name)
            source_results.append(
                {
                    "source": source_name,
                    "status": "failed",
                    "access_mode": registration.access_mode,
                    "experimental": registration.experimental,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            )
            if fail_fast:
                break

    enrichment = await enrich_pending_companies(
        store,
        pipeline,
        limit=max(1, enrichment_limit),
        min_identity_confidence=min_identity_confidence,
        refresh=refresh_enrichment,
    )
    export = export_company_leads_xlsx(store, output)
    source_health = [item.to_dict() for item in build_source_health(store, requested)]

    return WorkflowResult(
        db=db,
        output=str(export.path),
        status="partial" if failed else "success",
        requested_sources=requested,
        selected_sources=selected,
        skipped_sources=skipped,
        successful_sources=successful,
        failed_sources=failed,
        source_results=source_results,
        source_health=source_health,
        enrichment=asdict(enrichment),
        export=export.to_dict(),
    )
