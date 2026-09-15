from __future__ import annotations

from dataclasses import dataclass

from .sources.base import JobSource
from .storage import SQLiteStore, UpsertStats


@dataclass(slots=True)
class IngestResult:
    source: str
    pages: int
    next_cursor: str | None
    stats: UpsertStats


async def ingest_source(
    source: JobSource,
    store: SQLiteStore,
    *,
    pages: int = 1,
    resume: bool = True,
) -> IngestResult:
    store.init_schema()
    cursor = store.get_source_cursor(source.name) if resume else None
    aggregate = UpsertStats()
    processed_pages = 0

    for _ in range(max(1, pages)):
        batch = await source.collect(cursor)
        stats = store.upsert_jobs(batch.jobs)
        aggregate.jobs_seen += stats.jobs_seen
        aggregate.jobs_inserted += stats.jobs_inserted
        aggregate.jobs_updated += stats.jobs_updated
        aggregate.companies_created += stats.companies_created
        processed_pages += 1

        cursor = batch.next_cursor
        store.set_source_cursor(source.name, cursor)
        if cursor is None:
            break

    return IngestResult(
        source=source.name,
        pages=processed_pages,
        next_cursor=cursor,
        stats=aggregate,
    )
