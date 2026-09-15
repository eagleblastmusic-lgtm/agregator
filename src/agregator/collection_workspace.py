from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .benchmark_preflight import BenchmarkPreflight
from .benchmark_runner import BenchmarkCollectionResult, collect_benchmark
from .dataset_export import DatasetExportResult, export_dataset_bundle
from .reporting import BenchmarkReport, build_benchmark_report
from .sources.registry import SourceRegistry
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class CollectionWorkspaceResult:
    output_dir: Path
    collection_path: Path
    benchmark_report_path: Path
    run_manifest_path: Path
    collection: BenchmarkCollectionResult
    benchmark: BenchmarkReport
    dataset: DatasetExportResult
    preflight: BenchmarkPreflight

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "collection_path": str(self.collection_path),
            "benchmark_report_path": str(self.benchmark_report_path),
            "run_manifest_path": str(self.run_manifest_path),
            "collection": self.collection.to_dict(),
            "benchmark": self.benchmark.to_dict(),
            "dataset": self.dataset.to_dict(),
            "preflight": self.preflight.to_dict(),
        }


async def run_collection_workspace(
    store: SQLiteStore,
    registry: SourceRegistry,
    source_names: list[str],
    output_dir: str | Path,
    *,
    preflight: BenchmarkPreflight,
    target_jobs: int = 100,
    max_rounds: int = 20,
    max_errors_per_source: int = 3,
    fresh_collection: bool = False,
    fail_fast_collection: bool = False,
) -> CollectionWorkspaceResult:
    """Collect source data without website enrichment or a search-provider dependency."""

    if not preflight.ready:
        blockers = ", ".join(preflight.blockers) or "unknown"
        raise ValueError(f"collection preflight blockers: {blockers}")
    if preflight.search_provider_required:
        raise ValueError("collection workspace requires search_provider_required=false")

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    collection_path = directory / "collection.json"
    benchmark_report_path = directory / "benchmark_report.json"
    run_manifest_path = directory / "collection_run_manifest.json"

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
    benchmark = build_benchmark_report(store)
    dataset = export_dataset_bundle(store, directory / "dataset")

    _write_json(collection_path, collection.to_dict())
    _write_json(benchmark_report_path, benchmark.to_dict())
    manifest = {
        "schema_version": "1",
        "mode": "collection_only",
        "created_at": datetime.now(UTC).isoformat(),
        "database": str(store.path),
        "configuration": {
            "sources": [name.strip().lower() for name in source_names if name.strip()],
            "target_jobs": target_jobs,
            "max_rounds": max_rounds,
            "max_errors_per_source": max_errors_per_source,
            "fresh_collection": fresh_collection,
            "fail_fast_collection": fail_fast_collection,
        },
        "preflight": preflight.to_dict(),
        "collection": collection.to_dict(),
        "benchmark": benchmark.to_dict(),
        "dataset": dataset.to_dict(),
        "readiness": {
            "collection_target_reached": collection.target_reached,
            "ready_for_full_enrichment_benchmark": collection.target_reached,
            "manual_ground_truth_ready": False,
            "reason": (
                "collection-only workspace intentionally skips website/contact enrichment"
            ),
        },
        "files": {
            "collection": collection_path.name,
            "benchmark_report": benchmark_report_path.name,
            "dataset_dir": "dataset",
        },
    }
    _write_json(run_manifest_path, manifest)

    return CollectionWorkspaceResult(
        output_dir=directory,
        collection_path=collection_path,
        benchmark_report_path=benchmark_report_path,
        run_manifest_path=run_manifest_path,
        collection=collection,
        benchmark=benchmark,
        dataset=dataset,
        preflight=preflight,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
