from pathlib import Path

import pytest

from agregator.cli import _optional_search_provider
from agregator.company_websites import persist_job_company_website_candidates
from agregator.crawler import CrawlPage
from agregator.enrich import enrich_pending_companies
from agregator.models import CompanyWebsiteCandidate, JobPosting
from agregator.pipeline import EmployerDiscoveryPipeline
from agregator.storage import SQLiteStore


class FakeCrawler:
    def __init__(self, pages_by_url: dict[str, list[CrawlPage]]) -> None:
        self.pages_by_url = pages_by_url
        self.calls: list[str] = []

    async def crawl(self, start_url: str) -> list[CrawlPage]:
        self.calls.append(start_url)
        return self.pages_by_url.get(start_url, [])


def _page(url: str, html: str) -> CrawlPage:
    return CrawlPage(url=url, html=html, status_code=200)


def _seed_company(
    store: SQLiteStore,
    *,
    candidate_url: str | None,
    source_id: str = "1",
) -> int:
    store.init_schema()
    candidates = []
    if candidate_url is not None:
        candidates.append(
            CompanyWebsiteCandidate(
                url=candidate_url,
                source="job_source.employer_website",
                confidence=0.98,
            )
        )

    job = JobPosting(
        source="testjobs",
        source_id=source_id,
        url=f"https://jobs.test/{source_id}",
        title="Pracownik",
        company_name="ACME Logistics Sp. z o.o.",
        company_name_source="job_source.company",
        company_name_confidence=0.995,
        company_website_candidates=candidates,
        city="Gdańsk",
    )
    store.upsert_jobs([job])
    persist_job_company_website_candidates(store, [job])
    return int(store.list_companies()[0]["id"])


def test_optional_search_provider_is_none_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    assert _optional_search_provider() is None


@pytest.mark.asyncio
async def test_source_candidate_can_enrich_without_search_provider(tmp_path: Path) -> None:
    source_url = "https://acme-logistics.test"
    store = SQLiteStore(tmp_path / "source-only.sqlite3")
    _seed_company(store, candidate_url=source_url)
    crawler = FakeCrawler(
        {
            source_url: [
                _page(
                    source_url,
                    """
                    <html><body>
                      <h1>ACME Logistics Sp. z o.o.</h1>
                      <p>Siedziba: Gdańsk.</p>
                      <p>Propozycje współpracy: wspolpraca@acme-logistics.test</p>
                    </body></html>
                    """,
                )
            ]
        }
    )
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=None,
    )

    stats = await enrich_pending_companies(store, pipeline, limit=1)

    assert stats.enriched == 1
    assert stats.failed == 0
    assert stats.websites_found == 1
    assert stats.green_channels == 1
    assert stats.source_website_candidates_checked == 1
    assert stats.source_website_candidates_verified == 1
    assert stats.search_fallbacks == 0
    assert stats.search_skipped == 0
    assert crawler.calls == [source_url]


@pytest.mark.asyncio
async def test_missing_search_provider_is_reported_without_failed_company(tmp_path: Path) -> None:
    wrong_url = "https://wrong-company.test"
    store = SQLiteStore(tmp_path / "no-search-fallback.sqlite3")
    _seed_company(store, candidate_url=wrong_url)
    crawler = FakeCrawler(
        {
            wrong_url: [
                _page(
                    wrong_url,
                    "<html><body><h1>Completely Different Company</h1><p>Warszawa</p></body></html>",
                )
            ]
        }
    )
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=None,
    )

    stats = await enrich_pending_companies(store, pipeline, limit=1)

    assert stats.enriched == 1
    assert stats.failed == 0
    assert stats.websites_found == 0
    assert stats.source_website_candidates_checked == 1
    assert stats.source_website_candidates_verified == 0
    assert stats.search_fallbacks == 0
    assert stats.search_skipped == 1
    assert crawler.calls == [wrong_url]

    with store.connect() as connection:
        run = connection.execute(
            """
            SELECT website_url, verification_signals_json, website_attempts_json
            FROM website_verification_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert run is not None
    assert run["website_url"] is None
    assert "search_provider_unavailable" in run["verification_signals_json"]
    assert wrong_url in run["website_attempts_json"]


@pytest.mark.asyncio
async def test_company_without_source_website_is_skipped_not_failed_without_search(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "no-source-no-search.sqlite3")
    _seed_company(store, candidate_url=None)
    crawler = FakeCrawler({})
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=None,
    )

    stats = await enrich_pending_companies(store, pipeline, limit=1)

    assert stats.enriched == 1
    assert stats.failed == 0
    assert stats.websites_found == 0
    assert stats.source_website_candidates_checked == 0
    assert stats.search_fallbacks == 0
    assert stats.search_skipped == 1
    assert crawler.calls == []
