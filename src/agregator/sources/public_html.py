from __future__ import annotations

import asyncio
import json
import re
import urllib.robotparser
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import CompanyIdentifier, CompanyWebsiteCandidate, JobPosting
from .base import SourceBatch


@dataclass(frozen=True, slots=True)
class HtmlJobSourceConfig:
    name: str
    base_url: str
    listing_url_template: str
    offer_path_patterns: tuple[str, ...]
    paginated: bool = True
    start_page: int = 1
    max_offer_links: int = 50
    title_selectors: tuple[str, ...] = ("h1",)
    company_selectors: tuple[str, ...] = ()
    city_selectors: tuple[str, ...] = ()
    description_selectors: tuple[str, ...] = ("main", "article")


class PublicHtmlJobSource:
    """Reusable public HTML collector with robots, rate limiting and bounded retries."""

    def __init__(
        self,
        config: HtmlJobSourceConfig,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = "FaroEmployerDiscovery/0.2",
        request_delay: float = 0.8,
        max_retries: int = 2,
    ) -> None:
        self.config = config
        self.name = config.name
        self._client = client
        self.user_agent = user_agent
        self.request_delay = max(0.0, request_delay)
        self.max_retries = max(0, max_retries)
        self._robots: urllib.robotparser.RobotFileParser | None = None

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        page = self._parse_cursor(cursor)
        listing_url = self.config.listing_url_template.format(page=page)
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
            links = extract_offer_links(listing_url, listing_html, self.config)
            links = links[: self.config.max_offer_links]

            jobs: list[JobPosting] = []
            for index, url in enumerate(links):
                await self._assert_allowed(client, url)
                if index and self.request_delay:
                    await asyncio.sleep(self.request_delay)
                try:
                    detail_html = await self._get_text(client, url)
                except httpx.HTTPError:
                    continue
                job = parse_job_detail_html(self.config, url, detail_html)
                if job is not None:
                    jobs.append(job)
        finally:
            if owns_client:
                await client.aclose()

        next_cursor = str(page + 1) if self.config.paginated and links else None
        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    def _parse_cursor(self, cursor: str | None) -> int:
        if cursor is None:
            return self.config.start_page
        try:
            page = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid {self.name} page cursor: {cursor}") from exc
        if page < self.config.start_page:
            raise ValueError(f"{self.name} page cursor must be >= {self.config.start_page}")
        return page

    async def _assert_allowed(self, client: httpx.AsyncClient, url: str) -> None:
        if self._robots is None:
            parsed = urlparse(self.config.base_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
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
            raise PermissionError(f"robots.txt disallows {self.name} URL: {url}")

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


def extract_offer_links(
    listing_url: str,
    html: str,
    config: HtmlJobSourceConfig,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    expected_host = urlparse(config.base_url).netloc.lower()
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in config.offer_path_patterns]
    output: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        raw = str(anchor.get("href") or "").strip()
        if not raw:
            continue
        absolute = _normalize_url(urljoin(listing_url, raw))
        parsed = urlparse(absolute)
        if parsed.netloc.lower() != expected_host:
            continue
        decoded_path = unquote(parsed.path)
        if not any(pattern.search(decoded_path) for pattern in patterns):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        output.append(absolute)
    return output


def parse_job_detail_html(
    config: HtmlJobSourceConfig,
    url: str,
    html: str,
) -> JobPosting | None:
    soup = BeautifulSoup(html, "html.parser")
    structured = _find_job_posting_jsonld(soup)
    if structured is not None:
        job = _job_from_jsonld(config, url, structured)
        if job is not None:
            return job
    return _job_from_html_fallback(config, url, soup)


def _find_job_posting_jsonld(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _find_typed_object(payload, "JobPosting")
        if found is not None:
            return found
    return None


def _find_typed_object(value: Any, expected_type: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        raw_type = value.get("@type")
        if raw_type == expected_type:
            return value
        if isinstance(raw_type, list) and expected_type in raw_type:
            return value
        for child in value.values():
            found = _find_typed_object(child, expected_type)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_typed_object(child, expected_type)
            if found is not None:
                return found
    return None


def _job_from_jsonld(
    config: HtmlJobSourceConfig,
    url: str,
    payload: dict[str, Any],
) -> JobPosting | None:
    title = _text(payload.get("title"))
    organization = payload.get("hiringOrganization")
    company_name = _text(organization.get("name")) if isinstance(organization, dict) else None
    if not title or not company_name:
        return None

    identifiers = _company_identifiers(organization)
    websites = _company_websites(organization)
    description = _html_to_text(_text(payload.get("description")))
    source_id = _job_identifier(payload) or url

    return JobPosting(
        source=config.name,
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source="jsonld.hiringOrganization.name",
        company_name_confidence=0.99,
        company_identifiers=identifiers,
        company_website_candidates=websites,
        city=_job_city(payload),
        description=description,
        published_at=_text(payload.get("datePosted")),
        source_payload={"json_ld_job_posting": payload},
    )


def _job_from_html_fallback(
    config: HtmlJobSourceConfig,
    url: str,
    soup: BeautifulSoup,
) -> JobPosting | None:
    title = _first_selector_text(soup, config.title_selectors)
    company_name = _first_selector_text(soup, config.company_selectors)
    if not title or not company_name:
        return None

    city = _first_selector_text(soup, config.city_selectors)
    description = _first_selector_text(soup, config.description_selectors)
    canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    canonical_url = _text(canonical.get("href")) if canonical is not None else None
    final_url = _normalize_url(urljoin(url, canonical_url)) if canonical_url else url

    return JobPosting(
        source=config.name,
        source_id=final_url,
        url=final_url,
        title=title,
        company_name=company_name,
        company_name_source="html.selector",
        company_name_confidence=0.80,
        city=city,
        description=description,
        source_payload={
            "html_fallback": {
                "canonical_url": canonical_url,
                "title": title,
                "company_name": company_name,
                "city": city,
            }
        },
    )


def _company_identifiers(organization: Any) -> list[CompanyIdentifier]:
    if not isinstance(organization, dict):
        return []
    candidates: list[Any] = []
    raw_identifier = organization.get("identifier")
    if isinstance(raw_identifier, list):
        candidates.extend(raw_identifier)
    elif raw_identifier is not None:
        candidates.append(raw_identifier)
    for key in ("taxID", "vatID"):
        if organization.get(key):
            candidates.append({"propertyID": key, "value": organization.get(key)})

    output: list[CompanyIdentifier] = []
    for item in candidates:
        if isinstance(item, str):
            label = "organization_id"
            value = item
        elif isinstance(item, dict):
            label_text = " ".join(
                str(item.get(key) or "") for key in ("propertyID", "name", "@type")
            ).lower()
            if "nip" in label_text or "vat" in label_text or "tax" in label_text:
                label = "nip"
            elif "regon" in label_text:
                label = "regon"
            elif "krs" in label_text:
                label = "krs"
            else:
                label = "organization_id"
            value = _text(item.get("value")) or _text(item.get("@id"))
        else:
            continue
        cleaned = _text(value)
        if cleaned:
            output.append(
                CompanyIdentifier(
                    kind=label,
                    value=cleaned,
                    source="jsonld.hiringOrganization.identifier",
                    confidence=0.95,
                )
            )
    return output


def _company_websites(organization: Any) -> list[CompanyWebsiteCandidate]:
    if not isinstance(organization, dict):
        return []
    values: list[tuple[str, str]] = []
    for key in ("url", "sameAs"):
        raw = organization.get(key)
        if isinstance(raw, list):
            values.extend((str(item), key) for item in raw if item)
        elif raw:
            values.append((str(raw), key))

    output: list[CompanyWebsiteCandidate] = []
    seen: set[str] = set()
    for raw_url, key in values:
        candidate = raw_url.strip()
        if not candidate.startswith(("http://", "https://")):
            continue
        candidate = _normalize_url(candidate)
        if candidate in seen:
            continue
        seen.add(candidate)
        output.append(
            CompanyWebsiteCandidate(
                url=candidate,
                source=f"jsonld.hiringOrganization.{key}",
                confidence=0.90,
            )
        )
    return output


def _job_city(payload: dict[str, Any]) -> str | None:
    locations = payload.get("jobLocation")
    if not isinstance(locations, list):
        locations = [locations]
    fallback: str | None = None
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if not isinstance(address, dict):
            continue
        city = _text(address.get("addressLocality"))
        if city:
            return city
        for key in ("addressRegion", "addressCountry"):
            value = _text(address.get(key))
            if value and fallback is None:
                fallback = value
    if fallback:
        return fallback
    if str(payload.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        return "Remote"
    return None


def _job_identifier(payload: dict[str, Any]) -> str | None:
    identifier = payload.get("identifier")
    if isinstance(identifier, dict):
        return _text(identifier.get("value")) or _text(identifier.get("@id"))
    return _text(identifier)


def _first_selector_text(soup: BeautifulSoup, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is not None:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return None


def _html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    soup = BeautifulSoup(unescape(value), "html.parser")
    text = soup.get_text("\n", strip=True)
    return text or None


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
