import pytest

from agregator.crawler import CrawlPage
from agregator.models import SearchCandidate, WebsiteResolutionOrigin
from agregator.pipeline import EmployerDiscoveryPipeline
from agregator.search import StaticSearchProvider


class FakeCrawler:
    def __init__(self, pages_by_url: dict[str, list[CrawlPage]]) -> None:
        self.pages_by_url = pages_by_url
        self.calls: list[str] = []

    async def crawl(self, start_url: str) -> list[CrawlPage]:
        self.calls.append(start_url)
        return self.pages_by_url.get(start_url, [])


def _page(url: str, html: str) -> CrawlPage:
    return CrawlPage(url=url, html=html, status_code=200)


@pytest.mark.asyncio
async def test_discover_rejects_false_top_search_result_and_uses_verified_candidate() -> None:
    false_url = "https://acme-logistics-directory.test"
    official_url = "https://acme-logistics.test"
    crawler = FakeCrawler(
        {
            false_url: [
                _page(
                    false_url,
                    "<html><body><h1>Katalog firm</h1><p>Inne przedsiębiorstwa.</p></body></html>",
                )
            ],
            official_url: [
                _page(
                    official_url,
                    """
                    <html><body>
                      <h1>ACME Logistics Sp. z o.o.</h1>
                      <p>Siedziba firmy: Gdańsk.</p>
                      <p>Kontakt: wspolpraca@acme-logistics.test</p>
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
                url=false_url,
                snippet="ACME Logistics firma Gdańsk kontakt",
            ),
            SearchCandidate(
                title="ACME Logistics",
                url=official_url,
                snippet="Transport i logistyka",
            ),
        ]
    )
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=provider,
    )

    result = await pipeline.discover("ACME Logistics Sp. z o.o.", "Gdańsk")

    assert result.company.website_url == official_url
    assert result.company.website_confidence >= 0.55
    assert result.company.website_resolution_origin == WebsiteResolutionOrigin.SEARCH
    assert result.company.website_resolution_source == "search_provider"
    assert "accepted" in result.company.website_verification_signals
    assert crawler.calls == [false_url, official_url]
    assert result.scanned_pages == [official_url]
    assert len(result.page_snapshots) == 1
    assert result.page_snapshots[0].url == official_url
    assert len(result.page_snapshots[0].content_sha256) == 64
    assert "ACME Logistics" in result.page_snapshots[0].text_excerpt
    assert len(result.website_attempts) == 2
    assert result.website_attempts[0].url == false_url
    assert result.website_attempts[0].accepted is False
    assert result.website_attempts[0].origin == WebsiteResolutionOrigin.SEARCH
    assert result.website_attempts[0].source == "search_provider"
    assert "identity_not_confirmed" in result.website_attempts[0].signals
    assert len(result.website_attempts[0].page_snapshots[0].content_sha256) == 64
    assert result.website_attempts[1].url == official_url
    assert result.website_attempts[1].accepted is True
    assert result.website_attempts[1].origin == WebsiteResolutionOrigin.SEARCH
    assert result.website_attempts[1].scanned_pages == [official_url]


@pytest.mark.asyncio
async def test_discover_returns_no_website_when_identity_cannot_be_confirmed() -> None:
    candidate_url = "https://acme-directory.test"
    crawler = FakeCrawler(
        {
            candidate_url: [
                _page(
                    candidate_url,
                    "<html><body><h1>Katalog usług</h1><p>Warszawa</p></body></html>",
                )
            ]
        }
    )
    provider = StaticSearchProvider(
        [
            SearchCandidate(
                title="ACME Logistics Gdańsk oficjalna",
                url=candidate_url,
                snippet="ACME Logistics firma Gdańsk kontakt",
            )
        ]
    )
    pipeline = EmployerDiscoveryPipeline(
        crawler=crawler,  # type: ignore[arg-type]
        search_provider=provider,
    )

    result = await pipeline.discover("ACME Logistics", "Gdańsk")

    assert result.company.website_url is None
    assert result.company.website_confidence == 0.0
    assert result.company.website_resolution_origin is None
    assert result.company.website_verification_signals == [
        "no_verified_website_candidate"
    ]
    assert result.channels == []
    assert result.page_snapshots == []
    assert len(result.website_attempts) == 1
    assert result.website_attempts[0].accepted is False
    assert result.website_attempts[0].origin == WebsiteResolutionOrigin.SEARCH
    assert result.website_attempts[0].resolved_url == candidate_url
    assert len(result.website_attempts[0].page_snapshots) == 1


@pytest.mark.asyncio
async def test_source_website_candidate_is_verified_before_acceptance() -> None:
    official_url = "https://acme-logistics.test"
    crawler = FakeCrawler(
        {
            official_url: [
                _page(
                    official_url,
                    """
                    <html><body>
                      <h1>ACME Logistics Sp. z o.o.</h1>
                      <p>Siedziba firmy: Gdańsk.</p>
                      <p>Kontakt dla partnerów: partnerzy@acme-logistics.test</p>
                    </body></html>
                    """,
                )
            ]
        }
    )
    pipeline = EmployerDiscoveryPipeline(crawler=crawler)  # type: ignore[arg-type]

    result = await pipeline.verify_website_candidate(
        "ACME Logistics Sp. z o.o.",
        official_url,
        "Gdańsk",
        candidate_confidence=0.98,
        source_signal="source_website_candidate:official_feed.adresWww",
        resolution_source="official_feed.adresWww",
    )

    assert result.company.website_url == official_url
    assert result.company.website_confidence >= 0.55
    assert result.company.website_resolution_origin == WebsiteResolutionOrigin.SOURCE_CANDIDATE
    assert result.company.website_resolution_source == "official_feed.adresWww"
    assert result.company.website_verification_signals[0] == (
        "source_website_candidate:official_feed.adresWww"
    )
    assert "accepted" in result.company.website_verification_signals
    assert len(result.website_attempts) == 1
    assert result.website_attempts[0].accepted is True
    assert result.website_attempts[0].origin == WebsiteResolutionOrigin.SOURCE_CANDIDATE
    assert result.website_attempts[0].source == "official_feed.adresWww"
    assert crawler.calls == [official_url]


@pytest.mark.asyncio
async def test_source_website_candidate_is_rejected_when_identity_does_not_match() -> None:
    candidate_url = "https://unrelated-company.test"
    crawler = FakeCrawler(
        {
            candidate_url: [
                _page(
                    candidate_url,
                    "<html><body><h1>Inna Firma</h1><p>Warszawa</p></body></html>",
                )
            ]
        }
    )
    pipeline = EmployerDiscoveryPipeline(crawler=crawler)  # type: ignore[arg-type]

    result = await pipeline.verify_website_candidate(
        "ACME Logistics",
        candidate_url,
        "Gdańsk",
        candidate_confidence=0.98,
        source_signal="source_website_candidate:official_feed.adresWww",
        resolution_source="official_feed.adresWww",
    )

    assert result.company.website_url is None
    assert result.company.website_resolution_origin is None
    assert "source_candidate_not_verified" in result.company.website_verification_signals
    assert len(result.website_attempts) == 1
    assert result.website_attempts[0].accepted is False
    assert result.website_attempts[0].origin == WebsiteResolutionOrigin.SOURCE_CANDIDATE
    assert result.website_attempts[0].source == "official_feed.adresWww"
    assert "identity_not_confirmed" in result.website_attempts[0].signals
