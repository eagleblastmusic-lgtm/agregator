from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class EmployerDiscoveryScore:
    company_id: int
    canonical_name: str
    city: str | None
    score: int
    job_count: int
    source_count: int
    website_url: str | None
    website_confidence: float
    green_channels: int
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signals"] = list(self.signals)
        return payload


def rank_companies(
    store: SQLiteStore,
    *,
    min_score: int = 0,
    limit: int = 100,
    website_threshold: float = 0.7,
) -> list[EmployerDiscoveryScore]:
    """Rank companies by business discovery signals without changing classification.

    The score is intentionally separate from contact confidence and identity resolution
    confidence. It is a prioritization layer for manual/business review.
    """

    store.init_schema()
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id AS company_id,
                c.canonical_name,
                c.city,
                c.identity_confidence,
                c.website_url,
                c.website_confidence,
                COUNT(DISTINCT j.id) AS job_count,
                COUNT(DISTINCT j.source) AS source_count,
                COUNT(DISTINCT CASE WHEN cc.decision = 'green' THEN cc.id END)
                    AS green_channels,
                MAX(
                    CASE
                        WHEN cc.purpose IN (
                            'business_partnership',
                            'sales',
                            'supplier',
                            'franchise'
                        )
                        AND (
                            lower(cc.evidence_url) LIKE '%wspol%'
                            OR lower(cc.evidence_url) LIKE '%partner%'
                            OR lower(cc.evidence_url) LIKE '%b2b%'
                            OR lower(cc.evidence_url) LIKE '%dostaw%'
                            OR lower(cc.evidence_url) LIKE '%franczy%'
                        )
                        THEN 1
                        ELSE 0
                    END
                ) AS has_business_page
            FROM companies c
            LEFT JOIN job_postings j ON j.company_id = c.id
            LEFT JOIN contact_channels cc ON cc.company_id = c.id
            GROUP BY c.id
            ORDER BY c.id ASC
            """
        ).fetchall()

    scored: list[EmployerDiscoveryScore] = []
    for row in rows:
        score, signals = _score_row(row, website_threshold=website_threshold)
        if score < min_score:
            continue
        scored.append(
            EmployerDiscoveryScore(
                company_id=int(row["company_id"]),
                canonical_name=str(row["canonical_name"]),
                city=row["city"],
                score=score,
                job_count=int(row["job_count"] or 0),
                source_count=int(row["source_count"] or 0),
                website_url=row["website_url"],
                website_confidence=float(row["website_confidence"] or 0.0),
                green_channels=int(row["green_channels"] or 0),
                signals=tuple(signals),
            )
        )

    scored.sort(
        key=lambda item: (
            -item.score,
            -item.job_count,
            -item.green_channels,
            item.canonical_name.lower(),
        )
    )
    return scored[: max(1, limit)]


def _score_row(row: Any, *, website_threshold: float) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    job_count = int(row["job_count"] or 0)
    source_count = int(row["source_count"] or 0)
    website_confidence = float(row["website_confidence"] or 0.0)
    green_channels = int(row["green_channels"] or 0)
    identity_confidence = float(row["identity_confidence"] or 0.0)

    if job_count >= 3:
        score += 25
        signals.append("jobs_3_plus:+25")
    if source_count >= 2:
        score += 15
        signals.append("sources_2_plus:+15")
    if row["website_url"] and website_confidence >= website_threshold:
        score += 15
        signals.append("verified_website:+15")
    if int(row["has_business_page"] or 0) > 0:
        score += 20
        signals.append("explicit_business_page:+20")
    if green_channels > 0:
        score += 20
        signals.append("green_channel:+20")
    if identity_confidence >= 0.9:
        score += 5
        signals.append("strong_identity:+5")

    return min(score, 100), signals
