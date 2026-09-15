from __future__ import annotations

from dataclasses import asdict, dataclass
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

    content_score = min(content_score, 1.0)
    final_score = min((0.42 * search_score) + (0.58 * content_score), 1.0)

    strong_identity_signal = exact_name or coverage >= 0.7 or (
        host_match and coverage >= 0.5
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
    return any(
        len(token) >= 4 and token in compact_host
        for token in company_tokens
    )
