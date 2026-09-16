from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from .public_html import HtmlJobSourceConfig, PublicHtmlJobSource

BASE_URL = "https://www.skillshot.pl"
_PORTAL_ROOT_HOST = "skillshot.pl"

_CONFIG = HtmlJobSourceConfig(
    name="skillshot",
    base_url=BASE_URL,
    listing_url_template=BASE_URL + "/jobs?page={page}",
    offer_path_patterns=(r"^/jobs/\d+-",),
    paginated=True,
    start_page=1,
    max_offer_links=40,
    company_selectors=("a[href*='/users/']",),
    description_selectors=("main", "article", ".job-description"),
)

_WEBSITE_LABELS = (
    "web page",
    "website",
    "strona internetowa",
    "strona www",
)


class SkillshotPublicSource(PublicHtmlJobSource):
    """Public Skillshot collector enriched from first-party employer profiles.

    Job details expose a public `/users/<id>` employer profile. Skillshot profiles
    explicitly publish the employer's own site in a `Web page` field. Only that labelled
    field is accepted as a source-provided website; recruitment-system links from job ads
    and unrelated social links are deliberately ignored.
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
            item.kind == "skillshot_employer_profile" and item.value == profile_url
            for item in job.company_identifiers
        ):
            job.company_identifiers.append(
                CompanyIdentifier(
                    kind="skillshot_employer_profile",
                    value=profile_url,
                    source="skillshot.detail.employer_profile",
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
    normalized_company = _normalized_label(company_name)
    fallback: str | None = None

    for anchor in soup.select("a[href*='/users/']"):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = _clean_url(urljoin(detail_url, raw))
        parsed = urlparse(absolute)
        if not _is_portal_host(parsed.hostname or ""):
            continue
        if not parsed.path.startswith("/users/"):
            continue
        tail = parsed.path.removeprefix("/users/").strip("/")
        if not tail.isdigit():
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
    """Extract only Skillshot's explicitly labelled employer `Web page` field."""

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        if not isinstance(anchor, Tag):
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue

        context = _anchor_context(anchor)
        if not any(label in context for label in _WEBSITE_LABELS):
            continue

        absolute = _clean_url(urljoin(profile_url, raw))
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if _is_portal_host(host):
            continue

        return CompanyWebsiteCandidate(
            url=absolute,
            source="skillshot.employer_profile.web_page",
            confidence=0.97,
        )

    return None


def _anchor_context(anchor: Tag) -> str:
    parent = anchor.parent
    if isinstance(parent, Tag):
        text = parent.get_text(" ", strip=True)
    else:
        text = anchor.get_text(" ", strip=True)
    return _normalized_label(text)


def _is_portal_host(value: str) -> bool:
    host = value.strip().lower().rstrip(".")
    return host == _PORTAL_ROOT_HOST or host.endswith(f".{_PORTAL_ROOT_HOST}")


def _clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _normalized_label(value: str) -> str:
    return " ".join(value.casefold().split())
