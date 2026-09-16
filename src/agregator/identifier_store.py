from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from .company_resolution import ResolutionDecision
from .models import CompanyIdentifier, JobPosting
from .storage import SQLiteStore

STRONG_IDENTIFIER_CONFIDENCE = 0.95
_STATUTORY_IDENTIFIER_LENGTHS: dict[str, set[int]] = {
    "nip": {10},
    "regon": {9, 14},
    "krs": {10},
}


class IdentifierAwareSQLiteStore(SQLiteStore):
    """SQLite store that uses explicit strong company IDs as a conservative fallback key.

    Name/city resolution remains the first choice. Only when the existing resolver cannot
    safely select a company does ``SQLiteStore`` ask for a new company key. At that point
    this subclass may use a high-confidence statutory identifier or a source-namespaced
    employer-profile identifier instead of a per-job source id.

    This deliberately does not make short names such as ``PwC`` distinctive. Two short-name
    jobs without the same explicit strong identifier therefore stay separate exactly as
    before.
    """

    @staticmethod
    def _new_company_key(job: JobPosting, decision: ResolutionDecision) -> str:
        strong = strongest_company_identifier(job)
        if strong is None:
            return SQLiteStore._new_company_key(job, decision)

        kind, value = strong
        digest = hashlib.sha1(  # noqa: S324 - deterministic identity key, not security
            f"{kind}:{value}".encode("utf-8")
        ).hexdigest()[:20]
        return f"strong-id:{kind}:{digest}"


def strongest_company_identifier(job: JobPosting) -> tuple[str, str] | None:
    """Return the safest normalized source-provided company identifier for keying.

    Accepted identifiers are intentionally narrow:
    - NIP, REGON, KRS with valid structural lengths,
    - namespaced employer-profile identifiers such as
      ``karierawfinansach_employer_profile``.

    Generic organization IDs are not accepted here because their semantics vary by source.
    """

    candidates: list[tuple[int, float, str, str]] = []
    for identifier in job.company_identifiers:
        if identifier.confidence < STRONG_IDENTIFIER_CONFIDENCE:
            continue
        normalized = _normalize_strong_identifier(identifier, job.source)
        if normalized is None:
            continue
        kind, value, priority = normalized
        candidates.append((priority, -identifier.confidence, kind, value))

    if not candidates:
        return None

    _, _, kind, value = min(candidates)
    return kind, value


def _normalize_strong_identifier(
    identifier: CompanyIdentifier,
    job_source: str,
) -> tuple[str, str, int] | None:
    kind = identifier.kind.strip().lower()
    raw = identifier.value.strip()
    if not kind or not raw:
        return None

    expected_lengths = _STATUTORY_IDENTIFIER_LENGTHS.get(kind)
    if expected_lengths is not None:
        value = re.sub(r"\D", "", raw)
        if len(value) not in expected_lengths:
            return None
        return kind, value, 0

    if kind == "employer_profile" or kind.endswith("_employer_profile"):
        value = _normalize_profile_identifier(raw)
        if value is None:
            return None
        if kind == "employer_profile":
            kind = f"{job_source.strip().lower()}_employer_profile"
        return kind, value, 1

    return None


def _normalize_profile_identifier(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        normalized = " ".join(value.casefold().split())
        return normalized if len(normalized) >= 2 else None

    host = parsed.hostname.lower().rstrip(".")
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), f"{host}{port}", path, "", ""))
