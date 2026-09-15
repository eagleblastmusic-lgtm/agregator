from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .crawler import CrawlPage, WebsiteCrawler
from .extract import extract_channels
from .models import (
    CompanyIdentity,
    ContactChannel,
    DiscoveryResult,
    PageSnapshot,
    SearchCandidate,
    WebsiteResolutionOrigin,
    WebsiteVerificationAttempt,
)
from .resolver import score_candidate
from .search import SearchProvider
from .website_verification import WebsiteVerification, verify_company_website


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

    @staticmethod
    def _snapshot_page(page: CrawlPage) -> PageSnapshot:
        soup = BeautifulSoup(page.html, "html.parser")
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        text = " ".join(soup.stripped_strings)
        return PageSnapshot(
            url=page.url,
            status_code=page.status_code,
            content_sha256=hashlib.sha256(page.html.encode("utf-8")).hexdigest(),
            text_excerpt=text[:2000],
        )

    @classmethod
    def _page_snapshots(cls, pages: list[CrawlPage]) -> list[PageSnapshot]:
        return [cls._snapshot_page(page) for page in pages]

    @classmethod
    def _verification_attempt(
        cls,
        candidate: SearchCandidate,
        resolved_url: str,
        pages: list[CrawlPage],
        verification: WebsiteVerification,
        *,
        origin: WebsiteResolutionOrigin | None = None,
        source: str | None = None,
    ) -> WebsiteVerificationAttempt:
        return WebsiteVerificationAttempt(
            url=candidate.url,
            resolved_url=resolved_url,
            accepted=verification.accepted,
            score=verification.score,
            search_score=verification.search_score,
            content_score=verification.content_score,
            name_coverage=verification.name_coverage,
            origin=origin,
            source=source,
            signals=list(verification.signals),
            scanned_pages=[page.url for page in pages],
            page_snapshots=cls._page_snapshots(pages),
        )

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
        website_attempts: list[WebsiteVerificationAttempt] | None = None,
        resolution_origin: WebsiteResolutionOrigin | None = None,
        resolution_source: str | None = None,
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
                website_resolution_origin=resolution_origin,
                website_resolution_source=resolution_source,
                website_verification_signals=verification_signals or [],
            ),
            channels=self._deduplicate(channels),
            scanned_pages=[page.url for page in pages],
            page_snapshots=self._page_snapshots(pages),
            search_candidates=search_candidates or [],
            website_attempts=website_attempts or [],
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
            resolution_origin=WebsiteResolutionOrigin.KNOWN_URL,
            resolution_source="scan_known_website",
        )

    async def verify_website_candidate(
        self,
        company_name: str,
        website_url: str,
        city: str | None = None,
        *,
        candidate_confidence: float = 0.95,
        source_signal: str = "source_website_candidate",
        resolution_source: str | None = None,
    ) -> DiscoveryResult:
        """Verify a source-provided website candidate as first-party evidence.

        A URL present in a job/feed is useful provenance but is not accepted blindly.
        It is crawled and run through the same identity verifier used for search
        candidates. This lets official feeds reduce search cost without weakening the
        false-positive guardrail.
        """

        score = min(max(candidate_confidence, 0.0), 1.0)
        source = resolution_source or source_signal
        candidate = SearchCandidate(
            title=company_name,
            url=website_url,
            snippet=source_signal,
            score=score,
        )
        pages = await self.crawler.crawl(website_url)
        resolved_url = pages[0].url if pages else website_url
        verification = verify_company_website(
            company_name,
            city,
            resolved_url,
            pages,
            search_score=score,
        )
        attempt = self._verification_attempt(
            candidate,
            resolved_url,
            pages,
            verification,
            origin=WebsiteResolutionOrigin.SOURCE_CANDIDATE,
            source=source,
        )

        if verification.accepted:
            return self._result_from_pages(
                company_name=company_name,
                city=city,
                website_url=resolved_url,
                website_confidence=verification.score,
                pages=pages,
                verification_signals=[source_signal, *verification.signals],
                website_attempts=[attempt],
                resolution_origin=WebsiteResolutionOrigin.SOURCE_CANDIDATE,
                resolution_source=source,
            )

        return DiscoveryResult(
            company=CompanyIdentity(
                name=company_name,
                city=city,
                website_verification_signals=[
                    source_signal,
                    "source_candidate_not_verified",
                    *verification.signals,
                ],
            ),
            channels=[],
            scanned_pages=[],
            page_snapshots=[],
            search_candidates=[],
            website_attempts=[attempt],
        )

    async def discover(self, company_name: str, city: str | None = None) -> DiscoveryResult:
        if self.search_provider is None:
            raise RuntimeError("Search provider is required for automatic website discovery")

        search_source = str(
            getattr(self.search_provider, "name", type(self.search_provider).__name__)
        )
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
        attempts: list[WebsiteVerificationAttempt] = []

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
            attempts.append(
                self._verification_attempt(
                    candidate,
                    resolved_url,
                    pages,
                    verification,
                    origin=WebsiteResolutionOrigin.SEARCH,
                    source=search_source,
                )
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
                website_attempts=attempts,
                resolution_origin=WebsiteResolutionOrigin.SEARCH,
                resolution_source=search_source,
            )

        return DiscoveryResult(
            company=CompanyIdentity(
                name=company_name,
                city=city,
                website_verification_signals=["no_verified_website_candidate"],
            ),
            channels=[],
            scanned_pages=[],
            page_snapshots=[],
            search_candidates=ranked,
            website_attempts=attempts,
        )
