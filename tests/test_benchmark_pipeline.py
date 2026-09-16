import csv
import json
from pathlib import Path

import pytest

from agregator.benchmark_pipeline import run_benchmark_pipeline
from agregator.crawler import CrawlPage
from agregator.models import JobPosting, SearchCandidate
from agregator.pipeline import EmployerDiscoveryPipeline
from agregator.search import StaticSearchProvider
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.storage import SQLiteStore


class FakeSource:
    name = "fixture"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        if cursor is not None:
            return SourceBatch(jobs=[], next_cursor=None)
        jobs = [
            JobPosting(
                source=self.name,
                source_id=str(index),
                url=f"https://jobs.test/{index}",
                title=f"Magazynier {index}",
                company_name="ACME Logistics Sp. z o.o.",
                company_name_source="fixture.company",
                company_name_confidence=0.99,
                city="Gdańsk",
            )
            for index in range(2)
        ]
        return SourceBatch(jobs=jobs, next_cursor=None)


class FakeCrawler:
    def __init__(self, url: str) -> None:
        self.url = url
        self.calls: list[str] = []

    async def crawl(self, start_url: str) -> list[CrawlPage]:
        self.calls.append(start_url)
        if start_url != self.url:
            return []
        return [
            CrawlPage(
                url=self.url,
                status_code=200,
                html="""
                <html><body>
                  <h1>ACME Logistics Sp. z o.o.</h1>
                  <p>Siedziba firmy: Gdańsk.</p>
                  <p>Kontakt dla partnerów: partnerzy@acme-logistics.test</p>
                </body></html>
                """,
            )
        ]


class ExplodingPipeline:
    async def discover(self, company_name: str, city: str | None = None) -> object:
        raise RuntimeError("temporary search failure")


def _fields(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle).fieldnames or [])


async def test_benchmark_pipeline_collects_enriches_and_exports_workspace(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "benchmark.sqlite3")
    registry = SourceRegistry()
    registry.register("fixture", FakeSource)

    official_url = "https://acme-logistics.test"
    crawler = FakeCrawler(official_url)
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=StaticSearchProvider(
            [
                SearchCandidate(
                    title="ACME Logistics Gdańsk oficjalna",
                    url=official_url,
                    snippet="ACME Logistics Sp. z o.o. Gdańsk kontakt",
                )
            ]
        ),
    )

    result = await run_benchmark_pipeline(
        store,
        registry,
        pipeline,
        ["fixture"],
        tmp_path / "workspace",
        target_jobs=2,
        max_rounds=5,
        enrichment_batch_size=10,
        max_enrichment_companies=10,
        label_sampling_seed="benchmark-test-seed",
    )

    assert result.collection.target_reached is True
    assert result.collection.jobs_after == 2
    assert result.enrichment.enriched == 1
    assert result.enrichment.websites_found == 1
    assert result.enrichment.evidence_snapshots == 1
    assert result.enrichment.evidence_observations == 1
    assert result.enrichment.evidence_changes == 0
    assert result.enrichment.stopped_reason == "no_pending_companies"
    assert result.benchmark.jobs_total == 2
    assert result.benchmark.companies_total == 1
    assert result.benchmark.websites_found == 1
    assert result.benchmark.green_channels == 1
    assert result.readiness.collection_target_reached is True
    assert result.readiness.enrichment_complete is True
    assert result.readiness.ready_for_manual_labeling is True
    assert result.readiness.manual_ground_truth_required is True
    assert result.readiness.blockers == ()
    assert crawler.calls == [official_url]

    assert result.collection_path.exists()
    assert result.enrichment_path.exists()
    assert result.benchmark_report_path.exists()
    assert result.run_manifest_path.exists()
    assert result.dataset.manifest_path.exists()
    assert result.dataset.identifier_observations_path.exists()
    assert result.dataset.website_candidate_observations_path.exists()
    assert result.dataset.evidence_observations_path.exists()
    assert result.website_snapshots.path.exists()
    assert result.website_snapshots.rows == 1
    assert result.website_snapshots.parse_errors == 0
    assert result.quality_labels.company_resolution_path.exists()
    assert result.quality_labels.website_resolution_path.exists()
    assert result.quality_labels.contact_classification_path.exists()
    assert result.quality_labels.sampling_manifest_path.exists()
    assert result.quality_labels.prediction_reference_dir.exists()
    assert result.quality_labels.company_resolution_reference_path.exists()
    assert result.quality_labels.website_resolution_reference_path.exists()
    assert result.quality_labels.contact_classification_reference_path.exists()

    assert "predicted_company_id" not in _fields(
        result.quality_labels.company_resolution_path
    )
    assert "predicted_company_id" in _fields(
        result.quality_labels.company_resolution_reference_path
    )
    assert "predicted_website_url" not in _fields(
        result.quality_labels.website_resolution_path
    )
    assert "predicted_decision" not in _fields(
        result.quality_labels.contact_classification_path
    )

    sampling_manifest = json.loads(
        result.quality_labels.sampling_manifest_path.read_text(encoding="utf-8")
    )
    assert sampling_manifest["seed"] == "benchmark-test-seed"
    assert sampling_manifest["files"][0]["population_rows"] == 2

    manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "5"
    assert manifest["configuration"]["label_sampling_seed"] == "benchmark-test-seed"
    assert manifest["collection"]["target_reached"] is True
    assert manifest["enrichment"]["enriched"] == 1
    assert manifest["enrichment"]["evidence_observations"] == 1
    assert manifest["benchmark"]["websites_found"] == 1
    assert manifest["website_snapshots"]["rows"] == 1
    assert manifest["dataset"]["schema_version"] == "8"
    assert manifest["dataset"]["identifier_observations"] == 0
    assert manifest["dataset"]["website_candidate_observations"] == 0
    assert manifest["dataset"]["evidence_observations"] == 1
    assert manifest["readiness"]["ready_for_manual_labeling"] is True
    assert manifest["readiness"]["blockers"] == []
    assert manifest["files"]["dataset_dir"] == "dataset"
    assert manifest["files"]["website_page_snapshots"] == (
        "dataset/website_page_snapshots.csv"
    )
    assert manifest["files"]["labels_dir"] == "labels"
    assert manifest["files"]["label_sampling_manifest"] == (
        "labels/sampling_manifest.json"
    )
    assert manifest["files"]["prediction_reference_dir"] == (
        "labels/prediction_reference"
    )
    assert manifest["files"]["company_resolution_reference"] == (
        "labels/prediction_reference/company_resolution_reference.csv"
    )
    assert manifest["files"]["website_resolution_reference"] == (
        "labels/prediction_reference/website_resolution_reference.csv"
    )
    assert manifest["files"]["contact_classification_reference"] == (
        "labels/prediction_reference/contact_classification_reference.csv"
    )


async def test_benchmark_pipeline_stops_after_all_failed_enrichment_batch(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "failed.sqlite3")
    store.init_schema()
    store.upsert_jobs(
        [
            JobPosting(
                source="fixture",
                source_id="1",
                url="https://jobs.test/1",
                title="Pracownik",
                company_name="Failure Company",
                company_name_source="fixture.company",
                company_name_confidence=0.99,
                city="Gdynia",
            )
        ]
    )
    registry = SourceRegistry()
    registry.register("fixture", FakeSource)

    result = await run_benchmark_pipeline(
        store,
        registry,
        ExplodingPipeline(),  # type: ignore[arg-type]
        ["fixture"],
        tmp_path / "workspace-failed",
        target_jobs=1,
        enrichment_batch_size=5,
        max_enrichment_companies=100,
    )

    assert result.collection.stopped_reason == "target_already_reached"
    assert result.enrichment.batches == 1
    assert result.enrichment.candidates == 1
    assert result.enrichment.enriched == 0
    assert result.enrichment.failed == 1
    assert result.enrichment.evidence_observations == 0
    assert result.enrichment.evidence_changes == 0
    assert result.enrichment.stopped_reason == "batch_all_failed"
    assert result.website_snapshots.rows == 0
    assert result.readiness.collection_target_reached is True
    assert result.readiness.enrichment_complete is False
    assert result.readiness.ready_for_manual_labeling is False
    assert result.readiness.blockers == ("enrichment_incomplete:batch_all_failed",)
    assert result.run_manifest_path.exists()


async def test_benchmark_pipeline_rejects_empty_label_sampling_seed(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "seed.sqlite3")
    registry = SourceRegistry()
    registry.register("fixture", FakeSource)

    with pytest.raises(ValueError, match="label_sampling_seed"):
        await run_benchmark_pipeline(
            store,
            registry,
            ExplodingPipeline(),  # type: ignore[arg-type]
            ["fixture"],
            tmp_path / "workspace-seed",
            label_sampling_seed="   ",
        )
