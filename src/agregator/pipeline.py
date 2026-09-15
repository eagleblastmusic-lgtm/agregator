from __future__ import annotations

from urllib.parse import urlparse

from .crawler import WebsiteCrawler
from .extract import extract_channels
from .models import CompanyIdentity, ContactChannel, DiscoveryResult, SearchCandidate
from .resolver import choose_official_website, score_candidate
from .search import SearchProvider


class EmployerDiscoveryPipeline:
    def __init__(
        self,
        crawler: WebsiteCrawler,
        search_provider: SearchProvider | None = None,
    ) -> None:
        self.crawler = crawler
        self.search_provider = search_provider

    @staticmethod
    def _deduplicate(channels: list[ContactChannel]) -> list[ContactChannel]:
        best: dict[tuple[str, str], ContactChannel] = {}
        for channel in channels:
            key = (channel.kind.value, channel.value.lower())
            previous = best.get(key)
            if previous is None or channel.confidence > previous.confidence:
                best[key] = channel
        return sorted(best.values(), key=lambda item: item.confidence, reverse=True)

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
        channels: list[ContactChannel] = []
        for page in pages:
            channels.extend(extract_channels(page.html, page.url))

        domain = (urlparse(website_url).hostname or "").removeprefix("www.") or None
        return DiscoveryResult(
            company=CompanyIdentity(
                name=company_name,
                city=city,
                website_url=website_url,
                domain=domain,
                website_confidence=website_confidence,
            ),
            channels=self._deduplicate(channels),
            scanned_pages=[page.url for page in pages],
            search_candidates=search_candidates or [],
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
        chosen = choose_official_website(candidates, company_name, city)

        if chosen is None:
            return DiscoveryResult(
                company=CompanyIdentity(name=company_name, city=city),
                channels=[],
                scanned_pages=[],
                search_candidates=ranked,
            )

        return await self.scan_known_website(
            company_name=company_name,
            city=city,
            website_url=chosen.url,
            website_confidence=chosen.score,
            search_candidates=ranked,
        )
