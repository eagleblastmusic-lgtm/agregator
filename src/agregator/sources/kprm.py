from __future__ import annotations

import asyncio
import re
import urllib.robotparser
from urllib.parse import unquote, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..models import JobPosting
from .base import SourceBatch

KPRM_BASE_URL = "https://nabory.kprm.gov.pl"
KPRM_XML_URL = "https://nabory.kprm.gov.pl/pls/serwis/app.xml"
_DETAIL_PATH = re.compile(r"^/[^/]+/[^/]+/[^,]+,\d+,v\d+$", re.IGNORECASE)
_XML_OFFER_URL = re.compile(
    r"https?://nabory\.kprm\.gov\.pl/[^\s<>\"']+?,\d+,v\d+",
    re.IGNORECASE,
)
_ANNOUNCEMENT = re.compile(r"Ogłoszenie\s+nr\s+(\d+)\s*/\s*(\d{2}\.\d{2}\.\d{4})", re.I)


class KprmPublicSource:
    """Collect public civil-service notices from the official KPRM XML export.

    The XML endpoint is linked by the official service and contains current notice URLs.
    Detail pages remain the evidence source for the human-visible notice text.
    """

    name = "kprm"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.5,
        max_details_per_page: int = 20,
    ) -> None:
        self._client = client
        self.user_agent = user_agent
        self.request_delay = max(0.0, request_delay)
        self.max_details_per_page = max(1, min(max_details_per_page, 100))
        self._robots: urllib.robotparser.RobotFileParser | None = None

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = self._parse_page(cursor)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            headers={
                "Accept": "application/xml,text/xml,text/html;q=0.9,*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9",
                "User-Agent": self.user_agent,
            },
        )
        try:
            await self._assert_allowed(client, KPRM_XML_URL)
            xml = await self._get_text(client, KPRM_XML_URL)
            all_links = extract_kprm_offer_links(KPRM_XML_URL, xml)
            start = (page - 1) * self.max_details_per_page
            end = start + self.max_details_per_page
            links = all_links[start:end]

            jobs: list[JobPosting] = []
            for index, url in enumerate(links):
                await self._assert_allowed(client, url)
                if index and self.request_delay:
                    await asyncio.sleep(self.request_delay)
                try:
                    html = await self._get_text(client, url)
                except httpx.HTTPError:
                    continue
                job = parse_kprm_detail(url, html)
                if job is not None:
                    jobs.append(job)
        finally:
            if owns_client:
                await client.aclose()

        next_cursor = str(page + 1) if end < len(all_links) else None
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_page(cursor: str | None) -> int:
        if not cursor:
            return 1
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid KPRM page cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("KPRM page cursor must be positive")
        return page

    async def _assert_allowed(self, client: httpx.AsyncClient, url: str) -> None:
        if self._robots is None:
            robots_url = f"{KPRM_BASE_URL}/robots.txt"
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
            raise PermissionError(f"robots.txt disallows KPRM URL: {url}")

    @staticmethod
    async def _get_text(client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def extract_kprm_offer_links(listing_url: str, html: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    def add(raw_url: str) -> None:
        absolute = urljoin(listing_url, raw_url.strip())
        parsed = urlparse(absolute)
        if parsed.netloc.lower() != urlparse(KPRM_BASE_URL).netloc.lower():
            return
        path = unquote(parsed.path)
        if not _DETAIL_PATH.match(path):
            return
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if normalized in seen:
            return
        seen.add(normalized)
        output.append(normalized)

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        add(str(anchor.get("href") or ""))
    for match in _XML_OFFER_URL.finditer(html):
        add(match.group(0))
    return output


def parse_kprm_detail(url: str, html: str) -> JobPosting | None:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find("h1")
    title = title_node.get_text(" ", strip=True) if title_node is not None else ""
    if not title:
        return None

    lines = [text.strip() for text in soup.stripped_strings if text.strip()]
    full_text = "\n".join(lines)
    announcement = _ANNOUNCEMENT.search(full_text)
    source_id = announcement.group(1) if announcement else _source_id_from_url(url)
    if not source_id:
        return None

    company_name = _company_before_announcement(lines) or _company_from_document_title(soup, title)
    if not company_name:
        return None

    published_at = _publication_date(announcement)
    city = _city_from_url(url)
    contact_phones = _phones_after_marker(lines, "Zapraszamy również do kontaktu telefonicznego")

    return JobPosting(
        source="kprm",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source=(
            "kprm.detail.header" if _company_before_announcement(lines) else "kprm.document_title"
        ),
        company_name_confidence=0.99,
        city=city,
        description=full_text,
        published_at=published_at,
        source_payload={
            "announcement_number": source_id,
            "publication_date": published_at,
            "visible_text": full_text,
            "recruitment_contact_phones": contact_phones,
            "discovery_source": KPRM_XML_URL,
        },
    )


def _company_before_announcement(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        if _ANNOUNCEMENT.search(line):
            for candidate in reversed(lines[max(0, index - 6) : index]):
                if candidate.lower().startswith(("ogłoszenia o", "wyniki naborów", "wróć")):
                    continue
                if len(candidate) >= 4:
                    return candidate
    return None


def _company_from_document_title(soup: BeautifulSoup, job_title: str) -> str | None:
    title_node = soup.find("title")
    if title_node is None:
        return None
    parts = [part.strip() for part in title_node.get_text(" ", strip=True).split("|")]
    if len(parts) < 2:
        return None
    for part in parts[1:]:
        if not part or part.casefold() == job_title.casefold():
            continue
        if "praca w służbie cywilnej" in part.casefold():
            continue
        return part
    return None


def _publication_date(match: re.Match[str] | None) -> str | None:
    if match is None:
        return None
    day, month, year = match.group(2).split(".")
    return f"{year}-{month}-{day}"


def _source_id_from_url(url: str) -> str | None:
    match = re.search(r",(\d+),v\d+$", unquote(urlparse(url).path), re.I)
    return match.group(1) if match else None


def _city_from_url(url: str) -> str | None:
    parts = [part for part in unquote(urlparse(url).path).split("/") if part]
    if len(parts) < 2:
        return None
    return parts[1].replace("-", " ").title()


def _phones_after_marker(lines: list[str], marker: str) -> list[str]:
    marker_lower = marker.lower()
    for index, line in enumerate(lines):
        if marker_lower not in line.lower():
            continue
        chunk = " ".join(lines[index + 1 : index + 4])
        candidates = re.findall(r"(?:\+?48[\s/-]?)?(?:\d[\s/-]?){7,12}", chunk)
        return [value.strip() for value in candidates]
    return []
