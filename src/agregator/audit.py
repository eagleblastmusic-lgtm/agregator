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
    evidence_observations_recorded: int = 0
    evidence_changes_recorded: int = 0


def init_audit_schema(store: SQLiteStore) -> None:
    """Create append-only audit tables used by enrichment runs.

    These tables intentionally live outside the mutable current-state rows. They
    preserve what the resolver saw at a specific point in time, including rejected
    website discovery attempts, immutable contact-evidence snapshots and the full
    observation timeline linking each contact classification to a discovery run.
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
                resolution_origin TEXT,
                resolution_source TEXT,
                verification_signals_json TEXT NOT NULL,
                search_candidates_json TEXT NOT NULL,
                website_attempts_json TEXT NOT NULL DEFAULT '[]',
                scanned_pages_json TEXT NOT NULL,
                page_snapshots_json TEXT NOT NULL DEFAULT '[]',
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

            CREATE TABLE IF NOT EXISTS contact_evidence_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                website_verification_run_id INTEGER NOT NULL,
                contact_channel_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                snapshot_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                purpose TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_url TEXT NOT NULL,
                evidence_signal TEXT,
                snapshot_changed INTEGER NOT NULL DEFAULT 0,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(website_verification_run_id) REFERENCES website_verification_runs(id),
                FOREIGN KEY(contact_channel_id) REFERENCES contact_channels(id),
                FOREIGN KEY(company_id) REFERENCES companies(id),
                FOREIGN KEY(snapshot_id) REFERENCES contact_evidence_snapshots(id)
            );

            CREATE INDEX IF NOT EXISTS idx_contact_evidence_observations_channel
                ON contact_evidence_observations(contact_channel_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_contact_evidence_observations_company
                ON contact_evidence_observations(company_id, captured_at DESC);
            CREATE INDEX IF NOT EXISTS idx_contact_evidence_observations_run
                ON contact_evidence_observations(website_verification_run_id);
            """
        )
        _ensure_column(
            connection,
            "website_verification_runs",
            "website_attempts_json",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        _ensure_column(
            connection,
            "website_verification_runs",
            "page_snapshots_json",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        _ensure_column(
            connection,
            "website_verification_runs",
            "resolution_origin",
            "TEXT",
        )
        _ensure_column(
            connection,
            "website_verification_runs",
            "resolution_source",
            "TEXT",
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_website_verification_runs_origin
            ON website_verification_runs(resolution_origin, resolution_source)
            """
        )


def record_discovery_audit(
    store: SQLiteStore,
    company_id: int,
    result: DiscoveryResult,
) -> DiscoveryAuditStats:
    """Persist one discovery decision and immutable contact-evidence observations."""

    init_audit_schema(store)
    website_run = 0
    snapshots = 0
    observations = 0
    changes = 0

    candidates = [candidate.model_dump(mode="json") for candidate in result.search_candidates]
    attempts = [attempt.model_dump(mode="json") for attempt in result.website_attempts]
    page_snapshots = [snapshot.model_dump(mode="json") for snapshot in result.page_snapshots]
    outcome = "verified" if result.company.website_url else "not_verified"
    origin = (
        result.company.website_resolution_origin.value
        if result.company.website_resolution_origin is not None
        else None
    )

    with store.connect() as connection:
        run_cursor = connection.execute(
            """
            INSERT INTO website_verification_runs(
                company_id,
                outcome,
                website_url,
                website_confidence,
                resolution_origin,
                resolution_source,
                verification_signals_json,
                search_candidates_json,
                website_attempts_json,
                scanned_pages_json,
                page_snapshots_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                outcome,
                result.company.website_url,
                result.company.website_confidence,
                origin,
                result.company.website_resolution_source,
                json.dumps(
                    result.company.website_verification_signals,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(candidates, ensure_ascii=False, separators=(",", ":")),
                json.dumps(attempts, ensure_ascii=False, separators=(",", ":")),
                json.dumps(result.scanned_pages, ensure_ascii=False, separators=(",", ":")),
                json.dumps(page_snapshots, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        website_run_id = int(run_cursor.lastrowid)
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

            contact_channel_id = int(row["id"])
            digest = hashlib.sha256(channel.evidence.text.encode("utf-8")).hexdigest()
            snapshot_cursor = connection.execute(
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
                    contact_channel_id,
                    company_id,
                    channel.evidence.url,
                    channel.evidence.text,
                    channel.evidence.signal,
                    digest,
                ),
            )
            snapshots += int(snapshot_cursor.rowcount > 0)

            snapshot_row = connection.execute(
                """
                SELECT id
                FROM contact_evidence_snapshots
                WHERE contact_channel_id = ? AND content_sha256 = ?
                """,
                (contact_channel_id, digest),
            ).fetchone()
            if snapshot_row is None:
                continue
            snapshot_id = int(snapshot_row["id"])

            previous = connection.execute(
                """
                SELECT snapshot_id
                FROM contact_evidence_observations
                WHERE contact_channel_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (contact_channel_id,),
            ).fetchone()
            snapshot_changed = int(
                previous is not None and int(previous["snapshot_id"]) != snapshot_id
            )

            connection.execute(
                """
                INSERT INTO contact_evidence_observations(
                    website_verification_run_id,
                    contact_channel_id,
                    company_id,
                    snapshot_id,
                    decision,
                    purpose,
                    confidence,
                    evidence_url,
                    evidence_signal,
                    snapshot_changed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    website_run_id,
                    contact_channel_id,
                    company_id,
                    snapshot_id,
                    channel.decision.value,
                    channel.purpose.value,
                    channel.confidence,
                    channel.evidence.url,
                    channel.evidence.signal,
                    snapshot_changed,
                ),
            )
            observations += 1
            changes += snapshot_changed

    return DiscoveryAuditStats(
        website_runs_recorded=website_run,
        evidence_snapshots_recorded=snapshots,
        evidence_observations_recorded=observations,
        evidence_changes_recorded=changes,
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
