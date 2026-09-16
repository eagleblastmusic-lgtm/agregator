from __future__ import annotations

import asyncio
import hashlib
import html as html_lib
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..models import JobPosting
from .base import SourceBatch

OLX_BASE_URL = "https://www.olx.pl"
OLX_JOBS_URL = f"{OLX_BASE_URL}/praca/"
OLX_PAGE_CAP = 25
OLX_FULL_CATALOG_MAX_BATCHES = 50_000

OLX_PRIMARY_CATEGORY_SLUGS = (
    "administracja-biurowa",
    "badania-rozwoj",
    "bankowosc",
    "bhp-ochrona-srodowiska",
    "budowa-remonty",
    "dostawca-kurier-miejski",
    "e-commerce-handel-internetowy",
    "edukacja",
    "energetyka",
    "finanse-ksiegowosc",
    "franczyza-wlasna-firma",
    "fryzjerstwo-kosmetyka",
    "gastronomia",
    "hr",
    "hostessa-roznoszenie-ulotek",
    "hotelarstwo",
    "inzynieria",
    "informatyka",
    "kierowca",
    "logistyka-zakupy-spedycja",
    "marketing-pr",
    "mechanika-lakiernictwo",
    "montaz-serwis",
    "nieruchomosci",
    "obsluga-klienta-call-center",
    "ochrona",
    "opieka",
    "organizacja-obsluga-impres",
    "praca-za-granica",
    "prace-magazynowe",
    "pracownik-sklepu",
    "prawo",
    "produkcja",
    "rolnictwo-i-ogrodnictwo",
    "sprzatanie",
    "sprzedaz",
    "ubezpieczenia",
    "wykladanie-ekspozycja-towaru",
    "zdrowie",
    "inne-oferty-pracy",
)

OLX_REGION_SLUGS = (
    "dolnoslaskie",
    "kujawsko-pomorskie",
    "lubelskie",
    "lubuskie",
    "lodzkie",
    "malopolskie",
    "mazowieckie",
    "opolskie",
    "podkarpackie",
    "podlaskie",
    "pomorskie",
    "slaskie",
    "swietokrzyskie",
    "warminsko-mazurskie",
    "wielkopolskie",
    "zachodniopomorskie",
)

_PRERENDERED_RE = re.compile(
    r'window\.__PRERENDERED_STATE__\s*=\s*("(?:\\.|[^"\\])*")\s*;',
    re.DOTALL,
)
_OFFER_ID_RE = re.compile(r"-ID([A-Za-z0-9]+)\.html", re.IGNORECASE)


@dataclass(slots=True)
class ParsedOlxPage:
    jobs: list[JobPosting]
    total_count: int | None
    total_pages: int | None
    child_shards: list[str]


class OlxPublicSource:
    """Collect public OLX Praca listing pages without using blocked/private endpoints."""

    name = "olx"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str | None = None,
        request_delay: float | None = None,
    ) -> None:
        self._external_client = client
        self._owned_client: httpx.AsyncClient | None = None
        self.user_agent = (
            user_agent
            or os.getenv("AGREGATOR_USER_AGENT")
            or "FaroEmployerDiscovery/0.1 (+public-job-aggregation)"
        )
        if request_delay is None:
            raw_delay = os.getenv("AGREGATOR_REQUEST_DELAY", "0.8")
            try:
                request_delay = float(raw_delay)
            except ValueError:
                request_delay = 0.8
        self.request_delay = max(0.0, request_delay)
        self._last_request_at: float | None = None
        self._seen_job_keys: set[str] = set()

    async def collect(self, cursor: str | None = None) -> SourceBatch:
        index, page, extra_shards = _decode_cursor(cursor)
        queue = list(_initial_shards())
        for shard in extra_shards:
            if shard not in queue:
                queue.append(shard)

        if index >= len(queue):
            await self._close_owned_client()
            return SourceBatch(jobs=[], next_cursor=None)

        shard_url = queue[index]
        page_url = _with_page(shard_url, page)
        response = await self._get(page_url)
        parsed = parse_olx_html(response.text, page_url=page_url)

        if page == 1 and _needs_split(parsed):
            known = set(queue)
            for child in parsed.child_shards:
                if child not in known:
                    queue.append(child)
                    known.add(child)

        jobs: list[JobPosting] = []
        for job in parsed.jobs:
            key = job.source_id or job.url
            if key in self._seen_job_keys:
                continue
            self._seen_job_keys.add(key)
            jobs.append(job)

        next_index = index
        next_page = page
        page_limit = _effective_page_limit(parsed)
        if parsed.jobs and page < page_limit:
            next_page += 1
        else:
            next_index += 1
            next_page = 1

        if next_index >= len(queue):
            await self._close_owned_client()
            next_cursor = None
        else:
            next_cursor = _encode_cursor(
                next_index,
                next_page,
                queue[len(_initial_shards()) :],
            )

        return SourceBatch(jobs=jobs, next_cursor=next_cursor)

    async def _get(self, url: str) -> httpx.Response:
        await self._respect_delay()
        client = self._external_client or await self._owned()
        response = await client.get(url)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", "").lower():
            raise RuntimeError(
                "OLX public jobs route did not return HTML; refusing a silent schema fallback."
            )
        return response

    async def _owned(self) -> httpx.AsyncClient:
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "pl-PL,pl;q=0.9",
                    "User-Agent": self.user_agent,
                },
            )
        return self._owned_client

    async def _respect_delay(self) -> None:
        if self._last_request_at is None or self.request_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.request_delay - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _close_owned_client(self) -> None:
        if self._owned_client is None:
            return
        await self._owned_client.aclose()
        self._owned_client = None


def parse_olx_html(html: str, *, page_url: str = OLX_JOBS_URL) -> ParsedOlxPage:
    listing = _extract_prerendered_listing(html)
    if listing is not None:
        jobs = _jobs_from_prerendered(listing, page_url=page_url)
        total_count = _as_int(
            listing.get("visibleTotalCount", listing.get("totalElements"))
        )
        total_pages = _as_int(listing.get("totalPages"))
    else:
        jobs, total_count = _jobs_from_dom(html, page_url=page_url)
        total_pages = _dom_total_pages(html)

    category = _category_from_url(page_url)
    child_shards = (
        _discover_child_shards(html, category=category, current_url=page_url)
        if category
        else []
    )

    if total_count and total_count > 0 and not jobs:
        raise RuntimeError(
            "OLX returned a non-empty jobs listing but Faro could not parse any offer cards."
        )

    return ParsedOlxPage(
        jobs=jobs,
        total_count=total_count,
        total_pages=total_pages,
        child_shards=child_shards,
    )


def _extract_prerendered_listing(html: str) -> Mapping[str, Any] | None:
    match = _PRERENDERED_RE.search(html)
    if match is None:
        return None
    try:
        encoded = json.loads(match.group(1))
        state = json.loads(encoded) if isinstance(encoded, str) else encoded
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(state, Mapping):
        return None
    listing_container = state.get("listing")
    if not isinstance(listing_container, Mapping):
        return None
    listing = listing_container.get("listing")
    return listing if isinstance(listing, Mapping) else None


def _jobs_from_prerendered(
    listing: Mapping[str, Any],
    *,
    page_url: str,
) -> list[JobPosting]:
    raw_ads = listing.get("ads")
    if not isinstance(raw_ads, list):
        return []
    jobs: list[JobPosting] = []
    for raw in raw_ads:
        if not isinstance(raw, Mapping):
            continue
        job = _job_from_prerendered_ad(raw, page_url=page_url)
        if job is not None:
            jobs.append(job)
    return _dedupe_jobs(jobs)


def _job_from_prerendered_ad(
    raw: Mapping[str, Any],
    *,
    page_url: str,
) -> JobPosting | None:
    source_id = _string(raw.get("id"))
    title = _string(raw.get("title"))
    url = _absolute_url(_string(raw.get("url")))
    if not source_id or not title or not url:
        return None

    company_name, company_source, company_confidence = _prerendered_company(raw, source_id)
    location = raw.get("location")
    city = None
    if isinstance(location, Mapping):
        city = _string(location.get("cityName"))
        if not city:
            path_name = _string(location.get("pathName"))
            city = path_name.split(",")[0].strip() if path_name else None

    return JobPosting(
        source="olx",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source=company_source,
        company_name_confidence=company_confidence,
        city=city,
        description=_clean_text(_string(raw.get("description"))),
        published_at=_string(raw.get("createdTime")),
        refreshed_at=_string(raw.get("lastRefreshTime")),
        source_payload={
            "collection_mode": "public_html_prerendered",
            "listing_page": page_url,
        },
    )


def _prerendered_company(
    raw: Mapping[str, Any],
    source_id: str,
) -> tuple[str, str, float]:
    candidates: list[tuple[str | None, str, float]] = [
        (_nested_string(raw, "company", "name"), "company.name", 0.98),
        (_string(raw.get("companyName")), "companyName", 0.96),
        (_string(raw.get("businessName")), "businessName", 0.95),
        (_nested_string(raw, "user", "companyName"), "user.companyName", 0.95),
        (_nested_string(raw, "employer", "name"), "employer.name", 0.95),
        (_nested_string(raw, "contact", "name"), "contact.name", 0.55),
        (_nested_string(raw, "user", "name"), "user.name", 0.45),
    ]
    for value, source, confidence in candidates:
        if value:
            return value, source, confidence
    return (
        f"Nieujawniony pracodawca OLX #{source_id}",
        "olx.identity_not_public",
        0.0,
    )


def _jobs_from_dom(html: str, *, page_url: str) -> tuple[list[JobPosting], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('[data-cy="l-card"], [data-testid="l-card"]')
    jobs: list[JobPosting] = []

    for card in cards:
        link = card.select_one(
            'a[href*="/d/oferta/"], a[href*="/oferta/"], '
            '[data-testid="ad-card-title"] a[href]'
        )
        href = _string(link.get("href")) if link else None
        url = _absolute_url(href)
        if not url:
            continue

        title_node = card.select_one(
            '[data-testid="ad-card-title"] h4, '
            '[data-testid="ad-card-title"] h6, '
            '[data-cy="ad-card-title"] h4, '
            '[data-cy="ad-card-title"] h6, '
            "h4, h6"
        )
        title = title_node.get_text(" ", strip=True) if title_node else None
        if not title:
            continue

        source_id = _offer_id_from_url(url) or _string(card.get("id"))
        if not source_id:
            source_id = _stable_source_id(url)

        company_node = card.select_one(
            '[data-testid*="company"], [data-cy*="company"], '
            '[data-testid*="employer"], [data-cy*="employer"]'
        )
        company = company_node.get_text(" ", strip=True) if company_node else ""
        if company:
            company_name = company
            company_source = "listing_card.company"
            confidence = 0.75
        else:
            company_name = f"Nieujawniony pracodawca OLX #{source_id}"
            company_source = "olx.identity_not_public"
            confidence = 0.0

        location_node = card.select_one('[data-testid="location-date"]')
        location_text = location_node.get_text(" ", strip=True) if location_node else ""
        city = location_text.split(" - ", 1)[0].strip() or None

        jobs.append(
            JobPosting(
                source="olx",
                source_id=source_id,
                url=url,
                title=title,
                company_name=company_name,
                company_name_source=company_source,
                company_name_confidence=confidence,
                city=city,
                source_payload={
                    "collection_mode": "public_html_dom",
                    "listing_page": page_url,
                },
            )
        )

    total_node = soup.select_one('[data-testid="total-count"]')
    total_count = _first_int(total_node.get_text(" ", strip=True)) if total_node else None
    if total_count is None:
        total_count = _first_int(
            soup.get_text(" ", strip=True),
            marker="Znaleźliśmy",
        )
    return _dedupe_jobs(jobs), total_count


def _dom_total_pages(html: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    pages: list[int] = []
    for link in soup.select('a[href*="page="]'):
        text = link.get_text(" ", strip=True)
        if text.isdigit():
            pages.append(int(text))
        href = _string(link.get("href"))
        if href:
            match = re.search(r"(?:\?|&)page=(\d+)", href)
            if match:
                pages.append(int(match.group(1)))
    return max(pages) if pages else None


def _discover_child_shards(
    html: str,
    *,
    category: str,
    current_url: str,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    current_path = _normalized_path(current_url)
    prefix = f"/praca/{category}/"
    children: list[str] = []
    seen: set[str] = set()

    for link in soup.select("a[href]"):
        href = _string(link.get("href"))
        if not href:
            continue
        absolute = _absolute_url(href)
        if not absolute:
            continue
        parsed = urlparse(absolute)
        path = parsed.path.rstrip("/") + "/"
        if not path.startswith(prefix):
            continue
        if path == current_path:
            continue
        suffix = path[len(prefix) :].strip("/")
        if not suffix or suffix.startswith("q-"):
            continue
        if any(part.startswith("page-") for part in suffix.split("/")):
            continue
        canonical = urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
        if canonical in seen:
            continue
        seen.add(canonical)
        children.append(canonical)

    return children


def _needs_split(page: ParsedOlxPage) -> bool:
    if page.total_count is not None and page.total_count >= 1000:
        return True
    return page.total_pages is not None and page.total_pages >= OLX_PAGE_CAP


def _effective_page_limit(page: ParsedOlxPage) -> int:
    if page.total_pages is None:
        return OLX_PAGE_CAP
    return max(1, min(page.total_pages, OLX_PAGE_CAP))


def _initial_shards() -> tuple[str, ...]:
    return tuple(
        f"{OLX_BASE_URL}/praca/{category}/{region}/"
        for category in OLX_PRIMARY_CATEGORY_SLUGS
        for region in OLX_REGION_SLUGS
    )


def _encode_cursor(index: int, page: int, extra_shards: list[str]) -> str:
    return json.dumps(
        {"v": 1, "i": index, "p": page, "extra": extra_shards},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode_cursor(cursor: str | None) -> tuple[int, int, list[str]]:
    if not cursor:
        return 0, 1, []
    try:
        payload = json.loads(cursor)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid OLX cursor") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("invalid OLX cursor")
    index = _as_int(payload.get("i"))
    page = _as_int(payload.get("p"))
    extra = payload.get("extra", [])
    if index is None or index < 0 or page is None or page < 1:
        raise ValueError("invalid OLX cursor")
    if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
        raise ValueError("invalid OLX cursor")
    return index, page, list(extra)


def _with_page(url: str, page: int) -> str:
    if page <= 1:
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _category_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/").split("/")
    if len(path) < 2 or path[0] != "praca":
        return None
    category = path[1]
    return category if category in OLX_PRIMARY_CATEGORY_SLUGS else None


def _normalized_path(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path + "/"


def _absolute_url(url: str | None) -> str | None:
    if not url:
        return None
    return urljoin(OLX_BASE_URL, url)


def _offer_id_from_url(url: str) -> str | None:
    match = _OFFER_ID_RE.search(url)
    return match.group(1) if match else None


def _stable_source_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _nested_string(raw: Mapping[str, Any], parent: str, key: str) -> str | None:
    value = raw.get(parent)
    if not isinstance(value, Mapping):
        return None
    return _string(value.get(key))


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text).strip()
    return text or None


def _dedupe_jobs(jobs: list[JobPosting]) -> list[JobPosting]:
    result: list[JobPosting] = []
    seen: set[str] = set()
    for job in jobs:
        key = job.source_id or job.url
        if key in seen:
            continue
        seen.add(key)
        result.append(job)
    return result


def _first_int(text: str, *, marker: str | None = None) -> int | None:
    if marker:
        index = text.find(marker)
        if index >= 0:
            text = text[index + len(marker) :]
    match = re.search(r"(\d[\d\s\xa0]*)", text)
    if not match:
        return None
    return int(re.sub(r"\s|\xa0", "", match.group(1)))


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Backward-compatible parser for recorded legacy/API fixtures. Runtime collection no
# longer depends on the endpoint because the public HTML catalog is the primary path.
def parse_olx_payload(payload: Mapping[str, Any]) -> list[JobPosting]:
    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []

    jobs: list[JobPosting] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        job = _parse_api_offer(raw)
        if job is not None:
            jobs.append(job)
    return jobs


def _parse_api_offer(raw: Mapping[str, Any]) -> JobPosting | None:
    source_id = _string(raw.get("id"))
    title = _string(raw.get("title"))
    url = _absolute_url(_string(raw.get("url")))
    if not source_id or not title or not url:
        return None

    company_name, company_source, company_confidence = _api_company_name(raw)
    if not company_name:
        return None

    location = raw.get("location")
    city = None
    if isinstance(location, Mapping):
        raw_city = location.get("city")
        if isinstance(raw_city, Mapping):
            city = _string(raw_city.get("name"))
        elif isinstance(raw_city, str):
            city = raw_city.strip() or None

    return JobPosting(
        source="olx",
        source_id=source_id,
        url=url,
        title=title,
        company_name=company_name,
        company_name_source=company_source,
        company_name_confidence=company_confidence,
        city=city,
        description=_string(raw.get("description")),
        published_at=_string(raw.get("created_time")),
        refreshed_at=_string(raw.get("last_refresh_time")),
    )


def _api_company_name(raw: Mapping[str, Any]) -> tuple[str | None, str | None, float]:
    candidates: list[tuple[str | None, str, float]] = []

    company = raw.get("company")
    if isinstance(company, Mapping):
        candidates.append((_string(company.get("name")), "company.name", 0.98))

    user = raw.get("user")
    if isinstance(user, Mapping):
        candidates.append((_string(user.get("company_name")), "user.company_name", 0.95))

    partner = raw.get("partner")
    if isinstance(partner, Mapping):
        candidates.append((_string(partner.get("name")), "partner.name", 0.90))

    if isinstance(user, Mapping):
        candidates.append((_string(user.get("name")), "user.name", 0.45))

    contact = raw.get("contact")
    if isinstance(contact, Mapping):
        candidates.append((_string(contact.get("name")), "contact.name", 0.30))

    for value, source, confidence in candidates:
        if value:
            return value, source, confidence
    return None, None, 0.0
