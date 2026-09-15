from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any

from .company_resolution import is_distinctive_company_name
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class CompanyReviewProfile:
    company_id: int
    canonical_name: str
    normalized_name: str
    aliases: tuple[str, ...]
    normalized_aliases: tuple[str, ...]
    locations: tuple[str, ...]
    website_url: str | None
    identity_confidence: float


@dataclass(frozen=True, slots=True)
class ResolutionReviewCandidate:
    left_company_id: int
    right_company_id: int
    left_name: str
    right_name: str
    score: float
    name_similarity: float
    token_similarity: float
    location_overlap: bool
    website_match: bool
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signals"] = list(self.signals)
        return payload


def build_resolution_review_queue(
    store: SQLiteStore,
    *,
    min_score: float = 0.82,
    limit: int = 100,
    company_limit: int = 5000,
) -> list[ResolutionReviewCandidate]:
    """Return possible duplicate companies for manual review only.

    This function never mutates company IDs and never merges records. Candidate
    generation is blocked by shared tokens / prefixes / verified website hosts so
    it remains useful on benchmark-sized datasets without evaluating every pair.
    """

    store.init_schema()
    profiles = _load_profiles(store, company_limit=max(1, company_limit))
    pairs = _blocked_pairs(profiles)
    candidates: list[ResolutionReviewCandidate] = []

    for left_id, right_id in pairs:
        left = profiles[left_id]
        right = profiles[right_id]
        candidate = _score_pair(left, right)
        if candidate.score >= min_score:
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -item.score,
            -item.name_similarity,
            item.left_name.lower(),
            item.right_name.lower(),
        )
    )
    return candidates[: max(1, limit)]


def _load_profiles(
    store: SQLiteStore,
    *,
    company_limit: int,
) -> dict[int, CompanyReviewProfile]:
    with store.connect() as connection:
        companies = connection.execute(
            """
            SELECT
                id,
                canonical_name,
                normalized_name,
                website_url,
                identity_confidence
            FROM companies
            ORDER BY id ASC
            LIMIT ?
            """,
            (company_limit,),
        ).fetchall()
        company_ids = [int(row["id"]) for row in companies]
        if not company_ids:
            return {}

        placeholders = ",".join("?" for _ in company_ids)
        alias_rows = connection.execute(
            f"""
            SELECT company_id, alias, normalized_alias
            FROM company_aliases
            WHERE company_id IN ({placeholders})
            ORDER BY company_id, id
            """,
            tuple(company_ids),
        ).fetchall()
        location_rows = connection.execute(
            f"""
            SELECT company_id, normalized_city
            FROM company_locations
            WHERE company_id IN ({placeholders})
            ORDER BY company_id, id
            """,
            tuple(company_ids),
        ).fetchall()

    aliases: dict[int, list[str]] = {company_id: [] for company_id in company_ids}
    normalized_aliases: dict[int, list[str]] = {
        company_id: [] for company_id in company_ids
    }
    locations: dict[int, list[str]] = {company_id: [] for company_id in company_ids}

    for row in alias_rows:
        company_id = int(row["company_id"])
        aliases[company_id].append(str(row["alias"]))
        normalized_aliases[company_id].append(str(row["normalized_alias"]))
    for row in location_rows:
        company_id = int(row["company_id"])
        locations[company_id].append(str(row["normalized_city"]))

    profiles: dict[int, CompanyReviewProfile] = {}
    for row in companies:
        company_id = int(row["id"])
        normalized_name = str(row["normalized_name"])
        profile_aliases = tuple(aliases[company_id]) or (str(row["canonical_name"]),)
        profile_normalized_aliases = tuple(normalized_aliases[company_id]) or (
            normalized_name,
        )
        profiles[company_id] = CompanyReviewProfile(
            company_id=company_id,
            canonical_name=str(row["canonical_name"]),
            normalized_name=normalized_name,
            aliases=profile_aliases,
            normalized_aliases=profile_normalized_aliases,
            locations=tuple(locations[company_id]),
            website_url=row["website_url"],
            identity_confidence=float(row["identity_confidence"]),
        )
    return profiles


def _blocked_pairs(
    profiles: dict[int, CompanyReviewProfile],
) -> set[tuple[int, int]]:
    blocks: dict[str, set[int]] = {}
    for profile in profiles.values():
        keys = _blocking_keys(profile)
        for key in keys:
            blocks.setdefault(key, set()).add(profile.company_id)

    pairs: set[tuple[int, int]] = set()
    for company_ids in blocks.values():
        if len(company_ids) < 2:
            continue
        ordered = sorted(company_ids)
        for left_id, right_id in combinations(ordered, 2):
            pairs.add((left_id, right_id))
    return pairs


def _blocking_keys(profile: CompanyReviewProfile) -> set[str]:
    keys: set[str] = set()
    for value in {profile.normalized_name, *profile.normalized_aliases}:
        tokens = [token for token in value.split() if len(token) >= 4]
        for token in tokens:
            keys.add(f"token:{token}")

        compact = value.replace(" ", "")
        if len(compact) >= 6:
            keys.add(f"prefix:{compact[:4]}")
            keys.add(f"suffix:{compact[-4:]}")

    if profile.website_url:
        keys.add(f"website:{_website_host(profile.website_url)}")
    return keys


def _score_pair(
    left: CompanyReviewProfile,
    right: CompanyReviewProfile,
) -> ResolutionReviewCandidate:
    name_similarity = _best_name_similarity(left, right)
    token_similarity = _best_token_similarity(left, right)
    location_overlap = bool(set(left.locations) & set(right.locations))
    website_match = bool(
        left.website_url
        and right.website_url
        and _website_host(left.website_url) == _website_host(right.website_url)
    )

    base = (0.72 * name_similarity) + (0.28 * token_similarity)
    signals: list[str] = [
        f"name_similarity:{name_similarity:.3f}",
        f"token_similarity:{token_similarity:.3f}",
    ]

    if location_overlap:
        base += 0.04
        signals.append("shared_location")
    if website_match:
        base += 0.15
        signals.append("same_website_host")
    if left.identity_confidence >= 0.8 and right.identity_confidence >= 0.8:
        base += 0.02
        signals.append("strong_identity_both")
    if not (
        is_distinctive_company_name(left.normalized_name)
        and is_distinctive_company_name(right.normalized_name)
    ):
        base -= 0.08
        signals.append("weak_or_generic_name")

    return ResolutionReviewCandidate(
        left_company_id=left.company_id,
        right_company_id=right.company_id,
        left_name=left.canonical_name,
        right_name=right.canonical_name,
        score=round(max(0.0, min(base, 1.0)), 4),
        name_similarity=round(name_similarity, 4),
        token_similarity=round(token_similarity, 4),
        location_overlap=location_overlap,
        website_match=website_match,
        signals=tuple(signals),
    )


def _best_name_similarity(
    left: CompanyReviewProfile,
    right: CompanyReviewProfile,
) -> float:
    best = 0.0
    for left_name in {left.normalized_name, *left.normalized_aliases}:
        for right_name in {right.normalized_name, *right.normalized_aliases}:
            if left_name == right_name:
                return 1.0
            best = max(best, SequenceMatcher(None, left_name, right_name).ratio())
    return best


def _best_token_similarity(
    left: CompanyReviewProfile,
    right: CompanyReviewProfile,
) -> float:
    best = 0.0
    for left_name in {left.normalized_name, *left.normalized_aliases}:
        left_tokens = set(left_name.split())
        if not left_tokens:
            continue
        for right_name in {right.normalized_name, *right.normalized_aliases}:
            right_tokens = set(right_name.split())
            union = left_tokens | right_tokens
            if not union:
                continue
            best = max(best, len(left_tokens & right_tokens) / len(union))
    return best


def _website_host(value: str) -> str:
    host = value.lower().strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    host = host.split("/", 1)[0]
    return host.removeprefix("www.").split(":", 1)[0]
