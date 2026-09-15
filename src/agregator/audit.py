from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from .models import DiscoveryResult
from .storage import SQLiteStore


@dataclass(frozen=True, slots=True)
class DiscoveryAuditStats:
    website_runs_recorded: int = 0
    evidence_snapshots_recorded: int = 0


def init_audit_schema(store: SQLiteStore) -> None:
    """Create append-only audit tables used by enrichment runs.

    These tables intentionally live outside the mutable current-state rows. They
    preserve what the resolver saw at a specific point in time, including rejected
    website discovery attempts and immutable hashes of contact evidence.
    """

    store.init_schema()
    with store.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS website_verification_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                website_url TEXT,
                website_confidence REAL NOT NULL DEFAULT 0,
                verification_signals_json TEXT NOT NULL,
                search_candidates_json TEXT NOT NULL,
                website_attempts_json TEXT NOT NULL DEFAULT '[]',
                scanned_pages_json TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE INDEX IF NOT EXISTS idx_website_verification_runs_company
                ON website_verification_runs(company_id, captured_at DESC);

            CREATE TABLE IF NOT EXISTS contact_evidence_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_channel_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                evidence_url TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                evidence_signal TEXT,
                content_sha256 TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contact_channel_id) REFERENCES contact_channels(id),
                FOREIGN KEY(company_id) REFERENCES companies(id),
                UNIQUE(contact_channel_id, content_sha256)
            );

            CREATE INDEX IF NOT EXISTS idx_contact_evidence_snapshots_company
                ON contact_evidence_snapshots(company_id, captured_at DESC);
            """
        )
        _ensure_column(
            connection,
            "website_verification_runs",
            "website_attempts_json",
            "TEXT NOT NULL DEFAULT '[]'",
        )


def record_discovery_audit(
    store: SQLiteStore,
    company_id: int,
    result: DiscoveryResult,
) -> DiscoveryAuditStats:
    """Persist one discovery decision and immutable snapshots of its contact evidence."""

    init_audit_schema(store)
    website_run = 0
    snapshots = 0

    candidates = [candidate.model_dump(mode="json") for candidate in result.search_candidates]
    attempts = [attempt.model_dump(mode="json") for attempt in result.website_attempts]
    outcome = "verified" if result.company.website_url else "not_verified"

    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO website_verification_runs(
                company_id,
                outcome,
                website_url,
                website_confidence,
                verification_signals_json,
                search_candidates_json,
                website_attempts_json,
                scanned_pages_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                outcome,
                result.company.website_url,
                result.company.website_confidence,
                json.dumps(
                    result.company.website_verification_signals,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(candidates, ensure_ascii=False, separators=(",", ":")),
                json.dumps(attempts, ensure_ascii=False, separators=(",", ":")),
                json.dumps(result.scanned_pages, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        website_run = 1

        for channel in result.channels:
            row = connection.execute(
                """
                SELECT id
                FROM contact_channels
                WHERE company_id = ? AND kind = ? AND value = ?
                """,
                (company_id, channel.kind.value, channel.value),
            ).fetchone()
            if row is None:
                continue

            digest = hashlib.sha256(channel.evidence.text.encode("utf-8")).hexdigest()
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO contact_evidence_snapshots(
                    contact_channel_id,
                    company_id,
                    evidence_url,
                    evidence_text,
                    evidence_signal,
                    content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    company_id,
                    channel.evidence.url,
                    channel.evidence.text,
                    channel.evidence.signal,
                    digest,
                ),
            )
            snapshots += int(cursor.rowcount > 0)

    return DiscoveryAuditStats(
        website_runs_recorded=website_run,
        evidence_snapshots_recorded=snapshots,
    )


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
