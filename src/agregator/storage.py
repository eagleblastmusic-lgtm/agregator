from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .company_resolution import CompanyCandidate, ResolutionDecision, choose_company_candidate
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

                CREATE INDEX IF NOT EXISTS idx_companies_normalized_name
                    ON companies(normalized_name);
                CREATE INDEX IF NOT EXISTS idx_companies_normalized_city
                    ON companies(normalized_city);

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
                    company_resolution_method TEXT,
                    company_resolution_confidence REAL NOT NULL DEFAULT 0,
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
                CREATE INDEX IF NOT EXISTS idx_job_postings_resolution_method
                    ON job_postings(company_resolution_method);

                CREATE TABLE IF NOT EXISTS company_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    alias TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    source TEXT,
                    confidence REAL NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id),
                    UNIQUE(company_id, alias)
                );

                CREATE INDEX IF NOT EXISTS idx_company_aliases_normalized_alias
                    ON company_aliases(normalized_alias);

                CREATE TABLE IF NOT EXISTS company_locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    city TEXT NOT NULL,
                    normalized_city TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id),
                    UNIQUE(company_id, normalized_city)
                );

                CREATE INDEX IF NOT EXISTS idx_company_locations_normalized_city
                    ON company_locations(normalized_city);

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

                CREATE TABLE IF NOT EXISTS source_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    cursor_before TEXT,
                    cursor_after TEXT,
                    pages_requested INTEGER NOT NULL,
                    pages_processed INTEGER NOT NULL DEFAULT 0,
                    jobs_seen INTEGER NOT NULL DEFAULT 0,
                    jobs_inserted INTEGER NOT NULL DEFAULT 0,
                    jobs_updated INTEGER NOT NULL DEFAULT 0,
                    companies_created INTEGER NOT NULL DEFAULT 0,
                    error_type TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_source_runs_source_started
                    ON source_runs(source, started_at DESC);
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
            self._ensure_column(
                connection,
                "job_postings",
                "company_resolution_method",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "job_postings",
                "company_resolution_confidence",
                "REAL NOT NULL DEFAULT 0",
            )

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

    def start_source_run(
        self,
        source: str,
        *,
        cursor_before: str | None,
        pages_requested: int,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO source_runs(source, cursor_before, pages_requested)
                VALUES (?, ?, ?)
                """,
                (source, cursor_before, pages_requested),
            )
            return int(cursor.lastrowid)

    def finish_source_run(
        self,
        run_id: int,
        *,
        status: str,
        cursor_after: str | None,
        pages_processed: int,
        stats: UpsertStats,
        error: Exception | None = None,
    ) -> None:
        error_type = type(error).__name__ if error is not None else None
        error_message = str(error)[:1000] if error is not None else None
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE source_runs
                SET status = ?,
                    cursor_after = ?,
                    pages_processed = ?,
                    jobs_seen = ?,
                    jobs_inserted = ?,
                    jobs_updated = ?,
                    companies_created = ?,
                    error_type = ?,
                    error_message = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    cursor_after,
                    pages_processed,
                    stats.jobs_seen,
                    stats.jobs_inserted,
                    stats.jobs_updated,
                    stats.companies_created,
                    error_type,
                    error_message,
                    run_id,
                ),
            )

    def list_source_runs(
        self,
        *,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        query = """
            SELECT
                id,
                source,
                status,
                cursor_before,
                cursor_after,
                pages_requested,
                pages_processed,
                jobs_seen,
                jobs_inserted,
                jobs_updated,
                companies_created,
                error_type,
                error_message,
                started_at,
                finished_at
            FROM source_runs
        """
        params: tuple[object, ...]
        if source:
            query += " WHERE source = ?"
            params = (source, limit)
        else:
            params = (limit,)
        query += " ORDER BY id DESC LIMIT ?"

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_jobs(self, jobs: list[JobPosting]) -> UpsertStats:
        stats = UpsertStats()
        with self.connect() as connection:
            for job in jobs:
                stats.jobs_seen += 1
                company_id, created, resolution = self._resolve_or_create_company(connection, job)
                if created:
                    stats.companies_created += 1

                self._remember_company_identity(connection, company_id, job)
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
                        company_resolution_method,
                        company_resolution_confidence,
                        city,
                        description,
                        published_at,
                        refreshed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_id) DO UPDATE SET
                        url = excluded.url,
                        title = excluded.title,
                        company_id = excluded.company_id,
                        company_name_raw = excluded.company_name_raw,
                        company_name_source = excluded.company_name_source,
                        company_name_confidence = excluded.company_name_confidence,
                        company_resolution_method = excluded.company_resolution_method,
                        company_resolution_confidence = excluded.company_resolution_confidence,
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
                        resolution.method,
                        resolution.confidence,
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
                    ) AS green_channels,
                    (
                        SELECT GROUP_CONCAT(alias, ' | ')
                        FROM company_aliases ca
                        WHERE ca.company_id = c.id
                    ) AS aliases,
                    (
                        SELECT GROUP_CONCAT(city, ' | ')
                        FROM company_locations cl
                        WHERE cl.company_id = c.id
                    ) AS locations
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

    def company_resolution_stats(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    COALESCE(company_resolution_method, 'legacy') AS method,
                    COUNT(*) AS job_count,
                    AVG(company_resolution_confidence) AS avg_confidence
                FROM job_postings
                GROUP BY COALESCE(company_resolution_method, 'legacy')
                ORDER BY job_count DESC, method ASC
                """
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

    def _resolve_or_create_company(
        self,
        connection: sqlite3.Connection,
        job: JobPosting,
    ) -> tuple[int, bool, ResolutionDecision]:
        normalized_name = normalize_company_name(job.company_name)
        rows = connection.execute(
            """
            SELECT id, normalized_name, normalized_city, identity_confidence
            FROM companies
            WHERE normalized_name = ?
            ORDER BY identity_confidence DESC, id ASC
            """,
            (normalized_name,),
        ).fetchall()
        candidates = [
            CompanyCandidate(
                id=int(row["id"]),
                normalized_name=str(row["normalized_name"]),
                normalized_city=row["normalized_city"],
                identity_confidence=float(row["identity_confidence"]),
            )
            for row in rows
        ]
        decision = choose_company_candidate(
            job.company_name,
            job.city,
            job.company_name_confidence,
            candidates,
        )
        if decision.company_id is not None:
            return decision.company_id, False, decision

        key = self._new_company_key(job, decision)
        existing = connection.execute(
            "SELECT id FROM companies WHERE company_key = ?",
            (key,),
        ).fetchone()
        if existing is not None:
            stable = ResolutionDecision(
                company_id=int(existing["id"]),
                method="stable_source_key",
                confidence=job.company_name_confidence,
            )
            return int(existing["id"]), False, stable

        normalized_city = normalize_text(job.city or "") or None
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
        created = ResolutionDecision(
            company_id=int(cursor.lastrowid),
            method=decision.method,
            confidence=decision.confidence,
        )
        return int(cursor.lastrowid), True, created

    @staticmethod
    def _new_company_key(job: JobPosting, decision: ResolutionDecision) -> str:
        base = company_key(job.company_name, job.city)
        if job.city:
            return base
        stable_source_id = job.source_id or job.url
        digest = hashlib.sha1(  # noqa: S324 - non-cryptographic stable identifier
            f"{job.source}:{stable_source_id}".encode()
        ).hexdigest()[:12]
        return f"{base}|unknown:{digest}|{decision.method}"

    @staticmethod
    def _remember_company_identity(
        connection: sqlite3.Connection,
        company_id: int,
        job: JobPosting,
    ) -> None:
        normalized_alias = normalize_company_name(job.company_name)
        connection.execute(
            """
            INSERT INTO company_aliases(
                company_id,
                alias,
                normalized_alias,
                source,
                confidence
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(company_id, alias) DO UPDATE SET
                source = CASE
                    WHEN excluded.confidence >= confidence THEN excluded.source
                    ELSE source
                END,
                confidence = MAX(confidence, excluded.confidence),
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (
                company_id,
                job.company_name,
                normalized_alias,
                job.source,
                job.company_name_confidence,
            ),
        )

        normalized_city = normalize_text(job.city or "") or None
        if normalized_city is not None and job.city is not None:
            connection.execute(
                """
                INSERT INTO company_locations(company_id, city, normalized_city)
                VALUES (?, ?, ?)
                ON CONFLICT(company_id, normalized_city) DO UPDATE SET
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (company_id, job.city, normalized_city),
            )

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
                city = CASE
                    WHEN city IS NULL AND ? IS NOT NULL THEN ?
                    ELSE city
                END,
                normalized_city = CASE
                    WHEN normalized_city IS NULL AND ? IS NOT NULL THEN ?
                    ELSE normalized_city
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                job.company_name_confidence,
                job.company_name,
                job.company_name_confidence,
                job.company_name_source,
                job.company_name_confidence,
                job.city,
                job.city,
                normalize_text(job.city or "") or None,
                normalize_text(job.city or "") or None,
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
