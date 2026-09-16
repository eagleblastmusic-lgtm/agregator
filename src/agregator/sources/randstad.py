from __future__ import annotations

import asyncio
import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import JobPosting
from .base import SourceBatch
from .public_html import HtmlJobSourceConfig, parse_job_detail_html

BASE_URL = "https://www.randstad.pl"
LISTING_FIRST = BASE_URL + "/znajdz-prace/"
LISTING_PAGE = BASE_URL + "/znajdz-prace/page-{page}/"
_OFFER_PATH = re.compile(r"^/znajdz-prace/[^/]+_(\d+)/?$", re.IGNORECASE)
_REFERENCE = re.compile(r"\breference\s+number\s+(\d+)\b", re.IGNORECASE)
_DATE = re.compile(
    r"\bopublikowano\s+(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {
    "stycznia": "01",
    "lutego": "02",
    "marca": "03",
    "kwietnia": "04",
    "maja": "05",
    "czerwca": "06",
    "lipca": "07",
    "sierpnia": "08",
    "września": "09",
    "wrzesnia": "09",
    "października": "10",
    "pazdziernika": "10",
    "listopada": "11",
    "grudnia": "12",
}

_CONFIG = HtmlJobSourceConfig(
    name="randstad",
    base_url=BASE_URL,
    listing_url_template=LISTING_FIRST,
    offer_path_patterns=(r"^/znajdz-prace/[^/]+_\d+/?$",),
    paginated=True,
    title_selectors=("h1",),
    description_selectors=("main", "article"),
)


class RandstadPublicSource:
    """Collect public Randstad Poland job listing/detail pages.

    Randstad often recruits for an undisclosed client. When the page does not expose
    a structured hiring organization, the adapter keeps Randstad as a low-confidence
    agency fallback instead of pretending that the hidden end employer is known.
    """

    name = "randstad"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.5,
        max_details_per_page: int = 30,
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

        try:
            await self._assert_allowed(client, listing_url)
            listing_html = await self._get_text(client, listing_url)
            links = extract_offer_links(listing_url, listing_html)
            links = links[: self.max_details_per_page]

            jobs: list[JobPosting] = []
            for index, url in enumerate(links):
                await self._assert_allowed(client, url)
                if index and self.request_delay:
                    await asyncio.sleep(self.request_delay)
                try:
                    detail_html = await self._get_text(client, url)
                except httpx.HTTPError:
                    continue
                job = parse_randstad_detail(url, detail_html)
                if job is not None:
                    jobs.append(job)
        finally:
            if owns_client:
                await client.aclose()

        next_cursor = str(page + 1) if links else None
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_page(cursor: str | None) -> int:
        if not cursor:
            return 1
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid Randstad page cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("Randstad page cursor must be positive")
        return page

    async def _assert_allowed(self, client: httpx.AsyncClient, url: str) -> None:
        if self._robots is None:
            robots_url = f"{BASE_URL}/robots.txt"
            response = await client.get(robots_url)
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
            raise PermissionError(f"robots.txt disallows Randstad URL: {url}")

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


def extract_offer_links(listing_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    expected_host = urlparse(BASE_URL).netloc.lower()
    output: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = urljoin(listing_url, raw)
        parsed = urlparse(absolute)
        if parsed.netloc.lower() != expected_host or _OFFER_PATH.match(parsed.path) is None:
            continue
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/", "", "", "")
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def parse_randstad_detail(url: str, html: str) -> JobPosting | None:
    structured_job = parse_job_detail_html(_CONFIG, url, html)
    soup = BeautifulSoup(html, "html.parser")
    visible_text = "\n".join(text.strip() for text in soup.stripped_strings if text.strip())
    source_id = _source_id(url)
    if source_id is None:
        return None

    if structured_job is not None:
        job = structured_job.model_copy(deep=True)
        job.source = "randstad"
        job.source_id = source_id
        _augment_job(job, visible_text)
        return job

    title_node = soup.find("h1")
    if not isinstance(title_node, Tag):
        return None
    title = title_node.get_text(" ", strip=True)
    if not title:
        return None

    job = JobPosting(
        source="randstad",
        source_id=source_id,
        url=url,
        title=title,
        company_name="Randstad Polska Sp. z o.o.",
        company_name_source="randstad.agency_fallback",
        company_name_confidence=0.35,
        city=_city_after_heading(title_node),
        description=visible_text,
        published_at=_published_date(visible_text),
        source_payload={
            "portal_offer_id": source_id,
            "visible_text": visible_text,
            "agency_fallback": True,
            "client_employer_disclosed": False,
        },
    )
    _augment_job(job, visible_text)
    return job


def _augment_job(job: JobPosting, text: str) -> None:
    if not job.published_at:
        job.published_at = _published_date(text)

    reference = _REFERENCE.search(text)
    payload = dict(job.source_payload)
    payload.update(
        {
            "portal_offer_id": job.source_id,
            "reference_number": reference.group(1) if reference else None,
            "visible_text": text,
            "agency_fallback": job.company_name_source == "randstad.agency_fallback",
            "client_employer_disclosed": job.company_name_source
            != "randstad.agency_fallback",
        }
    )
    job.source_payload = payload


def _source_id(url: str) -> str | None:
    match = _OFFER_PATH.match(urlparse(url).path)
    return match.group(1) if match else None


def _published_date(text: str) -> str | None:
    match = _DATE.search(text)
    if match is None:
        return None
    month = _MONTHS.get(match.group(2).casefold())
    if month is None:
        return None
    return f"{match.group(3)}-{month}-{int(match.group(1)):02d}"


def _city_after_heading(title_node: Tag) -> str | None:
    skip = {
        "szczegóły oferty",
        "podsumowanie",
        "aplikuj",
    }
    title_text = title_node.get_text(" ", strip=True).removesuffix(".").casefold()
    for raw in title_node.find_all_next(string=True, limit=20):
        text = str(raw).strip().removesuffix(".")
        if not text or text.casefold() in skip:
            continue
        if text.casefold() == title_text:
            continue
        if text.casefold().startswith(("opublikowano", "ważna do")):
            continue
        if 2 <= len(text) <= 80 and not text.endswith(":"):
            return text.split(",", 1)[0].strip() or None
    return None
