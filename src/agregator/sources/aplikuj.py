from __future__ import annotations

import asyncio
import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from .base import SourceBatch
from .public_html import HtmlJobSourceConfig, parse_job_detail_html

BASE_URL = "https://www.aplikuj.pl"
LISTING_FIRST = BASE_URL + "/praca"
LISTING_PAGE = BASE_URL + "/praca/strona-{page}"
_OFFER_PATH = re.compile(r"^/oferta/(\d+)/[^/?#]+/?$", re.IGNORECASE)
_NIP = re.compile(r"\bNIP\s*[:\-]?\s*(\d{10})\b", re.IGNORECASE)
_DATE_ADDED = re.compile(
    r"\bDodana\s+(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {
    "sty": "01",
    "stycznia": "01",
    "lut": "02",
    "lutego": "02",
    "mar": "03",
    "marca": "03",
    "kwi": "04",
    "kwietnia": "04",
    "maj": "05",
    "maja": "05",
    "cze": "06",
    "czerwca": "06",
    "lip": "07",
    "lipca": "07",
    "sie": "08",
    "sierpnia": "08",
    "wrz": "09",
    "września": "09",
    "wrzesnia": "09",
    "paź": "10",
    "paz": "10",
    "października": "10",
    "pazdziernika": "10",
    "lis": "11",
    "listopada": "11",
    "gru": "12",
    "grudnia": "12",
}

_CONFIG = HtmlJobSourceConfig(
    name="aplikuj",
    base_url=BASE_URL,
    listing_url_template=LISTING_FIRST,
    offer_path_patterns=(r"^/oferta/\d+/",),
    paginated=True,
    title_selectors=("h1",),
    company_selectors=(
        "a[href*='/pracodawca/']",
        "a[href*='/firma/']",
    ),
    city_selectors=(
        "[class*='location']",
        "[data-testid*='location']",
    ),
    description_selectors=("main", "article"),
)


class AplikujPublicSource:
    """Collect public Aplikuj.pl job listing/detail pages.

    The portal exposes a public, server-rendered `/praca/strona-N` sequence and
    `/oferta/<id>/<slug>` detail pages. Listing cards also link to first-party
    employer profiles; when a profile explicitly labels an external link as
    `Strona www`, that URL is preserved as a source-provided website candidate.
    Only public HTML is used and robots.txt is checked before each Aplikuj path.
    """

    name = "aplikuj"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.5,
        max_details_per_page: int = 50,
        max_retries: int = 2,
    ) -> None:
        self._client = client
        self.user_agent = user_agent
        self.request_delay = max(0.0, request_delay)
        self.max_details_per_page = max(1, min(max_details_per_page, 100))
        self.max_retries = max(0, max_retries)
        self._robots: urllib.robotparser.RobotFileParser | None = None

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = self._parse_page(cursor)
        listing_url = LISTING_FIRST if page == 1 else LISTING_PAGE.format(page=page)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "pl-PL,pl;q=0.9",
                "User-Agent": self.user_agent,
            },
        )

        profile_cache: dict[str, CompanyWebsiteCandidate | None] = {}
        try:
            await self._assert_allowed(client, listing_url)
            listing_html = await self._get_text(client, listing_url)
            entries = extract_offer_entries(listing_url, listing_html)
            entries = entries[: self.max_details_per_page]

            jobs: list[JobPosting] = []
            for index, (url, listing_profile_url) in enumerate(entries):
                await self._assert_allowed(client, url)
                if index and self.request_delay:
                    await asyncio.sleep(self.request_delay)
                try:
                    detail_html = await self._get_text(client, url)
                except httpx.HTTPError:
                    continue
                job = parse_aplikuj_detail(url, detail_html)
                if job is None:
                    continue

                profile_url = listing_profile_url or _payload_profile_url(job)
                if profile_url:
                    _set_payload_profile_url(job, profile_url)
                    if not job.company_website_candidates:
                        candidate = await self._profile_website_candidate(
                            client,
                            profile_url,
                            profile_cache,
                        )
                        if candidate is not None:
                            job.company_website_candidates.append(
                                candidate.model_copy(deep=True)
                            )
                jobs.append(job)
        finally:
            if owns_client:
                await client.aclose()

        next_cursor = str(page + 1) if entries else None
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    async def _profile_website_candidate(
        self,
        client: httpx.AsyncClient,
        profile_url: str,
        cache: dict[str, CompanyWebsiteCandidate | None],
    ) -> CompanyWebsiteCandidate | None:
        if profile_url in cache:
            return cache[profile_url]

        try:
            await self._assert_allowed(client, profile_url)
            if self.request_delay:
                await asyncio.sleep(self.request_delay)
            profile_html = await self._get_text(client, profile_url)
        except (httpx.HTTPError, PermissionError):
            cache[profile_url] = None
            return None

        website_url = extract_employer_website(profile_url, profile_html)
        candidate = (
            CompanyWebsiteCandidate(
                url=website_url,
                source="aplikuj.employer_profile.website",
                confidence=0.95,
            )
            if website_url
            else None
        )
        cache[profile_url] = candidate
        return candidate

    @staticmethod
    def _parse_page(cursor: str | None) -> int:
        if not cursor:
            return 1
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid Aplikuj.pl page cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("Aplikuj.pl page cursor must be positive")
        return page

    async def _assert_allowed(self, client: httpx.AsyncClient, url: str) -> None:
        if self._robots is None:
            robots_url = f"{BASE_URL}/robots.txt"
            response = await client.get(
                robots_url,
                headers={"Accept": "text/plain,*/*;q=0.1"},
            )
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            if response.status_code in {401, 403}:
                parser.parse(["User-agent: *", "Disallow: /"])
            elif response.status_code == 404:
                parser.parse(["User-agent: *", "Allow: /"])
            else:
                response.raise_for_status()
                parser.parse(response.text.splitlines())
            self._robots = parser
        if not self._robots.can_fetch(self.user_agent, url):
            raise PermissionError(f"robots.txt disallows Aplikuj.pl URL: {url}")

    async def _get_text(self, client: httpx.AsyncClient, url: str) -> str:
        last_error: httpx.HTTPError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(min(2.0**attempt, 4.0))
        assert last_error is not None
        raise last_error


def extract_offer_entries(
    listing_url: str,
    html: str,
) -> list[tuple[str, str | None]]:
    """Return canonical offer URLs paired with their listing-card employer profile."""

    soup = BeautifulSoup(html, "html.parser")
    expected_host = urlparse(BASE_URL).netloc.lower()
    output: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        raw = str(anchor.get("href") or "").strip()
        if not raw or "/oferta/" not in raw:
            continue
        absolute = urljoin(listing_url, raw)
        parsed = urlparse(absolute)
        match = _OFFER_PATH.match(parsed.path)
        if parsed.netloc.lower() != expected_host or match is None:
            continue
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(
            (
                normalized,
                _listing_employer_profile_url(anchor, listing_url),
            )
        )
    return output


def extract_offer_links(listing_url: str, html: str) -> list[str]:
    return [url for url, _ in extract_offer_entries(listing_url, html)]


def extract_employer_website(profile_url: str, html: str) -> str | None:
    """Extract only Aplikuj's explicitly labelled employer `Strona www` link."""

    soup = BeautifulSoup(html, "html.parser")
    aplikuj_host = urlparse(BASE_URL).hostname or ""
    for anchor in soup.select("a[href]"):
        label = anchor.get_text(" ", strip=True).casefold()
        if "strona www" not in label:
            continue
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = urljoin(profile_url, raw)
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if host == aplikuj_host or host.endswith(f".{aplikuj_host}"):
            continue
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, "")
        )
    return None


def parse_aplikuj_detail(url: str, html: str) -> JobPosting | None:
    # Prefer structured JobPosting data when present; the generic parser also preserves
    # the original JSON-LD object in source_payload.
    structured_job = parse_job_detail_html(_CONFIG, url, html)
    soup = BeautifulSoup(html, "html.parser")
    visible_text = "\n".join(text.strip() for text in soup.stripped_strings if text.strip())

    if structured_job is not None:
        job = structured_job.model_copy(deep=True)
        job.source = "aplikuj"
        job.source_id = _source_id(url) or job.source_id
        _augment_job(job, soup, visible_text, url)
        return job

    title_node = soup.find("h1")
    source_id = _source_id(url)
    company_name = _company_name(soup, title_node)
    if title_node is None or not source_id or not company_name:
        return None

    title = title_node.get_text(" ", strip=True)
    if not title:
        return None
    job = JobPosting(
        source="aplikuj",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="aplikuj.detail.employer_link",
        company_name_confidence=0.98,
        city=_city_near_heading(title_node),
        description=visible_text,
        published_at=_published_date(visible_text),
        source_payload={"visible_text": visible_text},
    )
    _augment_job(job, soup, visible_text, url)
    return job


def _augment_job(job: JobPosting, soup: BeautifulSoup, text: str, url: str) -> None:
    source_id = _source_id(url)
    if source_id:
        job.source_id = source_id

    nip_match = _NIP.search(text)
    if nip_match is not None:
        nip = nip_match.group(1)
        duplicate_nip = any(
            item.kind.lower() == "nip" and item.value == nip
            for item in job.company_identifiers
        )
        if not duplicate_nip:
            job.company_identifiers.append(
                CompanyIdentifier(
                    kind="nip",
                    value=nip,
                    source="aplikuj.detail.recruitment_clause",
                    confidence=0.98,
                )
            )

    if not job.published_at:
        job.published_at = _published_date(text)
    if not job.city:
        heading = soup.find("h1")
        if isinstance(heading, Tag):
            job.city = _city_near_heading(heading)

    payload = dict(job.source_payload)
    payload.update(
        {
            "portal_offer_id": job.source_id,
            "visible_text": text,
            "employer_profile_url": _employer_profile_url(soup, url),
        }
    )
    job.source_payload = payload


def _listing_employer_profile_url(anchor: Tag, base_url: str) -> str | None:
    wrapper = anchor.find_parent("div", class_="offer-card-main-wrapper")
    if not isinstance(wrapper, Tag):
        return None
    for profile_anchor in wrapper.select("a[href*='/pracodawca/'], a[href*='/firma/']"):
        raw = str(profile_anchor.get("href") or "").strip()
        if raw:
            return _normalize_aplikuj_url(urljoin(base_url, raw))
    return None


def _payload_profile_url(job: JobPosting) -> str | None:
    value = job.source_payload.get("employer_profile_url")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _set_payload_profile_url(job: JobPosting, profile_url: str) -> None:
    payload = dict(job.source_payload)
    payload["employer_profile_url"] = profile_url
    job.source_payload = payload


def _normalize_aplikuj_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _source_id(url: str) -> str | None:
    match = _OFFER_PATH.match(urlparse(url).path)
    return match.group(1) if match else None


def _company_name(soup: BeautifulSoup, title_node: Tag | None) -> str | None:
    candidates: list[Tag] = []
    if isinstance(title_node, Tag):
        candidates.extend(title_node.find_all_next("a", href=True, limit=8))
    candidates.extend(soup.select("a[href*='/pracodawca/'], a[href*='/firma/']"))
    for anchor in candidates:
        href = str(anchor.get("href") or "")
        text = anchor.get_text(" ", strip=True)
        if text and ("/pracodawca/" in href or "/firma/" in href):
            return text
    return None


def _employer_profile_url(soup: BeautifulSoup, base_url: str) -> str | None:
    for anchor in soup.select("a[href*='/pracodawca/'], a[href*='/firma/']"):
        raw = str(anchor.get("href") or "").strip()
        if raw:
            return _normalize_aplikuj_url(urljoin(base_url, raw))
    return None


def _city_near_heading(title_node: Tag) -> str | None:
    ignored_prefixes = (
        "wygasa",
        "Umowa",
        "Pełny",
        "Specjalista",
        "Rekrutacja",
        "Praca",
    )
    for raw in title_node.find_all_next(string=True, limit=12):
        text = str(raw).strip()
        if not text or text == title_node.get_text(" ", strip=True):
            continue
        if text.startswith(ignored_prefixes):
            continue
        if len(text) <= 80 and not text.endswith(":"):
            return text.split(",", 1)[0].strip() or None
    return None


def _published_date(text: str) -> str | None:
    match = _DATE_ADDED.search(text)
    if match is None:
        return None
    month_key = match.group(2).casefold().rstrip(".")
    month = _MONTHS.get(month_key)
    if month is None:
        return None
    return f"{match.group(3)}-{month}-{int(match.group(1)):02d}"
