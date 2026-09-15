import json
from pathlib import Path

from agregator.benchmark_preflight import build_benchmark_preflight
from agregator.collection_workspace import run_collection_workspace
from agregator.models import JobPosting
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.storage import SQLiteStore


class FakeSource:
    name = "fixture"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        if cursor is not None:
            return SourceBatch(jobs=[], next_cursor=None)
        return SourceBatch(
            jobs=[
                JobPosting(
                    source="fixture",
                    source_id="1",
                    url="https://jobs.test/1",
                    title="Magazynier",
                    company_name="ACME Logistics",
                    company_name_source="fixture.company",
                    company_name_confidence=0.99,
                    city="Gdańsk",
                )
            ],
            next_cursor=None,
        )


async def test_collection_workspace_runs_without_search_provider(tmp_path: Path) -> None:
    registry = SourceRegistry()
    registry.register("fixture", FakeSource, access_mode="fixture")
    preflight = build_benchmark_preflight(
        registry,
        ["fixture"],
        search_provider_ready=False,
        require_search_provider=False,
    )
    assert preflight.ready is True
    assert preflight.search_provider_required is False
    assert preflight.search_provider_ready is False

    result = await run_collection_workspace(
        SQLiteStore(tmp_path / "collection.sqlite3"),
        registry,
        ["fixture"],
        tmp_path / "workspace",
        preflight=preflight,
        target_jobs=1,
        max_rounds=2,
    )

    assert result.collection.target_reached is True
    assert result.collection.jobs_after == 1
    assert result.benchmark.jobs_total == 1
    assert result.benchmark.source_identity_metrics["fixture"]["jobs"] == 1
    assert result.dataset.to_dict()["schema_version"] == "8"
    assert result.collection_path.exists()
    assert result.benchmark_report_path.exists()
    assert result.dataset.manifest_path.exists()
    assert result.run_manifest_path.exists()

    manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "collection_only"
    assert manifest["preflight"]["search_provider_required"] is False
    assert manifest["collection"]["target_reached"] is True
    assert manifest["dataset"]["schema_version"] == "8"
    assert manifest["readiness"]["ready_for_full_enrichment_benchmark"] is True
    assert manifest["readiness"]["manual_ground_truth_ready"] is False
