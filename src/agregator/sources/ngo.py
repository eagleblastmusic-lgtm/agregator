from __future__ import annotations

import asyncio
import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import CompanyWebsiteCandidate, JobPosting
from .base import SourceBatch

BASE_URL = "https://ogloszenia.ngo.pl"
LISTING_URL = BASE_URL + "/praca-staz/dam-prace?page={page}"
_OFFER_PATH = re.compile(r"^/(\d+)-[^/]+\.html$", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})\b", re.IGNORECASE)
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
_GENERIC_HEADINGS = {
    "ogłoszenia - ngo.pl",
    "ogłoszenia",
    "dane kontaktowe",
}


class NgoPublicSource:
    """Collect public NGO.pl job/cooperation advertisements.

    Only public listing/detail HTML is read. Recruitment contact data remains source
    evidence and is not automatically converted to Faro cooperation GREEN channels.
    """

    name = "ngo"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.5,
        max_details_per_page: int = 50,
    ) -> None:
        self._client = client
        self.user_agent = user_agent
        self.request_delay = max(0.0, request_delay)
        self.max_details_per_page = max(1, min(max_details_per_page, 100))
        self._robots: urllib.robotparser.RobotFileParser | None = None

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = self._parse_page(cursor)
        listing_url = LISTING_URL.format(page=page)
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
                job = parse_offer_detail(url, detail_html)
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
            raise ValueError(f"invalid NGO.pl page cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("NGO.pl page cursor must be positive")
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
            raise PermissionError(f"robots.txt disallows NGO.pl URL: {url}")

    @staticmethod
    async def _get_text(client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


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
        if parsed.netloc.lower() != expected_host or not _OFFER_PATH.match(parsed.path):
            continue
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def parse_offer_detail(url: str, html: str) -> JobPosting | None:
    soup = BeautifulSoup(html, "html.parser")
    title_node = _offer_title_node(soup)
    source_id = _source_id(url)
    company_name = _value_after_label(soup, "Ogłoszeniodawca:")
    if title_node is None or not source_id or not company_name:
        return None

    title = title_node.get_text(" ", strip=True)
    visible_text = "\n".join(text.strip() for text in soup.stripped_strings if text.strip())
    city = _city_after_title(title_node)
    published_at = _published_date(visible_text)
    website = _website_after_label(soup, "Strona internetowa:")
    websites = (
        [
            CompanyWebsiteCandidate(
                url=website,
                source="ngo.detail.contact.website",
                confidence=0.90,
            )
        ]
        if website
        else []
    )

    return JobPosting(
        source="ngo",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="ngo.detail.advertiser",
        company_name_confidence=0.99,
        company_website_candidates=websites,
        city=city,
        description=visible_text,
        published_at=published_at,
        source_payload={
            "advertisement_id": source_id,
            "advertiser": company_name,
            "visible_text": visible_text,
            "recruitment_email_visible": _value_after_label(soup, "E-mail:"),
            "advertiser_website": website,
        },
    )


def _offer_title_node(soup: BeautifulSoup) -> Tag | None:
    for node in soup.find_all(["h1", "h2", "h3"]):
        text = node.get_text(" ", strip=True)
        if text and text.lower() not in _GENERIC_HEADINGS:
            return node
    return None


def _source_id(url: str) -> str | None:
    match = _OFFER_PATH.match(urlparse(url).path)
    return match.group(1) if match else None


def _value_after_label(soup: BeautifulSoup, label: str) -> str | None:
    values = [text.strip() for text in soup.stripped_strings if text.strip()]
    target = label.casefold()
    for index, value in enumerate(values):
        if value.casefold() != target:
            continue
        for candidate in values[index + 1 : index + 4]:
            if candidate.endswith(":"):
                break
            if candidate:
                return candidate
    return None


def _website_after_label(soup: BeautifulSoup, label: str) -> str | None:
    marker = soup.find(string=lambda value: bool(value and value.strip().casefold() == label.casefold()))
    if marker is not None:
        parent = marker.parent
        if isinstance(parent, Tag):
            anchor = parent.find_next("a", href=True)
            if anchor is not None:
                raw = str(anchor.get("href") or "").strip()
                if raw.startswith(("http://", "https://")):
                    return raw
    value = _value_after_label(soup, label)
    return value if value and value.startswith(("http://", "https://")) else None


def _city_after_title(title_node: Tag) -> str | None:
    for candidate in title_node.find_all_next(string=True, limit=8):
        text = str(candidate).strip()
        if not text or text == title_node.get_text(" ", strip=True):
            continue
        if _DATE.search(text) or text.endswith(":"):
            continue
        if len(text) <= 80:
            return text.removesuffix("・").strip() or None
    return None


def _published_date(text: str) -> str | None:
    match = _DATE.search(text)
    if match is None:
        return None
    month = _MONTHS.get(match.group(2).casefold())
    if month is None:
        return None
    return f"{match.group(3)}-{month}-{int(match.group(1)):02d}"
