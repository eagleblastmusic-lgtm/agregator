from __future__ import annotations

import asyncio
import html as html_module
import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from .public_html import HtmlJobSourceConfig, PublicHtmlJobSource

BASE_URL = "https://rocketjobs.pl"
_PORTAL_ROOT_HOST = "rocketjobs.pl"
_PROFILE_PREFIX = "/brands/story/"
_PROFILE_LABEL = "zobacz profil firmy"
_SERIALIZED_WEBSITE_RE = re.compile(
    r'"link":"(?P<url>https?://[^"<>]+)","type":"Website"',
    re.IGNORECASE,
)

_CONFIG = HtmlJobSourceConfig(
    name="rocketjobs",
    base_url=BASE_URL,
    listing_url_template=BASE_URL + "/",
    offer_path_patterns=(r"^/oferta-pracy/",),
    paginated=False,
    max_offer_links=50,
    company_selectors=(
        "a[href*='/brands/story/']",
        "[data-testid*='company']",
        ".company-name",
    ),
    description_selectors=("main", "article"),
)


class RocketJobsPublicSource(PublicHtmlJobSource):
    """Public RocketJobs collector enriched from employer-brand profiles.

    Employer profiles are accepted only when the job detail itself exposes a dedicated
    `Zobacz profil firmy`/company-name link to `/brands/story/...`. Global footer links to
    RocketJobs' own brand profile are deliberately ignored.

    Profile websites are sourced only from RocketJobs' serialized `socialMedia` entry whose
    type is exactly `Website`; arbitrary campaign, social or first-external links are not
    used as company websites.
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
        # A portal/profile URL is not an employer-owned website. Keep only truly external
        # JSON-LD candidates before deciding whether profile enrichment is needed.
        job.company_website_candidates = [
            item for item in job.company_website_candidates if not _is_portal_url(item.url)
        ]

        profile_url = extract_employer_profile_url(detail_html, detail_url, job.company_name)
        if profile_url is None:
            return

        payload = dict(job.source_payload)
        payload["employer_profile_url"] = profile_url
        job.source_payload = payload

        if not any(
            item.kind == "rocketjobs_employer_profile" and item.value == profile_url
            for item in job.company_identifiers
        ):
            job.company_identifiers.append(
                CompanyIdentifier(
                    kind="rocketjobs_employer_profile",
                    value=profile_url,
                    source="rocketjobs.detail.employer_profile",
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
    """Return only a profile linked from the employer section, never the global footer."""

    soup = BeautifulSoup(html, "html.parser")
    normalized_company = _normalized_label(company_name)
    labels_by_url: dict[str, list[str]] = defaultdict(list)

    for anchor in soup.select("a[href*='/brands/story/']"):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = _clean_url(urljoin(detail_url, raw))
        parsed = urlparse(absolute)
        if not _is_portal_host(parsed.hostname or ""):
            continue
        if not parsed.path.startswith(_PROFILE_PREFIX):
            continue
        slug = parsed.path.removeprefix(_PROFILE_PREFIX).strip("/")
        if not slug:
            continue
        labels_by_url[absolute].append(_normalized_label(anchor.get_text(" ", strip=True)))

    # The dedicated CTA is the strongest signal and is absent from the global footer.
    for url, labels in labels_by_url.items():
        if _PROFILE_LABEL in labels:
            return url

    # A directly linked employer name is also acceptable. Exact normalized equality avoids
    # treating unrelated footer links such as `O nas`/`Kariera` as employer profiles.
    for url, labels in labels_by_url.items():
        if normalized_company and normalized_company in labels:
            return url

    return None


def extract_employer_website(
    html: str,
    profile_url: str,
) -> CompanyWebsiteCandidate | None:
    """Extract RocketJobs' explicit serialized `socialMedia[type=Website]` value."""

    soup = BeautifulSoup(html, "html.parser")
    rendered_external_urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = _clean_url(urljoin(profile_url, raw))
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if _is_portal_host(parsed.hostname):
            continue
        rendered_external_urls.add(absolute)

    # React Server Components serialize profile data inside escaped script strings. Removing
    # escape backslashes gives us a stable JSON-like fragment while we still require the URL
    # to be rendered as an actual external anchor on the public profile page.
    serialized = html_module.unescape(html).replace("\\", "")
    for match in _SERIALIZED_WEBSITE_RE.finditer(serialized):
        candidate = _clean_url(match.group("url"))
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if _is_portal_host(parsed.hostname):
            continue
        if candidate not in rendered_external_urls:
            continue
        return CompanyWebsiteCandidate(
            url=candidate,
            source="rocketjobs.employer_profile.social_media.website",
            confidence=0.98,
        )

    return None


def _is_portal_url(value: str) -> bool:
    return _is_portal_host(urlparse(value).hostname or "")


def _is_portal_host(value: str) -> bool:
    host = value.strip().lower().rstrip(".")
    return host == _PORTAL_ROOT_HOST or host.endswith(f".{_PORTAL_ROOT_HOST}")


def _clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _normalized_label(value: str) -> str:
    return " ".join(value.casefold().split())
