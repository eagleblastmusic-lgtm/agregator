from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import DiscoveryResult, JobPosting
from .normalize import company_key, normalize_company_name, normalize_text


@dataclass(slots=True)
class UpsertStats:
    jobs_seen: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    companies_created: int = 0


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_key TEXT NOT NULL UNIQUE,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    city TEXT,
                    normalized_city TEXT,
                    identity_source TEXT,
                    identity_confidence REAL NOT NULL DEFAULT 0,
                    website_url TEXT,
                    website_confidence REAL NOT NULL DEFAULT 0,
                    enriched_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS job_postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company_id INTEGER NOT NULL,
                    company_name_raw TEXT NOT NULL,
                    company_name_source TEXT,
                    company_name_confidence REAL NOT NULL DEFAULT 0,
                    city TEXT,
                    description TEXT,
                    published_at TEXT,
                    refreshed_at TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id),
                    UNIQUE(source, source_id)
                );

                CREATE INDEX IF NOT EXISTS idx_job_postings_company_id
                    ON job_postings(company_id);
                CREATE INDEX IF NOT EXISTS idx_job_postings_source
                    ON job_postings(source);

                CREATE TABLE IF NOT EXISTS contact_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_url TEXT NOT NULL,
                    evidence_text TEXT NOT NULL,
                    evidence_signal TEXT,
                    verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id),
                    UNIQUE(company_id, kind, value)
                );

                CREATE INDEX IF NOT EXISTS idx_contact_channels_decision
                    ON contact_channels(decision);

                CREATE TABLE IF NOT EXISTS source_state (
                    source TEXT PRIMARY KEY,
                    cursor TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._ensure_column(connection, "companies", "identity_source", "TEXT")
            self._ensure_column(
                connection,
                "companies",
                "identity_confidence",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(connection, "companies", "enriched_at", "TEXT")

    def get_source_cursor(self, source: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cursor FROM source_state WHERE source = ?",
                (source,),
            ).fetchone()
        return None if row is None else row["cursor"]

    def set_source_cursor(self, source: str, cursor: str | None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_state(source, cursor)
                VALUES (?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    cursor = excluded.cursor,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source, cursor),
            )

    def upsert_jobs(self, jobs: list[JobPosting]) -> UpsertStats:
        stats = UpsertStats()
        with self.connect() as connection:
            for job in jobs:
                stats.jobs_seen += 1
                company_id, created = self._get_or_create_company(connection, job)
                if created:
                    stats.companies_created += 1

                exists = connection.execute(
                    "SELECT 1 FROM job_postings WHERE source = ? AND source_id = ?",
                    (job.source, job.source_id or job.url),
                ).fetchone()

                connection.execute(
                    """
                    INSERT INTO job_postings(
                        source,
                        source_id,
                        url,
                        title,
                        company_id,
                        company_name_raw,
                        company_name_source,
                        company_name_confidence,
                        city,
                        description,
                        published_at,
                        refreshed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_id) DO UPDATE SET
                        url = excluded.url,
                        title = excluded.title,
                        company_id = excluded.company_id,
                        company_name_raw = excluded.company_name_raw,
                        company_name_source = excluded.company_name_source,
                        company_name_confidence = excluded.company_name_confidence,
                        city = excluded.city,
                        description = excluded.description,
                        published_at = excluded.published_at,
                        refreshed_at = excluded.refreshed_at,
                        last_seen_at = CURRENT_TIMESTAMP
                    """,
                    (
                        job.source,
                        job.source_id or job.url,
                        job.url,
                        job.title,
                        company_id,
                        job.company_name,
                        job.company_name_source,
                        job.company_name_confidence,
                        job.city,
                        job.description,
                        job.published_at,
                        job.refreshed_at,
                    ),
                )

                self._upgrade_company_identity(connection, company_id, job)
                if exists:
                    stats.jobs_updated += 1
                else:
                    stats.jobs_inserted += 1
        return stats

    def list_companies(self, limit: int = 100) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.id,
                    c.canonical_name,
                    c.city,
                    c.identity_source,
                    c.identity_confidence,
                    c.website_url,
                    c.website_confidence,
                    COUNT(DISTINCT j.id) AS job_count,
                    GROUP_CONCAT(DISTINCT j.source) AS sources,
                    COUNT(
                        DISTINCT CASE WHEN cc.decision = 'green' THEN cc.id END
                    ) AS green_channels
                FROM companies c
                LEFT JOIN job_postings j ON j.company_id = c.id
                LEFT JOIN contact_channels cc ON cc.company_id = c.id
                GROUP BY c.id
                ORDER BY job_count DESC, c.canonical_name ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def companies_for_enrichment(
        self,
        *,
        limit: int = 20,
        min_identity_confidence: float = 0.7,
        refresh: bool = False,
    ) -> list[dict[str, object]]:
        where_status = "1 = 1" if refresh else "c.enriched_at IS NULL"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    c.id,
                    c.canonical_name,
                    c.city,
                    c.identity_confidence,
                    COUNT(j.id) AS job_count
                FROM companies c
                LEFT JOIN job_postings j ON j.company_id = c.id
                WHERE {where_status}
                  AND c.identity_confidence >= ?
                GROUP BY c.id
                ORDER BY job_count DESC, c.identity_confidence DESC
                LIMIT ?
                """,
                (min_identity_confidence, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_discovery_result(self, company_id: int, result: DiscoveryResult) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE companies
                SET website_url = ?,
                    website_confidence = ?,
                    enriched_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    result.company.website_url,
                    result.company.website_confidence,
                    company_id,
                ),
            )

            for channel in result.channels:
                connection.execute(
                    """
                    INSERT INTO contact_channels(
                        company_id,
                        kind,
                        value,
                        purpose,
                        decision,
                        confidence,
                        evidence_url,
                        evidence_text,
                        evidence_signal
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(company_id, kind, value) DO UPDATE SET
                        purpose = excluded.purpose,
                        decision = excluded.decision,
                        confidence = excluded.confidence,
                        evidence_url = excluded.evidence_url,
                        evidence_text = excluded.evidence_text,
                        evidence_signal = excluded.evidence_signal,
                        verified_at = CURRENT_TIMESTAMP
                    """,
                    (
                        company_id,
                        channel.kind.value,
                        channel.value,
                        channel.purpose.value,
                        channel.decision.value,
                        channel.confidence,
                        channel.evidence.url,
                        channel.evidence.text,
                        channel.evidence.signal,
                    ),
                )

    def list_green_channels(self, limit: int = 100) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.canonical_name,
                    c.city,
                    c.website_url,
                    cc.kind,
                    cc.value,
                    cc.purpose,
                    cc.confidence,
                    cc.evidence_url,
                    cc.evidence_text,
                    cc.verified_at
                FROM contact_channels cc
                JOIN companies c ON c.id = cc.company_id
                WHERE cc.decision = 'green'
                ORDER BY cc.confidence DESC, c.canonical_name ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _get_or_create_company(
        connection: sqlite3.Connection,
        job: JobPosting,
    ) -> tuple[int, bool]:
        key = company_key(job.company_name, job.city)
        normalized_name = normalize_company_name(job.company_name)
        normalized_city = normalize_text(job.city or "") or None

        row = connection.execute(
            "SELECT id FROM companies WHERE company_key = ?",
            (key,),
        ).fetchone()
        if row is not None:
            return int(row["id"]), False

        cursor = connection.execute(
            """
            INSERT INTO companies(
                company_key,
                canonical_name,
                normalized_name,
                city,
                normalized_city,
                identity_source,
                identity_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                job.company_name,
                normalized_name,
                job.city,
                normalized_city,
                job.company_name_source,
                job.company_name_confidence,
            ),
        )
        return int(cursor.lastrowid), True

    @staticmethod
    def _upgrade_company_identity(
        connection: sqlite3.Connection,
        company_id: int,
        job: JobPosting,
    ) -> None:
        connection.execute(
            """
            UPDATE companies
            SET canonical_name = CASE
                    WHEN ? > identity_confidence THEN ?
                    ELSE canonical_name
                END,
                identity_source = CASE
                    WHEN ? > identity_confidence THEN ?
                    ELSE identity_source
                END,
                identity_confidence = MAX(identity_confidence, ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                job.company_name_confidence,
                job.company_name,
                job.company_name_confidence,
                job.company_name_source,
                job.company_name_confidence,
                company_id,
            ),
        )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
