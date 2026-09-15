from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .models import CompanyIdentifier, JobPosting
from .storage import SQLiteStore

KNOWN_LENGTHS: dict[str, set[int]] = {
    "nip": {10},
    "regon": {9, 14},
    "krs": {10},
}


@dataclass(slots=True)
class IdentifierPersistenceStats:
    observations: int = 0
    inserted: int = 0
    updated: int = 0
    invalid: int = 0
    conflicts: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def init_company_identifier_schema(store: SQLiteStore) -> None:
    store.init_schema()
    with store.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS company_identifiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT,
                confidence REAL NOT NULL DEFAULT 0,
                observation_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id),
                UNIQUE(company_id, kind, value)
            );

            CREATE INDEX IF NOT EXISTS idx_company_identifiers_lookup
                ON company_identifiers(kind, value);
            CREATE INDEX IF NOT EXISTS idx_company_identifiers_company
                ON company_identifiers(company_id);

            CREATE TABLE IF NOT EXISTS company_identifier_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                job_source TEXT NOT NULL,
                evidence_source TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                observation_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id),
                UNIQUE(company_id, kind, value, job_source, evidence_source)
            );

            CREATE INDEX IF NOT EXISTS idx_company_identifier_observations_source
                ON company_identifier_observations(job_source);
            CREATE INDEX IF NOT EXISTS idx_company_identifier_observations_company
                ON company_identifier_observations(company_id);
            """
        )


def persist_job_company_identifiers(
    store: SQLiteStore,
    jobs: list[JobPosting],
) -> IdentifierPersistenceStats:
    """Persist explicit source-provided company IDs after jobs are assigned to companies.

    Matching identifiers observed under multiple current company records are counted as
    conflicts but never merge those records automatically. A separate observation table
    preserves which job source supplied each identifier so source-value diagnostics do not
    need to infer provenance from generic field names such as ``official_feed.nip``.
    """

    init_company_identifier_schema(store)
    stats = IdentifierPersistenceStats()

    with store.connect() as connection:
        for job in jobs:
            if not job.company_identifiers:
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

            for identifier in job.company_identifiers:
                stats.observations += 1
                normalized = normalize_company_identifier(identifier)
                if normalized is None:
                    stats.invalid += 1
                    continue
                kind, value = normalized
                evidence_source = (
                    identifier.source or job.company_name_source or job.source
                )

                conflict = connection.execute(
                    """
                    SELECT 1
                    FROM company_identifiers
                    WHERE kind = ? AND value = ? AND company_id <> ?
                    LIMIT 1
                    """,
                    (kind, value, company_id),
                ).fetchone()
                if conflict is not None:
                    stats.conflicts += 1

                exists = connection.execute(
                    """
                    SELECT 1
                    FROM company_identifiers
                    WHERE company_id = ? AND kind = ? AND value = ?
                    """,
                    (company_id, kind, value),
                ).fetchone()

                connection.execute(
                    """
                    INSERT INTO company_identifiers(
                        company_id,
                        kind,
                        value,
                        source,
                        confidence
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(company_id, kind, value) DO UPDATE SET
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
                        kind,
                        value,
                        evidence_source,
                        identifier.confidence,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO company_identifier_observations(
                        company_id,
                        kind,
                        value,
                        job_source,
                        evidence_source,
                        confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                        company_id,
                        kind,
                        value,
                        job_source,
                        evidence_source
                    ) DO UPDATE SET
                        confidence = MAX(confidence, excluded.confidence),
                        observation_count = observation_count + 1,
                        last_seen_at = CURRENT_TIMESTAMP
                    """,
                    (
                        company_id,
                        kind,
                        value,
                        job.source,
                        evidence_source,
                        identifier.confidence,
                    ),
                )
                if exists is None:
                    stats.inserted += 1
                else:
                    stats.updated += 1

    return stats


def list_identifier_conflicts(
    store: SQLiteStore,
    *,
    limit: int = 100,
) -> list[dict[str, object]]:
    init_company_identifier_schema(store)
    with store.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                ci.kind,
                ci.value,
                COUNT(DISTINCT ci.company_id) AS company_count,
                GROUP_CONCAT(DISTINCT ci.company_id) AS company_ids,
                GROUP_CONCAT(DISTINCT c.canonical_name) AS company_names,
                MAX(ci.confidence) AS max_confidence
            FROM company_identifiers ci
            JOIN companies c ON c.id = ci.company_id
            GROUP BY ci.kind, ci.value
            HAVING COUNT(DISTINCT ci.company_id) > 1
            ORDER BY max_confidence DESC, company_count DESC, ci.kind, ci.value
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def normalize_company_identifier(
    identifier: CompanyIdentifier,
) -> tuple[str, str] | None:
    kind = identifier.kind.strip().lower()
    raw = identifier.value.strip()
    if not kind or not raw:
        return None

    if kind in KNOWN_LENGTHS:
        value = re.sub(r"\D", "", raw)
        if len(value) not in KNOWN_LENGTHS[kind]:
            return None
        return kind, value

    value = re.sub(r"\s+", " ", raw).strip().lower()
    if len(value) < 2 or len(value) > 128:
        return None
    return kind, value
