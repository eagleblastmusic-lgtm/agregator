from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit, urlunsplit

from .models import CompanyWebsiteCandidate, JobPosting
from .storage import SQLiteStore


@dataclass(slots=True)
class WebsiteCandidatePersistenceStats:
    observations: int = 0
    inserted: int = 0
    updated: int = 0
    invalid: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def init_company_website_candidate_schema(store: SQLiteStore) -> None:
    store.init_schema()
    with store.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS company_website_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                host TEXT NOT NULL,
                source TEXT,
                confidence REAL NOT NULL DEFAULT 0,
                observation_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id),
                UNIQUE(company_id, url)
            );

            CREATE INDEX IF NOT EXISTS idx_company_website_candidates_company
                ON company_website_candidates(company_id, confidence DESC);
            CREATE INDEX IF NOT EXISTS idx_company_website_candidates_host
                ON company_website_candidates(host);
            """
        )


def persist_job_company_website_candidates(
    store: SQLiteStore,
    jobs: list[JobPosting],
) -> WebsiteCandidatePersistenceStats:
    init_company_website_candidate_schema(store)
    stats = WebsiteCandidatePersistenceStats()

    with store.connect() as connection:
        for job in jobs:
            if not job.company_website_candidates:
                continue

            source_id = job.source_id or job.url
            row = connection.execute(
                """
                SELECT company_id
                FROM job_postings
                WHERE source = ? AND source_id = ?
                """,
                (job.source, source_id),
            ).fetchone()
            if row is None:
                continue
            company_id = int(row["company_id"])

            for candidate in job.company_website_candidates:
                stats.observations += 1
                normalized = normalize_company_website_candidate(candidate.url)
                if normalized is None:
                    stats.invalid += 1
                    continue
                url, host = normalized

                exists = connection.execute(
                    """
                    SELECT 1
                    FROM company_website_candidates
                    WHERE company_id = ? AND url = ?
                    """,
                    (company_id, url),
                ).fetchone()

                connection.execute(
                    """
                    INSERT INTO company_website_candidates(
                        company_id,
                        url,
                        host,
                        source,
                        confidence
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(company_id, url) DO UPDATE SET
                        source = CASE
                            WHEN excluded.confidence >= confidence THEN excluded.source
                            ELSE source
                        END,
                        confidence = MAX(confidence, excluded.confidence),
                        observation_count = observation_count + 1,
                        last_seen_at = CURRENT_TIMESTAMP
                    """,
                    (
                        company_id,
                        url,
                        host,
                        candidate.source or job.source,
                        candidate.confidence,
                    ),
                )
                if exists is None:
                    stats.inserted += 1
                else:
                    stats.updated += 1

    return stats


def list_company_website_candidates(
    store: SQLiteStore,
    company_id: int,
    *,
    limit: int = 5,
) -> list[dict[str, object]]:
    init_company_website_candidate_schema(store)
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                company_id,
                url,
                host,
                source,
                confidence,
                observation_count,
                first_seen_at,
                last_seen_at
            FROM company_website_candidates
            WHERE company_id = ?
            ORDER BY confidence DESC, observation_count DESC, id ASC
            LIMIT ?
            """,
            (company_id, max(1, limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def normalize_company_website_candidate(raw_url: str) -> tuple[str, str] | None:
    value = raw_url.strip()
    if not value or any(character.isspace() for character in value):
        return None
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return None

    netloc = parsed.netloc
    path = parsed.path or ""
    normalized = urlunsplit((parsed.scheme, netloc, path, parsed.query, ""))
    return normalized, host
