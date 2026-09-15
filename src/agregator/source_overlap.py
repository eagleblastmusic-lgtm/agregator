from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any

from .normalize import normalize_company_name, normalize_text
from .source_quality import build_source_identity_metrics
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class SourcePairOverlap:
    source_a: str
    source_b: str
    source_a_fingerprints: int
    source_b_fingerprints: int
    shared_fingerprints: int
    union_fingerprints: int
    jaccard: float
    overlap_rate_a: float
    overlap_rate_b: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceFingerprintValue:
    source: str
    fingerprints: int
    exclusive_fingerprints: int
    shared_fingerprints: int
    exclusive_rate: float
    shared_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceOverlapReport:
    unique_job_fingerprints: int
    cross_source_shared_fingerprints: int
    cross_source_shared_fingerprint_rate: float
    by_source: dict[str, SourceFingerprintValue]
    identity_quality: dict[str, dict[str, Any]]
    pairwise: dict[str, SourcePairOverlap]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unique_job_fingerprints": self.unique_job_fingerprints,
            "cross_source_shared_fingerprints": self.cross_source_shared_fingerprints,
            "cross_source_shared_fingerprint_rate": self.cross_source_shared_fingerprint_rate,
            "by_source": {
                key: value.to_dict()
                for key, value in self.by_source.items()
            },
            "identity_quality": self.identity_quality,
            "pairwise": {
                key: value.to_dict()
                for key, value in self.pairwise.items()
            },
        }


def build_source_overlap_report(store: SQLiteStore) -> SourceOverlapReport:
    """Measure heuristic cross-source overlap without declaring jobs identical.

    A fingerprint is based on normalized company name, title and city. It is only a
    benchmark diagnostic: matching fingerprints are candidates for overlap, not a
    production-grade duplicate identity decision. The report also carries job-level
    identity-quality diagnostics so source value can be judged alongside exclusivity.
    """

    store.init_schema()
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT source, company_name_raw, title, city
            FROM job_postings
            ORDER BY source, id
            """
        ).fetchall()

    by_source_fingerprints: dict[str, set[tuple[str, str, str]]] = {}
    fingerprint_sources: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        source = str(row["source"] or "").strip().lower()
        fingerprint = job_overlap_fingerprint(
            str(row["company_name_raw"] or ""),
            str(row["title"] or ""),
            str(row["city"] or ""),
        )
        if not source or fingerprint is None:
            continue
        by_source_fingerprints.setdefault(source, set()).add(fingerprint)
        fingerprint_sources.setdefault(fingerprint, set()).add(source)

    by_source: dict[str, SourceFingerprintValue] = {}
    for source, fingerprints in sorted(by_source_fingerprints.items()):
        exclusive = sum(
            1 for fingerprint in fingerprints if len(fingerprint_sources[fingerprint]) == 1
        )
        shared = len(fingerprints) - exclusive
        by_source[source] = SourceFingerprintValue(
            source=source,
            fingerprints=len(fingerprints),
            exclusive_fingerprints=exclusive,
            shared_fingerprints=shared,
            exclusive_rate=_ratio(exclusive, len(fingerprints)),
            shared_rate=_ratio(shared, len(fingerprints)),
        )

    pairwise: dict[str, SourcePairOverlap] = {}
    for source_a, source_b in combinations(sorted(by_source_fingerprints), 2):
        fingerprints_a = by_source_fingerprints[source_a]
        fingerprints_b = by_source_fingerprints[source_b]
        shared = fingerprints_a & fingerprints_b
        union = fingerprints_a | fingerprints_b
        key = f"{source_a}|{source_b}"
        pairwise[key] = SourcePairOverlap(
            source_a=source_a,
            source_b=source_b,
            source_a_fingerprints=len(fingerprints_a),
            source_b_fingerprints=len(fingerprints_b),
            shared_fingerprints=len(shared),
            union_fingerprints=len(union),
            jaccard=_ratio(len(shared), len(union)),
            overlap_rate_a=_ratio(len(shared), len(fingerprints_a)),
            overlap_rate_b=_ratio(len(shared), len(fingerprints_b)),
        )

    identity_quality = {
        source: metrics.to_dict()
        for source, metrics in build_source_identity_metrics(store).items()
    }
    unique_fingerprints = len(fingerprint_sources)
    shared_fingerprints = sum(
        1 for sources in fingerprint_sources.values() if len(sources) >= 2
    )
    return SourceOverlapReport(
        unique_job_fingerprints=unique_fingerprints,
        cross_source_shared_fingerprints=shared_fingerprints,
        cross_source_shared_fingerprint_rate=_ratio(
            shared_fingerprints,
            unique_fingerprints,
        ),
        by_source=by_source,
        identity_quality=identity_quality,
        pairwise=pairwise,
    )


def job_overlap_fingerprint(
    company_name: str,
    title: str,
    city: str | None,
) -> tuple[str, str, str] | None:
    company = normalize_company_name(company_name)
    normalized_title = normalize_text(title)
    normalized_city = normalize_text(city or "")
    if not company or not normalized_title:
        return None
    return company, normalized_title, normalized_city


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
