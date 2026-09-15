from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .audit_export import WebsiteSnapshotExportResult
from .benchmark_runner import BenchmarkCollectionResult, collect_benchmark
from .dataset_export import DatasetExportResult, export_dataset_bundle
from .enrich import EnrichmentStats, enrich_pending_companies
from .pipeline import EmployerDiscoveryPipeline
from .quality_labels import QualityLabelBundle, export_quality_label_bundle
from .reporting import BenchmarkReport, build_benchmark_report
from .sources.registry import SourceRegistry
from .storage import SQLiteStore


@dataclass(slots=True)
class BenchmarkEnrichmentSummary:
    batches: int = 0
    candidates: int = 0
    enriched: int = 0
    websites_found: int = 0
    channels_found: int = 0
    green_channels: int = 0
    evidence_snapshots: int = 0
    evidence_observations: int = 0
    evidence_changes: int = 0
    source_website_candidates_checked: int = 0
    source_website_candidates_verified: int = 0
    search_fallbacks: int = 0
    failed: int = 0
    stopped_reason: str = "not_started"

    def add(self, stats: EnrichmentStats) -> None:
        self.batches += 1
        self.candidates += stats.candidates
        self.enriched += stats.enriched
        self.websites_found += stats.websites_found
        self.channels_found += stats.channels_found
        self.green_channels += stats.green_channels
        self.evidence_snapshots += stats.evidence_snapshots
        self.evidence_observations += stats.evidence_observations
        self.evidence_changes += stats.evidence_changes
        self.source_website_candidates_checked += stats.source_website_candidates_checked
        self.source_website_candidates_verified += stats.source_website_candidates_verified
        self.search_fallbacks += stats.search_fallbacks
        self.failed += stats.failed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkReadiness:
    collection_target_reached: bool
    enrichment_complete: bool
    dataset_exported: bool
    ground_truth_templates_generated: bool
    ready_for_manual_labeling: bool
    manual_ground_truth_required: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True, slots=True)
class BenchmarkPipelineResult:
    output_dir: Path
    collection_path: Path
    enrichment_path: Path
    benchmark_report_path: Path
    run_manifest_path: Path
    collection: BenchmarkCollectionResult
    enrichment: BenchmarkEnrichmentSummary
    benchmark: BenchmarkReport
    dataset: DatasetExportResult
    website_snapshots: WebsiteSnapshotExportResult
    quality_labels: QualityLabelBundle
    readiness: BenchmarkReadiness

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "collection_path": str(self.collection_path),
            "enrichment_path": str(self.enrichment_path),
            "benchmark_report_path": str(self.benchmark_report_path),
            "run_manifest_path": str(self.run_manifest_path),
            "collection": self.collection.to_dict(),
            "enrichment": self.enrichment.to_dict(),
            "benchmark": self.benchmark.to_dict(),
            "dataset": self.dataset.to_dict(),
            "website_snapshots": self.website_snapshots.to_dict(),
            "quality_labels": self.quality_labels.to_dict(),
            "readiness": self.readiness.to_dict(),
        }


async def run_benchmark_pipeline(
    store: SQLiteStore,
    registry: SourceRegistry,
    pipeline: EmployerDiscoveryPipeline,
    source_names: list[str],
    output_dir: str | Path,
    *,
    target_jobs: int = 1000,
    max_rounds: int = 100,
    max_errors_per_source: int = 3,
    fresh_collection: bool = False,
    fail_fast_collection: bool = False,
    enrichment_batch_size: int = 25,
    max_enrichment_companies: int = 1000,
    min_identity_confidence: float = 0.7,
    job_label_limit: int = 1000,
    company_label_limit: int = 1000,
    contact_label_limit: int = 1000,
) -> BenchmarkPipelineResult:
    """Run the reproducible Faro benchmark workflow from collection to label bundle.

    The workflow deliberately keeps collection, enrichment, reporting and manual-label
    exports separate in the output directory. It never sends outreach. Failed enrichment
    rows remain pending in the database, but a batch where every selected company fails
    stops the run so one persistent failure cannot create an infinite retry loop.
    """

    if enrichment_batch_size < 1:
        raise ValueError("enrichment_batch_size must be >= 1")
    if max_enrichment_companies < 1:
        raise ValueError("max_enrichment_companies must be >= 1")
    if not 0.0 <= min_identity_confidence <= 1.0:
        raise ValueError("min_identity_confidence must be between 0 and 1")

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    collection_path = directory / "collection.json"
    enrichment_path = directory / "enrichment.json"
    benchmark_report_path = directory / "benchmark_report.json"
    run_manifest_path = directory / "benchmark_run_manifest.json"

    collection = await collect_benchmark(
        store,
        registry,
        source_names,
        target_jobs=target_jobs,
        max_rounds=max_rounds,
        max_errors_per_source=max_errors_per_source,
        fresh=fresh_collection,
        fail_fast=fail_fast_collection,
    )
    _write_json(collection_path, collection.to_dict())

    enrichment = await _run_enrichment_batches(
        store,
        pipeline,
        batch_size=enrichment_batch_size,
        max_companies=max_enrichment_companies,
        min_identity_confidence=min_identity_confidence,
    )
    _write_json(enrichment_path, enrichment.to_dict())

    benchmark = build_benchmark_report(store)
    _write_json(benchmark_report_path, benchmark.to_dict())

    dataset = export_dataset_bundle(store, directory / "dataset")
    website_snapshots = dataset.website_snapshots
    quality_labels = export_quality_label_bundle(
        store,
        directory / "labels",
        job_limit=job_label_limit,
        company_limit=company_label_limit,
        contact_limit=contact_label_limit,
    )
    readiness = _build_readiness(collection, enrichment)

    manifest = {
        "schema_version": "3",
        "created_at": datetime.now(UTC).isoformat(),
        "database": str(store.path),
        "configuration": {
            "sources": [name.strip().lower() for name in source_names if name.strip()],
            "target_jobs": target_jobs,
            "max_rounds": max_rounds,
            "max_errors_per_source": max_errors_per_source,
            "fresh_collection": fresh_collection,
            "fail_fast_collection": fail_fast_collection,
            "enrichment_batch_size": enrichment_batch_size,
            "max_enrichment_companies": max_enrichment_companies,
            "min_identity_confidence": min_identity_confidence,
            "job_label_limit": job_label_limit,
            "company_label_limit": company_label_limit,
            "contact_label_limit": contact_label_limit,
        },
        "collection": collection.to_dict(),
        "enrichment": enrichment.to_dict(),
        "benchmark": benchmark.to_dict(),
        "dataset": dataset.to_dict(),
        "website_snapshots": website_snapshots.to_dict(),
        "quality_labels": quality_labels.to_dict(),
        "readiness": readiness.to_dict(),
        "files": {
            "collection": collection_path.name,
            "enrichment": enrichment_path.name,
            "benchmark_report": benchmark_report_path.name,
            "dataset_dir": "dataset",
            "website_page_snapshots": "dataset/website_page_snapshots.csv",
            "labels_dir": "labels",
        },
    }
    _write_json(run_manifest_path, manifest)

    return BenchmarkPipelineResult(
        output_dir=directory,
        collection_path=collection_path,
        enrichment_path=enrichment_path,
        benchmark_report_path=benchmark_report_path,
        run_manifest_path=run_manifest_path,
        collection=collection,
        enrichment=enrichment,
        benchmark=benchmark,
        dataset=dataset,
        website_snapshots=website_snapshots,
        quality_labels=quality_labels,
        readiness=readiness,
    )


async def _run_enrichment_batches(
    store: SQLiteStore,
    pipeline: EmployerDiscoveryPipeline,
    *,
    batch_size: int,
    max_companies: int,
    min_identity_confidence: float,
) -> BenchmarkEnrichmentSummary:
    summary = BenchmarkEnrichmentSummary()
    remaining = max_companies

    while remaining > 0:
        limit = min(batch_size, remaining)
        stats = await enrich_pending_companies(
            store,
            pipeline,
            limit=limit,
            min_identity_confidence=min_identity_confidence,
            refresh=False,
        )
        summary.add(stats)

        if stats.candidates == 0:
            summary.stopped_reason = "no_pending_companies"
            break

        remaining -= stats.candidates
        if stats.enriched == 0 and stats.failed > 0:
            summary.stopped_reason = "batch_all_failed"
            break
    else:
        summary.stopped_reason = "max_enrichment_companies"

    if remaining <= 0 and summary.stopped_reason == "not_started":
        summary.stopped_reason = "max_enrichment_companies"

    return summary


def _build_readiness(
    collection: BenchmarkCollectionResult,
    enrichment: BenchmarkEnrichmentSummary,
) -> BenchmarkReadiness:
    blockers: list[str] = []
    if not collection.target_reached:
        blockers.append("collection_target_not_reached")
    enrichment_complete = enrichment.stopped_reason == "no_pending_companies"
    if not enrichment_complete:
        blockers.append(f"enrichment_incomplete:{enrichment.stopped_reason}")

    return BenchmarkReadiness(
        collection_target_reached=collection.target_reached,
        enrichment_complete=enrichment_complete,
        dataset_exported=True,
        ground_truth_templates_generated=True,
        ready_for_manual_labeling=not blockers,
        manual_ground_truth_required=True,
        blockers=tuple(blockers),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
