from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from .public_html import HtmlJobSourceConfig, PublicHtmlJobSource

BASE_URL = "https://www.karierawfinansach.pl"
LISTING_URL = BASE_URL + "/praca"

_CONFIG = HtmlJobSourceConfig(
    name="karierawfinansach",
    base_url=BASE_URL,
    listing_url_template=LISTING_URL,
    offer_path_patterns=(r"^/oferta-pracy/\d+",),
    paginated=False,
    max_offer_links=50,
    company_selectors=("a[href*='/pracodawca/']", ".company-name"),
    description_selectors=("main", "article", ".offer-content"),
)

_EXCLUDED_EXTERNAL_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "linkedin.com",
    "www.linkedin.com",
    "youtube.com",
    "www.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "play.google.com",
    "apps.apple.com",
    "itunes.apple.com",
    "grupambe.pl",
    "www.grupambe.pl",
    "careersinpoland.com",
    "www.careersinpoland.com",
    "techkariera.pl",
    "www.techkariera.pl",
    "googletagmanager.com",
    "www.googletagmanager.com",
}


class KarieraWFinansachPublicSource(PublicHtmlJobSource):
    """Public KarierawFinansach collector with employer-profile website enrichment.

    Job details expose a first-party `/pracodawca/...` profile. Those public profiles
    frequently publish the employer's own careers/corporate URL. The profile is fetched
    at most once per run and only after the inherited robots check allows it.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.8,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            _CONFIG,
            client=client,
            user_agent=user_agent,
            request_delay=request_delay,
            max_retries=max_retries,
        )
        self._profile_cache: dict[str, CompanyWebsiteCandidate | None] = {}

    async def _enrich_job_from_detail(
        self,
        client: httpx.AsyncClient,
        job: JobPosting,
        detail_html: str,
        detail_url: str,
    ) -> None:
        profile_url = extract_employer_profile_url(detail_html, detail_url, job.company_name)
        if profile_url is None:
            return

        payload = dict(job.source_payload)
        payload["employer_profile_url"] = profile_url
        job.source_payload = payload

        if not any(
            item.kind == "karierawfinansach_employer_profile" and item.value == profile_url
            for item in job.company_identifiers
        ):
            job.company_identifiers.append(
                CompanyIdentifier(
                    kind="karierawfinansach_employer_profile",
                    value=profile_url,
                    source="karierawfinansach.detail.employer_profile",
                    confidence=0.99,
                )
            )

        if job.company_website_candidates:
            return

        if profile_url not in self._profile_cache:
            try:
                await self._assert_allowed(client, profile_url)
                if self.request_delay:
                    await asyncio.sleep(self.request_delay)
                profile_html = await self._get_text(client, profile_url)
            except (PermissionError, httpx.HTTPError):
                self._profile_cache[profile_url] = None
            else:
                self._profile_cache[profile_url] = extract_employer_website(
                    profile_html,
                    profile_url,
                )

        candidate = self._profile_cache.get(profile_url)
        if candidate is not None:
            job.company_website_candidates.append(candidate.model_copy(deep=True))


def extract_employer_profile_url(
    html: str,
    detail_url: str,
    company_name: str,
) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    expected_host = (urlparse(BASE_URL).hostname or "").lower()
    normalized_company = _normalized_label(company_name)
    fallback: str | None = None

    for anchor in soup.select("a[href*='/pracodawca/']"):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = _clean_url(urljoin(detail_url, raw))
        parsed = urlparse(absolute)
        if (parsed.hostname or "").lower() != expected_host:
            continue
        if not parsed.path.startswith("/pracodawca/"):
            continue
        if fallback is None:
            fallback = absolute
        label = _normalized_label(anchor.get_text(" ", strip=True))
        if label and label == normalized_company:
            return absolute

    return fallback


def extract_employer_website(
    html: str,
    profile_url: str,
) -> CompanyWebsiteCandidate | None:
    """Return the first employer-owned external link before portal footer links.

    Live profiles place the employer website/careers URL before additional campaign links
    and before the portal-wide MBE/Careers in Poland/TechKariera footer. Known social,
    app-store and portal-owned destinations are excluded explicitly.
    """

    soup = BeautifulSoup(html, "html.parser")
    portal_host = (urlparse(BASE_URL).hostname or "").lower()

    for anchor in soup.select("a[href]"):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = _clean_url(urljoin(profile_url, raw))
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if host == portal_host or host.endswith(".karierawfinansach.pl"):
            continue
        if host in _EXCLUDED_EXTERNAL_HOSTS:
            continue

        return CompanyWebsiteCandidate(
            url=absolute,
            source="karierawfinansach.employer_profile.website",
            confidence=0.95,
        )

    return None


def _clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _normalized_label(value: str) -> str:
    return " ".join(value.casefold().split())
