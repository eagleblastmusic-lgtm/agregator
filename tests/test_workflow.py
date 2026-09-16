from pathlib import Path

import pytest

from agregator.crawler import CrawlPage
from agregator.models import CompanyWebsiteCandidate, JobPosting
from agregator.pipeline import EmployerDiscoveryPipeline
from agregator.sources.base import SourceBatch
from agregator.sources.registry import SourceRegistry
from agregator.storage import SQLiteStore
from agregator.workflow import (
    resolve_workflow_sources,
    run_collection_workflow,
    run_end_to_end_workflow,
    run_enrichment_workflow,
)


class FakeSource:
    name = "publictest"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        if cursor == "done":
            return SourceBatch(jobs=[], next_cursor="done")
        return SourceBatch(
            jobs=[
                JobPosting(
                    source=self.name,
                    source_id="job-1",
                    url="https://jobs.test/job-1",
                    title="Pracownik",
                    company_name="ACME Logistics Sp. z o.o.",
                    company_name_source="publictest.company",
                    company_name_confidence=0.99,
                    company_website_candidates=[
                        CompanyWebsiteCandidate(
                            url="https://acme-logistics.test",
                            source="publictest.website",
                            confidence=0.98,
                        )
                    ],
                    city="Gdańsk",
                )
            ],
            next_cursor="done",
        )


class FakePartnerSource:
    name = "partnerfake"

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        return SourceBatch(jobs=[], next_cursor=None)


class FakeCrawler:
    async def crawl(self, start_url: str) -> list[CrawlPage]:
        if start_url != "https://acme-logistics.test":
            return []
        return [
            CrawlPage(
                url=start_url,
                status_code=200,
                html="""
                <html><body>
                  <h1>ACME Logistics Sp. z o.o.</h1>
                  <p>Siedziba: Gdańsk.</p>
                  <p>Kontakt dla partnerów biznesowych:
                     partnerzy@acme-logistics.test</p>
                </body></html>
                """,
            )
        ]


def _registry_with_optional_partner() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("publictest", FakeSource, access_mode="public_html")
    registry.register(
        "partnerfake",
        FakePartnerSource,
        access_mode="partner_api",
        required_env=("PARTNER_API_KEY",),
    )
    return registry


def test_source_resolution_skips_missing_partner_credentials() -> None:
    requested, selected, skipped = resolve_workflow_sources(
        _registry_with_optional_partner(),
        "all",
        environment={},
    )

    assert requested == ["partnerfake", "publictest"]
    assert selected == ["publictest"]
    assert skipped == [
        {
            "source": "partnerfake",
            "status": "skipped",
            "reason": "missing_required_environment",
            "missing_env": ["PARTNER_API_KEY"],
            "access_mode": "partner_api",
        }
    ]


def test_source_resolution_enables_configured_partner() -> None:
    _, selected, skipped = resolve_workflow_sources(
        _registry_with_optional_partner(),
        "all",
        environment={"PARTNER_API_KEY": "configured"},
    )

    assert selected == ["partnerfake", "publictest"]
    assert skipped == []


def test_source_resolution_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Nieznane źródła"):
        resolve_workflow_sources(
            _registry_with_optional_partner(),
            "does-not-exist",
            environment={},
        )


@pytest.mark.asyncio
async def test_collection_and_enrichment_are_independent_stages(tmp_path: Path) -> None:
    registry = SourceRegistry()
    registry.register("publictest", FakeSource, access_mode="public_html")
    db = tmp_path / "workflow.sqlite3"
    output = tmp_path / "faro_firmy_kontakt.xlsx"

    collection = await run_collection_workflow(
        db=str(db),
        sources="all",
        pages_per_source=1,
        registry=registry,
        environment={},
    )

    assert collection.status == "success"
    assert collection.successful_sources == ["publictest"]
    assert collection.source_results[0]["jobs_inserted"] == 1
    assert not output.exists()

    store = SQLiteStore(str(db))
    assert len(store.companies_for_enrichment(limit=10, min_identity_confidence=0.7)) == 1

    pipeline = EmployerDiscoveryPipeline(
        crawler=FakeCrawler(),  # type: ignore[arg-type]
        search_provider=None,
    )
    enrichment = await run_enrichment_workflow(
        db=str(db),
        output=str(output),
        pipeline=pipeline,
        enrichment_limit=10,
    )

    assert enrichment.status == "success"
    assert enrichment.enrichment["enriched"] == 1
    assert enrichment.enrichment["websites_found"] == 1
    assert enrichment.enrichment["green_channels"] == 1
    assert enrichment.export["companies"] == 1
    assert output.exists()


@pytest.mark.asyncio
async def test_end_to_end_workflow_collects_enriches_and_exports(tmp_path: Path) -> None:
    registry = SourceRegistry()
    registry.register("publictest", FakeSource, access_mode="public_html")
    db = tmp_path / "workflow.sqlite3"
    output = tmp_path / "faro_firmy_kontakt.xlsx"
    pipeline = EmployerDiscoveryPipeline(
        crawler=FakeCrawler(),  # type: ignore[arg-type]
        search_provider=None,
    )

    result = await run_end_to_end_workflow(
        db=str(db),
        output=str(output),
        pipeline=pipeline,
        sources="all",
        pages_per_source=1,
        enrichment_limit=10,
        registry=registry,
        environment={},
    )

    assert result.status == "success"
    assert result.successful_sources == ["publictest"]
    assert result.failed_sources == []
    assert result.source_results[0]["jobs_inserted"] == 1
    assert result.enrichment["enriched"] == 1
    assert result.enrichment["websites_found"] == 1
    assert result.enrichment["green_channels"] == 1
    assert result.enrichment["search_skipped"] == 0
    assert result.export["companies"] == 1
    assert Path(result.output).exists()

    resumed = await run_end_to_end_workflow(
        db=str(db),
        output=str(output),
        pipeline=pipeline,
        sources="all",
        pages_per_source=1,
        enrichment_limit=10,
        registry=registry,
        environment={},
    )

    assert resumed.status == "success"
    assert resumed.source_results[0]["jobs_seen"] == 0
    assert resumed.enrichment["candidates"] == 0
    assert resumed.export["companies"] == 1
