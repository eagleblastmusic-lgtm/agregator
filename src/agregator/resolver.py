from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import SearchCandidate
from .signals import normalize_text

BLOCKED_HOSTS = {
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "olx.pl",
    "pracuj.pl",
    "indeed.com",
    "indeed.pl",
    "gowork.pl",
    "jooble.org",
}

STOP_WORDS = {
    "sp",
    "z",
    "oo",
    "sa",
    "s",
    "a",
    "polska",
    "firma",
    "group",
    "grupa",
}


def _tokens(value: str) -> set[str]:
    normalized = normalize_text(value)
    raw = re.findall(r"[a-z0-9]{2,}", normalized)
    return {token for token in raw if token not in STOP_WORDS}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _blocked(host: str) -> bool:
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_HOSTS)


def score_candidate(candidate: SearchCandidate, company_name: str, city: str | None = None) -> float:
    host = _host(candidate.url)
    if not host or _blocked(host):
        return 0.0

    company_tokens = _tokens(company_name)
    if not company_tokens:
        return 0.0

    haystack = _tokens(f"{candidate.title} {candidate.snippet} {host}")
    overlap = len(company_tokens & haystack) / len(company_tokens)
    score = 0.62 * overlap

    host_flat = normalize_text(host).replace("-", "").replace(".", "")
    company_flat = "".join(sorted(company_tokens))
    if any(token in host_flat for token in company_tokens if len(token) >= 4):
        score += 0.20
    elif company_flat and company_flat in host_flat:
        score += 0.20

    if city and normalize_text(city) in normalize_text(f"{candidate.title} {candidate.snippet}"):
        score += 0.12

    if any(word in normalize_text(candidate.title) for word in ("kontakt", "oficjalna", "official")):
        score += 0.04

    return min(score, 1.0)


def choose_official_website(
    candidates: list[SearchCandidate],
    company_name: str,
    city: str | None = None,
    *,
    minimum_score: float = 0.45,
) -> SearchCandidate | None:
    scored: list[SearchCandidate] = []
    for candidate in candidates:
        candidate = candidate.model_copy(deep=True)
        candidate.score = score_candidate(candidate, company_name, city)
        scored.append(candidate)

    scored.sort(key=lambda item: item.score, reverse=True)
    if not scored or scored[0].score < minimum_score:
        return None
    return scored[0]
