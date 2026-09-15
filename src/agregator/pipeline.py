from __future__ import annotations

from urllib.parse import urlparse

from .crawler import CrawlPage, WebsiteCrawler
from .extract import extract_channels
from .models import CompanyIdentity, ContactChannel, DiscoveryResult, SearchCandidate
from .resolver import score_candidate
from .search import SearchProvider
from .website_verification import verify_company_website


class EmployerDiscoveryPipeline:
    def __init__(
        self,
        crawler: WebsiteCrawler,
        search_provider: SearchProvider | None = None,
        *,
        max_website_candidates: int = 3,
        minimum_search_score: float = 0.45,
    ) -> None:
        self.crawler = crawler
        self.search_provider = search_provider
        self.max_website_candidates = max(1, max_website_candidates)
        self.minimum_search_score = minimum_search_score

    @staticmethod
    def _deduplicate(channels: list[ContactChannel]) -> list[ContactChannel]:
        best: dict[tuple[str, str], ContactChannel] = {}
        for channel in channels:
            key = (channel.kind.value, channel.value.lower())
            previous = best.get(key)
            if previous is None or channel.confidence > previous.confidence:
                best[key] = channel
        return sorted(best.values(), key=lambda item: item.confidence, reverse=True)

    def _result_from_pages(
        self,
        *,
        company_name: str,
        city: str | None,
        website_url: str,
        website_confidence: float,
        pages: list[CrawlPage],
        search_candidates: list[SearchCandidate] | None = None,
        verification_signals: list[str] | None = None,
    ) -> DiscoveryResult:
        channels: list[ContactChannel] = []
        for page in pages:
            channels.extend(extract_channels(page.html, page.url))

        resolved_url = pages[0].url if pages else website_url
        domain = (urlparse(resolved_url).hostname or "").removeprefix("www.") or None
        return DiscoveryResult(
            company=CompanyIdentity(
                name=company_name,
                city=city,
                website_url=resolved_url,
                domain=domain,
                website_confidence=website_confidence,
                website_verification_signals=verification_signals or [],
            ),
            channels=self._deduplicate(channels),
            scanned_pages=[page.url for page in pages],
            search_candidates=search_candidates or [],
        )

    async def scan_known_website(
        self,
        company_name: str,
        website_url: str,
        city: str | None = None,
        *,
        website_confidence: float = 1.0,
        search_candidates: list[SearchCandidate] | None = None,
    ) -> DiscoveryResult:
        pages = await self.crawler.crawl(website_url)
        return self._result_from_pages(
            company_name=company_name,
            city=city,
            website_url=website_url,
            website_confidence=website_confidence,
            pages=pages,
            search_candidates=search_candidates,
            verification_signals=["known_or_user_supplied_website"],
        )

    async def discover(self, company_name: str, city: str | None = None) -> DiscoveryResult:
        if self.search_provider is None:
            raise RuntimeError("Search provider is required for automatic website discovery")

        candidates = await self.search_provider.search_company(company_name, city)
        ranked = [
            candidate.model_copy(
                update={"score": score_candidate(candidate, company_name, city)}
            )
            for candidate in candidates
        ]
        ranked.sort(key=lambda item: item.score, reverse=True)

        eligible = [
            candidate
            for candidate in ranked
            if candidate.score >= self.minimum_search_score
        ][: self.max_website_candidates]

        for candidate in eligible:
            pages = await self.crawler.crawl(candidate.url)
            resolved_url = pages[0].url if pages else candidate.url
            verification = verify_company_website(
                company_name,
                city,
                resolved_url,
                pages,
                search_score=candidate.score,
            )
            if not verification.accepted:
                continue

            return self._result_from_pages(
                company_name=company_name,
                city=city,
                website_url=resolved_url,
                website_confidence=verification.score,
                pages=pages,
                search_candidates=ranked,
                verification_signals=list(verification.signals),
            )

        return DiscoveryResult(
            company=CompanyIdentity(
                name=company_name,
                city=city,
                website_verification_signals=["no_verified_website_candidate"],
            ),
            channels=[],
            scanned_pages=[],
            search_candidates=ranked,
        )
