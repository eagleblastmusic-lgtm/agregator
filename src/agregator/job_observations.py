from __future__ import annotations

import json
from collections.abc import Iterable

from .models import JobPosting
from .storage import SQLiteStore


def init_job_observation_schema(store: SQLiteStore) -> None:
    """Create the append-only raw/source observation table.

    `job_postings` remains the convenient current normalized view keyed by
    `(source, source_id)`. This table is deliberately different: it records every
    observation returned by a collector, including repeated appearances of the
    same source record and different representations of the same vacancy across
    different portals. There is intentionally no deduplication constraint.
    """

    store.init_schema()
    with store.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS job_posting_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_run_id INTEGER,
                source TEXT NOT NULL,
                source_id TEXT,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                company_name_raw TEXT NOT NULL,
                city TEXT,
                description TEXT,
                published_at TEXT,
                refreshed_at TEXT,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_run_id) REFERENCES source_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_job_posting_observations_source
                ON job_posting_observations(source, observed_at);
            CREATE INDEX IF NOT EXISTS idx_job_posting_observations_source_id
                ON job_posting_observations(source, source_id);
            CREATE INDEX IF NOT EXISTS idx_job_posting_observations_run
                ON job_posting_observations(source_run_id);
            """
        )


def record_job_observations(
    store: SQLiteStore,
    jobs: Iterable[JobPosting],
    *,
    source_run_id: int | None,
) -> int:
    """Append every collector result exactly once for this ingestion pass.

    Nothing is merged here. `payload_json` preserves the complete parsed
    `JobPosting`, including source-specific identifiers and website candidates.
    """

    init_job_observation_schema(store)
    rows = list(jobs)
    if not rows:
        return 0

    with store.connect() as connection:
        connection.executemany(
            """
            INSERT INTO job_posting_observations(
                source_run_id,
                source,
                source_id,
                url,
                title,
                company_name_raw,
                city,
                description,
                published_at,
                refreshed_at,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    source_run_id,
                    job.source,
                    job.source_id,
                    job.url,
                    job.title,
                    job.company_name,
                    job.city,
                    job.description,
                    job.published_at,
                    job.refreshed_at,
                    json.dumps(job.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                )
                for job in rows
            ],
        )
    return len(rows)
