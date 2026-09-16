from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .crawler import CrawlPage
from .normalize import normalize_company_name, normalize_text

GENERIC_COMPANY_TOKENS = {
    "firma",
    "company",
    "group",
    "grupa",
    "polska",
    "service",
    "services",
}
ORGANIZATION_TYPES = {
    "organization",
    "corporation",
    "localbusiness",
    "professionalservice",
    "store",
}


@dataclass(frozen=True, slots=True)
class WebsiteVerification:
    accepted: bool
    score: float
    search_score: float
    content_score: float
    name_coverage: float
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["signals"] = list(self.signals)
        return payload


@dataclass(frozen=True, slots=True)
class StructuredOrganizationEvidence:
    names: tuple[str, ...]
    urls: tuple[str, ...]
    cities: tuple[str, ...]
    has_tax_id: bool


def verify_company_website(
    company_name: str,
    city: str | None,
    website_url: str,
    pages: list[CrawlPage],
    *,
    search_score: float,
    minimum_score: float = 0.55,
) -> WebsiteVerification:
    """Verify a search-selected domain against crawled first-party content.

    Search ranking alone is not treated as proof. Automatic acceptance requires
    both a combined score and an identity signal from the crawled website.
    """

    if not pages:
        return WebsiteVerification(
            accepted=False,
            score=round(0.35 * search_score, 4),
            search_score=round(search_score, 4),
            content_score=0.0,
            name_coverage=0.0,
            signals=("no_crawlable_pages",),
        )

    normalized_name = normalize_company_name(company_name)
    company_tokens = {
        token
        for token in normalized_name.split()
        if len(token) >= 3 and token not in GENERIC_COMPANY_TOKENS
    }
    if not company_tokens:
        company_tokens = {token for token in normalized_name.split() if len(token) >= 2}

    page_texts = [_page_text(page) for page in pages]
    combined_text = " ".join(page_texts)
    text_tokens = set(combined_text.split())
    matched_tokens = company_tokens & text_tokens
    coverage = len(matched_tokens) / len(company_tokens) if company_tokens else 0.0

    exact_name = bool(normalized_name and normalized_name in combined_text)
    host_match = _host_matches_company(website_url, company_tokens)
    normalized_city = normalize_text(city or "")
    city_match = bool(normalized_city and normalized_city in combined_text)

    structured = _structured_organization_evidence(pages)
    structured_name_match = _structured_name_matches(
        structured.names,
        normalized_name,
        company_tokens,
    )
    structured_host_match = any(
        _website_host(url) == _website_host(website_url)
        for url in structured.urls
        if url
    )
    structured_city_match = bool(
        normalized_city
        and any(normalized_city == normalize_text(value) for value in structured.cities)
    )

    content_score = 0.0
    signals: list[str] = []
    if exact_name:
        content_score += 0.48
        signals.append("exact_normalized_company_name")
    if coverage:
        content_score += 0.34 * coverage
        signals.append(f"company_token_coverage:{coverage:.3f}")
    if host_match:
        content_score += 0.12
        signals.append("company_token_in_host")
    if city_match:
        content_score += 0.06
        signals.append("city_on_website")
    if structured_name_match:
        content_score += 0.20
        signals.append("jsonld_organization_name")
    if structured_host_match:
        content_score += 0.05
        signals.append("jsonld_organization_url")
    if structured_city_match:
        content_score += 0.03
        signals.append("jsonld_address_city")
    if structured.has_tax_id:
        signals.append("jsonld_tax_id_present")

    content_score = min(content_score, 1.0)
    final_score = min((0.42 * search_score) + (0.58 * content_score), 1.0)

    strong_identity_signal = (
        exact_name
        or structured_name_match
        or coverage >= 0.7
        or (host_match and coverage >= 0.5)
    )
    accepted = final_score >= minimum_score and strong_identity_signal
    signals.append("accepted" if accepted else "identity_not_confirmed")

    return WebsiteVerification(
        accepted=accepted,
        score=round(final_score, 4),
        search_score=round(search_score, 4),
        content_score=round(content_score, 4),
        name_coverage=round(coverage, 4),
        signals=tuple(signals),
    )


def _page_text(page: CrawlPage) -> str:
    soup = BeautifulSoup(page.html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    text = " ".join(soup.stripped_strings)
    return normalize_text(text[:200_000])


def _host_matches_company(url: str, company_tokens: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    compact_host = normalize_text(host).replace(" ", "")
    return any(len(token) >= 4 and token in compact_host for token in company_tokens)


def _structured_organization_evidence(
    pages: list[CrawlPage],
) -> StructuredOrganizationEvidence:
    names: set[str] = set()
    urls: set[str] = set()
    cities: set[str] = set()
    has_tax_id = False

    for page in pages:
        soup = BeautifulSoup(page.html, "html.parser")
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text(" ", strip=True)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            for item in _iter_jsonld_objects(payload):
                if not _is_organization_object(item):
                    continue
                for key in ("name", "legalName", "alternateName"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        names.add(value.strip())
                value = item.get("url")
                if isinstance(value, str) and value.strip():
                    urls.add(value.strip())
                address = item.get("address")
                if isinstance(address, dict):
                    locality = address.get("addressLocality")
                    if isinstance(locality, str) and locality.strip():
                        cities.add(locality.strip())
                if _has_tax_identifier(item):
                    has_tax_id = True

    return StructuredOrganizationEvidence(
        names=tuple(sorted(names)),
        urls=tuple(sorted(urls)),
        cities=tuple(sorted(cities)),
        has_tax_id=has_tax_id,
    )


def _iter_jsonld_objects(value: Any) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    if isinstance(value, dict):
        objects.append(value)
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                objects.extend(_iter_jsonld_objects(item))
    elif isinstance(value, list):
        for item in value:
            objects.extend(_iter_jsonld_objects(item))
    return objects


def _is_organization_object(value: dict[str, Any]) -> bool:
    raw_type = value.get("@type")
    if isinstance(raw_type, str):
        types = {raw_type.lower()}
    elif isinstance(raw_type, list):
        types = {str(item).lower() for item in raw_type}
    else:
        return False
    return bool(types & ORGANIZATION_TYPES)


def _has_tax_identifier(value: dict[str, Any]) -> bool:
    for key in ("taxID", "vatID"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return True
    return False


def _structured_name_matches(
    names: tuple[str, ...],
    normalized_name: str,
    company_tokens: set[str],
) -> bool:
    for value in names:
        normalized = normalize_company_name(value)
        if normalized and normalized == normalized_name:
            return True
        tokens = set(normalized.split())
        if company_tokens and len(company_tokens & tokens) / len(company_tokens) >= 0.8:
            return True
    return False


def _website_host(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower().removeprefix("www.")
