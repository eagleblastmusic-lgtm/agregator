from __future__ import annotations

import asyncio
import html as html_module
import json
import re
import urllib.robotparser
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..models import CompanyWebsiteCandidate, JobPosting
from .base import SourceBatch

BASE_URL = "https://ofertypracy.edu.pl"
LISTING_URL = BASE_URL + "/?page={page}&per_page=25&search=1&sort=-published_at"
_OFFER_PATH = re.compile(r"^/oferty/(\d+)/?$", re.IGNORECASE)
_OFFICIAL_ID = re.compile(r"\bID:\s*([0-9]+/[0-9]{4})\b", re.IGNORECASE)
_POSTAL_CITY = re.compile(r"\b\d{2}-\d{3}\s+([^\n]+)")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?48[\s/-]?)?(?:\d[\s/-]?){7,12}(?!\d)")


class OfertyPracyEduPublicSource:
    """Collect public MEN/SIO education vacancies from OfertyPracy.edu.pl.

    The current site is an Inertia application. Public offer records are embedded in
    the server response as ``#app[data-page]`` JSON, so the adapter reads that public
    payload instead of depending on client-side rendered anchors. Recruitment contact
    data stays raw evidence only and is never promoted directly to Faro GREEN.
    """

    name = "ofertypracyedu"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.5,
        max_details_per_page: int = 100,
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
            links, next_cursor = extract_listing_offer_links(listing_url, listing_html)
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

        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    @staticmethod
    def _parse_page(cursor: str | None) -> int:
        if not cursor:
            return 1
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid OfertyPracy.edu.pl page cursor: {cursor}") from exc
        if page < 1:
            raise ValueError("OfertyPracy.edu.pl page cursor must be positive")
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
            raise PermissionError(f"robots.txt disallows OfertyPracy.edu.pl URL: {url}")

    @staticmethod
    async def _get_text(client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def extract_listing_offer_links(
    listing_url: str,
    html: str,
) -> tuple[list[str], str | None]:
    """Return offer URLs and the next cursor from public Inertia or legacy HTML."""

    payload = _inertia_payload(html)
    if payload is not None:
        props = payload.get("props")
        props = props if isinstance(props, dict) else {}
        offers = props.get("offers")
        offers = offers if isinstance(offers, dict) else {}
        data = offers.get("data")
        data = data if isinstance(data, list) else []
        meta = offers.get("meta")
        meta = meta if isinstance(meta, dict) else {}

        output: list[str] = []
        seen: set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            offer_id = _as_identifier(item.get("id"))
            if offer_id is None:
                continue
            url = f"{BASE_URL}/oferty/{offer_id}"
            if url not in seen:
                seen.add(url)
                output.append(url)

        current_page = _as_positive_int(meta.get("current_page"))
        last_page = _as_positive_int(meta.get("last_page"))
        next_cursor = None
        if current_page is not None and last_page is not None and current_page < last_page:
            next_cursor = str(current_page + 1)
        return output, next_cursor

    links = extract_offer_links(listing_url, html)
    page = _page_from_listing_url(listing_url)
    return links, str(page + 1) if links else None


def extract_offer_links(listing_url: str, html: str) -> list[str]:
    """Legacy server-rendered HTML fallback kept for backwards compatibility."""

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
        if parsed.netloc.lower() != expected_host:
            continue
        if not _OFFER_PATH.match(parsed.path):
            continue
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def parse_offer_detail(url: str, html: str) -> JobPosting | None:
    payload = _inertia_payload(html)
    if payload is not None:
        props = payload.get("props")
        props = props if isinstance(props, dict) else {}
        offer = props.get("offer")
        if isinstance(offer, dict):
            parsed = _job_from_inertia_offer(url, offer)
            if parsed is not None:
                return parsed

    return _parse_legacy_offer_detail(url, html)


def _job_from_inertia_offer(url: str, offer: dict[str, Any]) -> JobPosting | None:
    source_id = _as_identifier(offer.get("id")) or _source_id_from_url(url)
    rspo = offer.get("rspo")
    rspo = rspo if isinstance(rspo, dict) else {}
    position_category = offer.get("position_category")
    position_category = position_category if isinstance(position_category, dict) else {}

    title = _first_text(
        offer.get("position_category_name"),
        position_category.get("name"),
        _nested_name(offer, "subject"),
        _nested_name(offer, "profession"),
        _nested_name(offer, "employee_type"),
    )
    company_name = _first_text(rspo.get("name"))
    if not source_id or not title or not company_name:
        return None

    city = _first_text(rspo.get("city"), rspo.get("post_office"), rspo.get("commune"))
    websites = _website_candidates_from_offer(offer)
    emails = _recruitment_emails_from_offer(offer)
    phones = _recruitment_phones_from_offer(offer)
    description = _offer_description(offer)
    official_id = _first_text(offer.get("reference"))

    return JobPosting(
        source="ofertypracyedu",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="ofertypracyedu.inertia.offer.rspo.name",
        company_name_confidence=0.99,
        company_website_candidates=websites,
        city=city,
        description=description,
        published_at=_first_text(offer.get("published_at")),
        source_payload={
            "portal_offer_id": source_id,
            "official_offer_id": official_id,
            "public_inertia_offer": offer,
            "recruitment_emails": emails,
            "recruitment_phones": phones,
            "company_website_candidates": [item.url for item in websites],
            "deadline_for_submission_of_documents": _first_text(
                offer.get("deadline_for_submission_of_documents")
            ),
        },
    )


def _parse_legacy_offer_detail(url: str, html: str) -> JobPosting | None:
    soup = BeautifulSoup(html, "html.parser")
    title = _heading_text(soup, "h3")
    company_name = _company_heading(soup)
    source_id = _source_id_from_url(url)
    if not title or not company_name or not source_id:
        return None

    visible_text = "\n".join(text.strip() for text in soup.stripped_strings if text.strip())
    official_id_match = _OFFICIAL_ID.search(visible_text)
    official_id = official_id_match.group(1) if official_id_match else None
    city = _city_from_text(visible_text)
    websites = _company_websites(soup)
    emails = _unique(_EMAIL.findall(visible_text))
    phones = _unique(match.group(0).strip() for match in _PHONE.finditer(visible_text))

    return JobPosting(
        source="ofertypracyedu",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="ofertypracyedu.detail.heading",
        company_name_confidence=0.99,
        company_website_candidates=websites,
        city=city,
        description=visible_text,
        source_payload={
            "portal_offer_id": source_id,
            "official_offer_id": official_id,
            "visible_text": visible_text,
            "recruitment_emails": emails,
            "recruitment_phones": phones,
            "company_website_candidates": [item.url for item in websites],
        },
    )


def _inertia_payload(html: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    app = soup.select_one("#app[data-page]")
    if app is None:
        return None
    raw = str(app.get("data-page") or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(html_module.unescape(raw))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _offer_description(offer: dict[str, Any]) -> str | None:
    parts: list[str] = []
    fields = (
        "job_description",
        "requirements",
        "responsibilities",
        "offer",
        "required_documents",
        "additional_documents",
        "contact",
    )
    for field in fields:
        value = _first_text(offer.get(field))
        if value and value not in parts:
            parts.append(value)
    return "\n\n".join(parts) if parts else None


def _recruitment_emails_from_offer(offer: dict[str, Any]) -> list[str]:
    rspo = offer.get("rspo")
    rspo = rspo if isinstance(rspo, dict) else {}
    values = [
        offer.get("required_application_documents_to"),
        offer.get("contact"),
        rspo.get("email"),
    ]
    matches: list[str] = []
    for value in values:
        text = _first_text(value)
        if text:
            matches.extend(_EMAIL.findall(text))
    return _unique(matches)


def _recruitment_phones_from_offer(offer: dict[str, Any]) -> list[str]:
    rspo = offer.get("rspo")
    rspo = rspo if isinstance(rspo, dict) else {}
    values = [rspo.get("phone_number"), rspo.get("phone_number_2"), offer.get("contact")]
    matches: list[str] = []
    for value in values:
        text = _first_text(value)
        if not text:
            continue
        found = [match.group(0).strip() for match in _PHONE.finditer(text)]
        if found:
            matches.extend(found)
        elif re.sub(r"\D", "", text):
            matches.append(text)
    return _unique(matches)


def _website_candidates_from_offer(
    offer: dict[str, Any],
) -> list[CompanyWebsiteCandidate]:
    rspo = offer.get("rspo")
    rspo = rspo if isinstance(rspo, dict) else {}
    output: list[CompanyWebsiteCandidate] = []
    seen: set[str] = set()

    candidates = (
        (rspo.get("website"), "ofertypracyedu.inertia.offer.rspo.website", 0.90),
        (
            offer.get("sample_statements_available_at"),
            "ofertypracyedu.inertia.offer.sample_statements_available_at",
            0.70,
        ),
    )
    for raw, source, confidence in candidates:
        normalized = _normalize_public_url(raw)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        output.append(
            CompanyWebsiteCandidate(
                url=normalized,
                source=source,
                confidence=confidence,
            )
        )
    return output


def _normalize_public_url(value: object) -> str | None:
    text = _first_text(value)
    if not text:
        return None
    if not text.startswith(("http://", "https://")):
        text = "https://" + text.lstrip("/")
    parsed = urlparse(text)
    if not parsed.netloc:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


def _nested_name(offer: dict[str, Any], key: str) -> object:
    value = offer.get(key)
    return value.get("name") if isinstance(value, dict) else None


def _first_text(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _as_identifier(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, str)):
        text = str(value).strip()
        return text or None
    return None


def _as_positive_int(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _page_from_listing_url(url: str) -> int:
    for key, value in httpx.QueryParams(urlparse(url).query).multi_items():
        if key == "page":
            parsed = _as_positive_int(value)
            if parsed is not None:
                return parsed
    return 1


def _heading_text(soup: BeautifulSoup, tag: str) -> str | None:
    node = soup.find(tag)
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _company_heading(soup: BeautifulSoup) -> str | None:
    node = soup.find("h4")
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    text = re.sub(r"\s*\(Szczegóły placówki\)\s*$", "", text, flags=re.IGNORECASE)
    return text.strip() or None


def _source_id_from_url(url: str) -> str | None:
    match = _OFFER_PATH.match(urlparse(url).path)
    return match.group(1) if match else None


def _city_from_text(text: str) -> str | None:
    match = _POSTAL_CITY.search(text)
    if match is None:
        return None
    city = match.group(1).strip()
    return city or None


def _company_websites(soup: BeautifulSoup) -> list[CompanyWebsiteCandidate]:
    portal_host = urlparse(BASE_URL).netloc.lower()
    output: list[CompanyWebsiteCandidate] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        raw = str(anchor.get("href") or "").strip()
        if not raw.startswith(("http://", "https://")):
            continue
        parsed = urlparse(raw)
        if not parsed.netloc or parsed.netloc.lower() == portal_host:
            continue
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, "")
        )
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(
            CompanyWebsiteCandidate(
                url=normalized,
                source="ofertypracyedu.detail.external_link",
                confidence=0.80,
            )
        )
    return output


def _unique(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
