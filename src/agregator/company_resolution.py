from __future__ import annotations

from dataclasses import dataclass

from .normalize import normalize_company_name, normalize_text

STRONG_IDENTITY_CONFIDENCE = 0.8

# Pojedyncze, ogólne określenia są zbyt słabym sygnałem do łączenia firm
# działających w różnych miejscowościach. To celowo konserwatywna lista.
GENERIC_SINGLE_TOKEN_NAMES = {
    "firma",
    "company",
    "group",
    "polska",
    "service",
    "services",
    "sklep",
    "hotel",
    "restaurant",
    "restauracja",
    "transport",
    "budownictwo",
}


@dataclass(frozen=True, slots=True)
class CompanyCandidate:
    id: int
    normalized_name: str
    normalized_city: str | None
    identity_confidence: float


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    company_id: int | None
    method: str
    confidence: float


def is_distinctive_company_name(normalized_name: str) -> bool:
    """Return whether a normalized name is safe enough for cross-city exact matching."""

    tokens = [token for token in normalized_name.split() if token]
    if not tokens:
        return False
    if len(tokens) >= 2:
        return len("".join(tokens)) >= 5

    token = tokens[0]
    return len(token) >= 6 and token not in GENERIC_SINGLE_TOKEN_NAMES


def choose_company_candidate(
    company_name: str,
    city: str | None,
    identity_confidence: float,
    candidates: list[CompanyCandidate],
) -> ResolutionDecision:
    """Choose an existing company using exact normalized signals only.

    V1 deliberately avoids fuzzy-name matching. Exact name + exact city remains the
    strongest rule. Cross-city merging is allowed only for one unambiguous candidate,
    a distinctive normalized name and strong identity confidence on both sides.
    """

    normalized_name = normalize_company_name(company_name)
    normalized_city = normalize_text(city or "") or None
    exact_name = [candidate for candidate in candidates if candidate.normalized_name == normalized_name]

    same_city = [
        candidate
        for candidate in exact_name
        if candidate.normalized_city == normalized_city and normalized_city is not None
    ]
    if len(same_city) == 1:
        return ResolutionDecision(
            company_id=same_city[0].id,
            method="exact_name_city",
            confidence=1.0,
        )

    if len(exact_name) != 1:
        method = "ambiguous_exact_name" if exact_name else "new_company"
        return ResolutionDecision(company_id=None, method=method, confidence=identity_confidence)

    candidate = exact_name[0]
    if (
        identity_confidence < STRONG_IDENTITY_CONFIDENCE
        or candidate.identity_confidence < STRONG_IDENTITY_CONFIDENCE
        or not is_distinctive_company_name(normalized_name)
    ):
        return ResolutionDecision(
            company_id=None,
            method="insufficient_cross_city_evidence",
            confidence=min(identity_confidence, candidate.identity_confidence),
        )

    if normalized_city is None or candidate.normalized_city is None:
        return ResolutionDecision(
            company_id=candidate.id,
            method="exact_name_partial_location",
            confidence=0.92,
        )

    return ResolutionDecision(
        company_id=candidate.id,
        method="exact_name_cross_city",
        confidence=0.88,
    )
