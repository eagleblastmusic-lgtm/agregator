import json
from pathlib import Path

import pytest

from agregator.company_websites import persist_job_company_website_candidates
from agregator.crawler import CrawlPage
from agregator.enrich import enrich_pending_companies
from agregator.models import (
    CompanyWebsiteCandidate,
    JobPosting,
    SearchCandidate,
    WebsiteResolutionOrigin,
)
from agregator.pipeline import EmployerDiscoveryPipeline
from agregator.search import StaticSearchProvider
from agregator.storage import SQLiteStore


class FakeCrawler:
    def __init__(self, pages_by_url: dict[str, list[CrawlPage]]) -> None:
        self.pages_by_url = pages_by_url
        self.calls: list[str] = []

    async def crawl(self, start_url: str) -> list[CrawlPage]:
        self.calls.append(start_url)
        return self.pages_by_url.get(start_url, [])


class ExplodingSearchProvider:
    async def search_company(
        self,
        company_name: str,
        city: str | None = None,
    ) -> list[SearchCandidate]:
        raise AssertionError("search provider should not be called")


def _page(url: str, html: str) -> CrawlPage:
    return CrawlPage(url=url, html=html, status_code=200)


def _seed_company(store: SQLiteStore, candidate_url: str) -> int:
    store.init_schema()
    job = JobPosting(
        source="epraca",
        source_id="1",
        url="https://jobs.test/1",
        title="Pracownik",
        company_name="ACME Logistics Sp. z o.o.",
        company_name_source="official_feed.pracodawca",
        company_name_confidence=0.995,
        company_website_candidates=[
            CompanyWebsiteCandidate(
                url=candidate_url,
                source="official_feed.adresWww",
                confidence=0.98,
            )
        ],
        city="Gdańsk",
    )
    store.upsert_jobs([job])
    persist_job_company_website_candidates(store, [job])
    return int(store.list_companies()[0]["id"])


@pytest.mark.asyncio
async def test_enrichment_uses_verified_source_website_without_search(tmp_path: Path) -> None:
    source_url = "https://acme-logistics.test"
    store = SQLiteStore(tmp_path / "source-candidate.sqlite3")
    company_id = _seed_company(store, source_url)
    crawler = FakeCrawler(
        {
            source_url: [
                _page(
                    source_url,
                    """
                    <html><body>
                      <h1>ACME Logistics Sp. z o.o.</h1>
                      <p>Siedziba: Gdańsk.</p>
                      <p>Kontakt dla partnerów: partnerzy@acme-logistics.test</p>
                    </body></html>
                    """,
                )
            ]
        }
    )
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=ExplodingSearchProvider(),  # type: ignore[arg-type]
    )

    stats = await enrich_pending_companies(store, pipeline, limit=1)

    assert stats.enriched == 1
    assert stats.websites_found == 1
    assert stats.source_website_candidates_checked == 1
    assert stats.source_website_candidates_verified == 1
    assert stats.search_fallbacks == 0
    assert crawler.calls == [source_url]
    company = store.list_companies()[0]
    assert company["website_url"] == source_url

    with store.connect() as connection:
        row = connection.execute(
            """
            SELECT resolution_origin, resolution_source, website_attempts_json
            FROM website_verification_runs
            WHERE company_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (company_id,),
        ).fetchone()

    assert row["resolution_origin"] == WebsiteResolutionOrigin.SOURCE_CANDIDATE.value
    assert row["resolution_source"] == "official_feed.adresWww"
    attempt = json.loads(row["website_attempts_json"])[0]
    assert attempt["origin"] == WebsiteResolutionOrigin.SOURCE_CANDIDATE.value
    assert attempt["source"] == "official_feed.adresWww"


@pytest.mark.asyncio
async def test_enrichment_falls_back_to_search_after_bad_source_candidate(tmp_path: Path) -> None:
    source_url = "https://wrong-company.test"
    official_url = "https://acme-logistics.test"
    store = SQLiteStore(tmp_path / "source-fallback.sqlite3")
    company_id = _seed_company(store, source_url)
    crawler = FakeCrawler(
        {
            source_url: [
                _page(
                    source_url,
                    "<html><body><h1>Inna Firma</h1><p>Warszawa</p></body></html>",
                )
            ],
            official_url: [
                _page(
                    official_url,
                    """
                    <html><body>
                      <h1>ACME Logistics Sp. z o.o.</h1>
                      <p>Siedziba firmy: Gdańsk.</p>
                    </body></html>
                    """,
                )
            ],
        }
    )
    provider = StaticSearchProvider(
        [
            SearchCandidate(
                title="ACME Logistics Gdańsk oficjalna",
                url=official_url,
                snippet="ACME Logistics Sp. z o.o. Gdańsk",
            )
        ]
    )
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=provider,
    )

    stats = await enrich_pending_companies(store, pipeline, limit=1)

    assert stats.enriched == 1
    assert stats.websites_found == 1
    assert stats.source_website_candidates_checked == 1
    assert stats.source_website_candidates_verified == 0
    assert stats.search_fallbacks == 1
    assert crawler.calls == [source_url, official_url]

    with store.connect() as connection:
        row = connection.execute(
            """
            SELECT website_url, resolution_origin, resolution_source, website_attempts_json
            FROM website_verification_runs
            WHERE company_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (company_id,),
        ).fetchone()

    assert row["website_url"] == official_url
    assert row["resolution_origin"] == WebsiteResolutionOrigin.SEARCH.value
    assert row["resolution_source"] == "static"
    attempts = json.loads(row["website_attempts_json"])
    assert len(attempts) == 2
    assert attempts[0]["url"] == source_url
    assert attempts[0]["accepted"] is False
    assert attempts[0]["origin"] == WebsiteResolutionOrigin.SOURCE_CANDIDATE.value
    assert attempts[0]["source"] == "official_feed.adresWww"
    assert attempts[1]["url"] == official_url
    assert attempts[1]["accepted"] is True
    assert attempts[1]["origin"] == WebsiteResolutionOrigin.SEARCH.value
    assert attempts[1]["source"] == "static"
